"""Bulk catalog authoring from a flat CSV.

The owner holds most of this taxonomy in their head, and typing it into nested
JSON is the wrong shape for that. This module accepts one wide row per รุ่นย่อย
and builds the brand/model/generation/variant/period nesting underneath, so the
catalog can be filled in a spreadsheet and re-imported at any time.

Re-importing is safe: a row that names an existing variant updates it instead of
duplicating it, and a row with a later ``start`` adds a dated period rather than
overwriting the previous price.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Optional

from .catalog import DATA_DIR, Catalog, CatalogError
from .normalize import slug
from .taxonomy import (
    BodyType, BrandSegment, CabType, Drivetrain, ImportType, Powertrain,
    RegistrationType, Segment,
)

COLUMNS: tuple[str, ...] = (
    # identity
    "brand", "model", "generation", "variant",
    # brand facets
    "brand_th", "brand_segment", "oem_group", "brand_origin",
    # model facets
    "model_th", "body_type", "registration_type", "model_aliases",
    # generation facets
    "segment", "seats", "launched", "ended",
    # variant facets
    "powertrain", "drivetrain", "engine_cc", "battery_kwh", "cab_type",
    "variant_aliases",
    # dated commercial facets
    "start", "end", "price_thb", "import_type", "origin_country", "model_year",
    "price_note",
)

REQUIRED: tuple[str, ...] = ("brand", "model", "variant")


def template(path: Path | str) -> Path:
    """Write an empty CSV with the full column set and one worked example."""
    path = Path(path)
    example = {
        "brand": "Toyota", "model": "Yaris Ativ", "generation": "MXPA10",
        "variant": "1.2 Smart", "brand_th": "โตโยต้า", "brand_segment": "MASS",
        "oem_group": "Toyota Group", "brand_origin": "JP",
        "model_th": "ยาริส เอทีฟ", "body_type": "SEDAN",
        "registration_type": "RY1", "model_aliases": "ativ|ยาริสเอทีฟ",
        "segment": "B", "seats": "5", "launched": "2022-08-09", "ended": "",
        "powertrain": "ICE", "drivetrain": "FWD", "engine_cc": "1197",
        "battery_kwh": "", "cab_type": "", "variant_aliases": "1.2 smart cvt",
        "start": "2022-08-09", "end": "", "price_thb": "609000",
        "import_type": "CKD", "origin_country": "TH", "model_year": "",
        "price_note": "",
    }
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        writer.writerow(example)
    return path


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _num(value: Any) -> Optional[float]:
    text = _clean(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise CatalogError(f"{value!r} is not a number")


def _int(value: Any) -> Optional[int]:
    number = _num(value)
    return int(number) if number is not None else None


def _aliases(value: Any) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    return [part.strip() for part in text.replace(";", "|").split("|")
            if part.strip()]


def _find(items: list[dict], key: str, value: str) -> Optional[dict]:
    folded = slug(value)
    for item in items:
        if slug(item.get(key, "")) == folded:
            return item
    return None


def apply_rows(payloads: dict[str, dict], rows: Iterable[dict[str, Any]]
               ) -> tuple[int, list[str]]:
    """Merge CSV rows into ``{brand_id: brand_payload}``. Returns (rows, problems)."""
    problems: list[str] = []
    applied = 0

    for line_no, row in enumerate(rows, start=2):
        try:
            missing = [c for c in REQUIRED if not _clean(row.get(c))]
            if missing:
                if any(_clean(v) for v in row.values()):
                    problems.append(f"line {line_no}: missing {', '.join(missing)}")
                continue

            brand_name = _clean(row["brand"])
            brand_id = slug(brand_name)
            payload = payloads.setdefault(brand_id, {
                "brand": {"id": brand_id, "name_en": brand_name, "name_th": "",
                          "brand_segment": "UNKNOWN", "oem_group": "UNKNOWN",
                          "brand_origin": "UNKNOWN", "aliases": []},
                "models": [],
            })
            brand = payload["brand"]
            if _clean(row.get("brand_th")):
                brand["name_th"] = _clean(row["brand_th"])
            if _clean(row.get("brand_segment")):
                brand["brand_segment"] = BrandSegment.parse(row["brand_segment"]).value
            if _clean(row.get("oem_group")):
                brand["oem_group"] = _clean(row["oem_group"])
            if _clean(row.get("brand_origin")):
                brand["brand_origin"] = _clean(row["brand_origin"]).upper()

            model_name = _clean(row["model"])
            model = _find(payload["models"], "name_en", model_name)
            if model is None:
                model = {"id": slug(model_name), "name_en": model_name,
                         "name_th": "", "body_type": "OTHER",
                         "cab_type": "NOT_APPLICABLE",
                         "registration_type": "RY1", "aliases": [],
                         "generations": []}
                payload["models"].append(model)
            if _clean(row.get("model_th")):
                model["name_th"] = _clean(row["model_th"])
            if _clean(row.get("body_type")):
                model["body_type"] = BodyType.parse(row["body_type"]).value
                if model["body_type"] == "PICKUP" and \
                        not _clean(row.get("registration_type")):
                    model["registration_type"] = "RY3"
            if _clean(row.get("registration_type")):
                model["registration_type"] = RegistrationType.parse(
                    row["registration_type"]).value
            for alias in _aliases(row.get("model_aliases")):
                if alias not in model["aliases"]:
                    model["aliases"].append(alias)

            gen_code = _clean(row.get("generation")) or _clean(
                row.get("launched"))[:4] or "gen1"
            gen = _find(model["generations"], "code", gen_code)
            if gen is None:
                gen = {"code": gen_code, "segment": "UNKNOWN", "seats": None,
                       "launched": None, "ended": None, "variants": []}
                model["generations"].append(gen)
            if _clean(row.get("segment")):
                gen["segment"] = Segment.parse(row["segment"]).value
            if _clean(row.get("seats")):
                gen["seats"] = _int(row["seats"])
            if _clean(row.get("launched")):
                gen["launched"] = _clean(row["launched"])
            if _clean(row.get("ended")):
                gen["ended"] = _clean(row["ended"])

            variant_name = _clean(row["variant"])
            variant = _find(gen["variants"], "name", variant_name)
            if variant is None:
                variant = {"name": variant_name, "powertrain": "UNKNOWN",
                           "drivetrain": "UNKNOWN", "engine_cc": None,
                           "battery_kwh": None, "cab_type": "NOT_APPLICABLE",
                           "aliases": [], "periods": []}
                gen["variants"].append(variant)
            if _clean(row.get("powertrain")):
                variant["powertrain"] = Powertrain.parse(row["powertrain"]).value
            if _clean(row.get("drivetrain")):
                variant["drivetrain"] = Drivetrain.parse(row["drivetrain"]).value
            if _clean(row.get("engine_cc")):
                variant["engine_cc"] = _int(row["engine_cc"])
            if _clean(row.get("battery_kwh")):
                variant["battery_kwh"] = _num(row["battery_kwh"])
            if _clean(row.get("cab_type")):
                variant["cab_type"] = CabType.parse(row["cab_type"]).value
            for alias in _aliases(row.get("variant_aliases")):
                if alias not in variant["aliases"]:
                    variant["aliases"].append(alias)

            start = _clean(row.get("start")) or gen.get("launched") or "1900-01-01"
            period = next((p for p in variant["periods"] if p["start"] == start),
                          None)
            if period is None:
                period = {"start": start, "end": None, "price_thb": None,
                          "import_type": "UNKNOWN", "origin_country": "UNKNOWN",
                          "model_year": None, "price_note": ""}
                variant["periods"].append(period)
                variant["periods"].sort(key=lambda p: p["start"])
                # Close the preceding open period so the timeline stays a
                # partition rather than a set of overlapping claims.
                index = variant["periods"].index(period)
                if index > 0 and variant["periods"][index - 1].get("end") is None:
                    variant["periods"][index - 1]["end"] = start
            if _clean(row.get("end")):
                period["end"] = _clean(row["end"])
            if _clean(row.get("price_thb")):
                period["price_thb"] = _num(row["price_thb"])
            if _clean(row.get("import_type")):
                period["import_type"] = ImportType.parse(row["import_type"]).value
            if _clean(row.get("origin_country")):
                period["origin_country"] = _clean(row["origin_country"]).upper()
            if _clean(row.get("model_year")):
                period["model_year"] = _int(row["model_year"])
            if _clean(row.get("price_note")):
                period["price_note"] = _clean(row["price_note"])
            applied += 1
        except (ValueError, CatalogError) as exc:
            problems.append(f"line {line_no}: {exc}")

    return applied, problems


def import_csv(path: Path | str, data_dir: Path | str = DATA_DIR, *,
               dry_run: bool = False) -> tuple[int, list[str], list[str]]:
    """Merge a CSV into the on-disk catalog. Returns (rows, problems, files)."""
    data_dir = Path(data_dir)
    models_dir = data_dir / "models"
    payloads: dict[str, dict] = {}
    for existing in sorted(models_dir.glob("*.json")):
        payload = json.loads(existing.read_text(encoding="utf-8"))
        payloads[payload["brand"]["id"]] = payload

    # Problems the catalog already had are not this import's fault; only newly
    # introduced ones block the write.
    try:
        baseline = set(Catalog.load(data_dir).validate()) if payloads else set()
    except CatalogError:
        baseline = set()

    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    before = {bid: json.dumps(p, sort_keys=True) for bid, p in payloads.items()}
    applied, problems = apply_rows(payloads, rows)

    # Fail closed: a catalog that will not load is never written to disk.
    probe = Catalog()
    for bid, payload in payloads.items():
        probe.add_brand_payload(payload, source=f"<import {bid}>")
    probe.build_indexes()
    introduced = [p for p in probe.validate() if p not in baseline]
    problems += introduced

    written: list[str] = []
    if not dry_run and not problems:
        models_dir.mkdir(parents=True, exist_ok=True)
        for bid, payload in payloads.items():
            if before.get(bid) == json.dumps(payload, sort_keys=True):
                continue
            target = models_dir / f"{bid}.json"
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            written.append(str(target))
    return applied, problems, written


def export_csv(catalog: Catalog, path: Path | str) -> int:
    """Flatten the catalog back out to the same wide CSV shape."""
    count = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        for variant in catalog.variants.values():
            gen = catalog.generation_for_variant(variant.id)
            model = catalog.model_for_variant(variant.id)
            brand = catalog.brand_for_variant(variant.id)
            for period in catalog.periods.get(variant.id, []) or [None]:
                writer.writerow({
                    "brand": brand.name_en, "model": model.name_en,
                    "generation": gen.code, "variant": variant.name,
                    "brand_th": brand.name_th,
                    "brand_segment": brand.brand_segment.value,
                    "oem_group": brand.oem_group,
                    "brand_origin": brand.brand_origin,
                    "model_th": model.name_th,
                    "body_type": model.body_type.value,
                    "registration_type": model.registration_type.value,
                    "model_aliases": "|".join(model.aliases),
                    "segment": gen.segment.value, "seats": gen.seats,
                    "launched": gen.launched, "ended": gen.ended,
                    "powertrain": variant.powertrain.value,
                    "drivetrain": variant.drivetrain.value,
                    "engine_cc": variant.engine_cc,
                    "battery_kwh": variant.battery_kwh,
                    "cab_type": variant.cab_type.value,
                    "variant_aliases": "|".join(variant.aliases),
                    "start": period.start if period else "",
                    "end": period.end if period else "",
                    "price_thb": period.price_thb if period else "",
                    "import_type": period.import_type.value if period else "",
                    "origin_country": period.origin_country if period else "",
                    "model_year": period.model_year if period else "",
                    "price_note": period.price_note if period else "",
                })
                count += 1
    return count
