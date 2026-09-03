"""Bulk catalog authoring from a flat CSV, for one year at a time.

The owner holds most of this taxonomy in their head, and typing it into nested
JSON is the wrong shape for that. This module accepts one wide row per รุ่นย่อย
and builds the brand/model/generation/variant nesting underneath, so the catalog
can be filled in a spreadsheet and re-imported at any time.

Two rules from the taxonomy show up here as column behaviour:

* ``body_type`` and ``cab_type`` belong to the model. One nameplate sold in two
  bodies is two rows with two different ``model`` names - the importer will not
  let a second body hide inside a trim.
* ``registration_type`` is left blank in normal use. A double-cab pickup resolves
  to รย.1 and the other cabs to รย.3 on their own.

Re-importing is safe: a row that names an existing variant updates it in place
rather than duplicating it.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Optional

from .catalog import DATA_DIR, DEFAULT_YEAR, Catalog, CatalogError, year_dir
from .normalize import slug
from .taxonomy import (
    BodyType, BrandSegment, CabType, Drivetrain, ImportType, Powertrain,
    RegistrationType, Segment,
)

COLUMNS: tuple[str, ...] = (
    # identity - brand + model + variant is the minimum for a usable row
    "brand", "model", "generation", "variant",
    # brand facets
    "brand_th", "brand_segment", "oem_group", "brand_origin",
    # model facets (one model = one body; pickups split by cab)
    "model_th", "body_type", "cab_type", "registration_type", "model_aliases",
    # generation facets
    "segment", "seats", "launched", "ended",
    # variant facets
    "powertrain", "drivetrain", "engine_cc", "battery_kwh", "variant_aliases",
    # commercial facets for this catalog year
    "price_thb", "import_type", "origin_country", "price_note",
)

REQUIRED: tuple[str, ...] = ("brand", "model", "variant")

EXAMPLE_ROWS: tuple[dict[str, str], ...] = (
    {
        "brand": "Toyota", "model": "Yaris Ativ", "generation": "MXPA10",
        "variant": "1.2 Smart", "brand_th": "โตโยต้า", "brand_segment": "MASS",
        "oem_group": "Toyota Group", "brand_origin": "JP",
        "model_th": "ยาริส เอทีฟ", "body_type": "SEDAN", "cab_type": "",
        "registration_type": "", "model_aliases": "ativ|ยาริสเอทีฟ",
        "segment": "B", "seats": "5", "launched": "2022-08-09", "ended": "",
        "powertrain": "ICE", "drivetrain": "FWD", "engine_cc": "1197",
        "battery_kwh": "", "variant_aliases": "1.2 smart cvt",
        "price_thb": "609000", "import_type": "CKD", "origin_country": "TH",
        "price_note": "",
    },
    {
        # A pickup: one model per cab, and the รย. class follows from the cab.
        "brand": "Toyota", "model": "Hilux Revo Double Cab", "generation": "AN120",
        "variant": "2.8 GR Sport 4x4", "body_type": "PICKUP",
        "cab_type": "DOUBLE_CAB", "registration_type": "",
        "model_aliases": "revo double cab|revo 4 ประตู", "segment": "F",
        "seats": "5", "powertrain": "ICE", "drivetrain": "4WD",
        "engine_cc": "2755", "price_thb": "1359000", "import_type": "CKD",
        "origin_country": "TH",
    },
)


def template(path: Path | str) -> Path:
    """Write a CSV with the full column set and two worked examples."""
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS),
                                extrasaction="ignore")
        writer.writeheader()
        for row in EXAMPLE_ROWS:
            writer.writerow(row)
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
                         "registration_type": "", "aliases": [],
                         "generations": []}
                payload["models"].append(model)
            if _clean(row.get("model_th")):
                model["name_th"] = _clean(row["model_th"])
            if _clean(row.get("body_type")):
                body = BodyType.parse(row["body_type"]).value
                if model["body_type"] not in {"OTHER", body}:
                    raise CatalogError(
                        f"model {model_name!r} is already {model['body_type']}; "
                        f"a nameplate sold as {body} too is a separate model - "
                        f"give it its own name, e.g. '{model_name} {body.title()}'")
                model["body_type"] = body
            if _clean(row.get("cab_type")):
                model["cab_type"] = CabType.parse(row["cab_type"]).value
            if _clean(row.get("registration_type")):
                model["registration_type"] = RegistrationType.parse(
                    row["registration_type"]).value
            for alias in _aliases(row.get("model_aliases")):
                if alias not in model["aliases"]:
                    model["aliases"].append(alias)

            gen_code = _clean(row.get("generation")) or "gen1"
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
                           "battery_kwh": None, "price_thb": None,
                           "import_type": "UNKNOWN", "origin_country": "UNKNOWN",
                           "price_note": "", "aliases": []}
                gen["variants"].append(variant)
            if _clean(row.get("powertrain")):
                variant["powertrain"] = Powertrain.parse(row["powertrain"]).value
            if _clean(row.get("drivetrain")):
                variant["drivetrain"] = Drivetrain.parse(row["drivetrain"]).value
            if _clean(row.get("engine_cc")):
                variant["engine_cc"] = _int(row["engine_cc"])
            if _clean(row.get("battery_kwh")):
                variant["battery_kwh"] = _num(row["battery_kwh"])
            if _clean(row.get("price_thb")):
                variant["price_thb"] = _num(row["price_thb"])
            if _clean(row.get("import_type")):
                variant["import_type"] = ImportType.parse(row["import_type"]).value
            if _clean(row.get("origin_country")):
                variant["origin_country"] = _clean(row["origin_country"]).upper()
            if _clean(row.get("price_note")):
                variant["price_note"] = _clean(row["price_note"])
            for alias in _aliases(row.get("variant_aliases")):
                if alias not in variant["aliases"]:
                    variant["aliases"].append(alias)
            applied += 1
        except (ValueError, CatalogError) as exc:
            problems.append(f"line {line_no}: {exc}")

    return applied, problems


def import_csv(path: Path | str, data_dir: Path | str = DATA_DIR, *,
               year: int = DEFAULT_YEAR,
               dry_run: bool = False) -> tuple[int, list[str], list[str]]:
    """Merge a CSV into one year's catalog. Returns (rows, problems, files)."""
    models_dir = year_dir(data_dir, year)
    payloads: dict[str, dict] = {}
    for existing in sorted(models_dir.glob("*.json")):
        payload = json.loads(existing.read_text(encoding="utf-8"))
        payloads[payload["brand"]["id"]] = payload

    # Problems the catalog already had are not this import's fault; only newly
    # introduced ones block the write.
    try:
        baseline = set(Catalog.load(data_dir, year).validate()) if payloads \
            else set()
    except CatalogError:
        baseline = set()

    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    before = {bid: json.dumps(p, sort_keys=True) for bid, p in payloads.items()}
    applied, problems = apply_rows(payloads, rows)

    # Fail closed: a catalog that will not load or will not validate is never
    # written to disk.
    probe = Catalog(year)
    for bid, payload in payloads.items():
        probe.add_brand_payload(payload, source=f"<import {bid}>")
    probe.build_indexes()
    problems += [p for p in probe.validate() if p not in baseline]

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
    """Flatten a year's catalog back out to the same wide CSV shape."""
    count = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
        writer.writeheader()
        for variant in catalog.variants.values():
            gen = catalog.generation_for_variant(variant.id)
            model = catalog.model_for_variant(variant.id)
            brand = catalog.brand_for_variant(variant.id)
            writer.writerow({
                "brand": brand.name_en, "model": model.name_en,
                "generation": gen.code, "variant": variant.name,
                "brand_th": brand.name_th,
                "brand_segment": brand.brand_segment.value,
                "oem_group": brand.oem_group,
                "brand_origin": brand.brand_origin,
                "model_th": model.name_th,
                "body_type": model.body_type.value,
                "cab_type": model.cab_type.value,
                "registration_type": model.registration_type.value,
                "model_aliases": "|".join(model.aliases),
                "segment": gen.segment.value, "seats": gen.seats,
                "launched": gen.launched, "ended": gen.ended,
                "powertrain": variant.powertrain.value,
                "drivetrain": variant.drivetrain.value,
                "engine_cc": variant.engine_cc,
                "battery_kwh": variant.battery_kwh,
                "variant_aliases": "|".join(variant.aliases),
                "price_thb": variant.price_thb,
                "import_type": variant.import_type.value,
                "origin_country": variant.origin_country,
                "price_note": variant.price_note,
            })
            count += 1
    return count
