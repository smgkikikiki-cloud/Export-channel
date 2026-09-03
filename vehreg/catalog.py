"""Loading, validating and querying the vehicle catalog.

The catalog is plain JSON on disk, one file per brand, so the owner can extend
it in a text editor or with ``python -m vehreg catalog`` and diff it in Git. A
brand file nests the identity layers exactly as ``entities.py`` describes them:

    brand -> models[] -> generations[] -> variants[] -> periods[]

IDs are composed from the path, so nothing in the file has to repeat a parent
key and no two brands can collide.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from .entities import (
    Brand, Generation, Model, ResolvedVehicle, Variant, VariantPeriod,
    cross_check, resolve,
)
from .normalize import MatchIndex, slug
from .taxonomy import (
    BodyType, BrandSegment, CabType, Drivetrain, ImportType, Powertrain,
    RegistrationType, Segment,
)

DATA_DIR = Path(__file__).with_name("data")
MODELS_DIR = DATA_DIR / "models"


class CatalogError(ValueError):
    pass


def _facet(cls, raw, default):
    if raw in (None, ""):
        return default
    return cls.parse(raw)


#: Override values arriving from JSON are plain strings; parse the ones that
#: name a closed vocabulary so downstream code always sees the enum.
_OVERRIDE_PARSERS = {
    "body_type": BodyType, "cab_type": CabType, "segment": Segment,
    "powertrain": Powertrain, "drivetrain": Drivetrain,
    "import_type": ImportType, "brand_segment": BrandSegment,
    "registration_type": RegistrationType,
}


def _overrides(raw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in dict(raw or {}).items():
        parser = _OVERRIDE_PARSERS.get(key)
        out[key] = parser.parse(value) if parser and value not in (None, "") else value
    return out


def _tuple(raw: Any) -> tuple[str, ...]:
    if not raw:
        return ()
    if isinstance(raw, str):
        return (raw,)
    return tuple(str(x) for x in raw)


class Catalog:
    """In-memory catalog with the match indexes the ingest layer needs."""

    def __init__(self) -> None:
        self.brands: dict[str, Brand] = {}
        self.models: dict[str, Model] = {}
        self.generations: dict[str, Generation] = {}
        self.variants: dict[str, Variant] = {}
        self.periods: dict[str, list[VariantPeriod]] = {}
        self.brand_index = MatchIndex()
        self.model_index = MatchIndex()
        self.variant_index = MatchIndex()
        self._models_by_brand: dict[str, list[str]] = {}
        self._variants_by_model: dict[str, list[str]] = {}

    # ---------------------------------------------------------------- load
    @classmethod
    def load(cls, data_dir: Path | str = DATA_DIR) -> "Catalog":
        catalog = cls()
        data_dir = Path(data_dir)
        model_files = sorted((data_dir / "models").glob("*.json"))
        if not model_files:
            raise CatalogError(f"no brand files under {data_dir / 'models'}")
        for path in model_files:
            catalog.load_brand_file(path)
        catalog.build_indexes()
        return catalog

    def load_brand_file(self, path: Path) -> None:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CatalogError(f"{path}: invalid JSON: {exc}") from exc
        self.add_brand_payload(payload, source=str(path))

    def add_brand_payload(self, payload: dict, source: str = "<memory>") -> None:
        raw_brand = payload.get("brand")
        if not raw_brand:
            raise CatalogError(f"{source}: missing 'brand'")
        brand_id = slug(raw_brand.get("id") or raw_brand["name_en"])
        if brand_id in self.brands:
            raise CatalogError(f"{source}: duplicate brand id {brand_id!r}")
        brand = Brand(
            id=brand_id,
            name_en=raw_brand["name_en"],
            name_th=raw_brand.get("name_th", ""),
            brand_segment=_facet(BrandSegment, raw_brand.get("brand_segment"),
                                 BrandSegment.UNKNOWN),
            oem_group=raw_brand.get("oem_group", "UNKNOWN"),
            brand_origin=raw_brand.get("brand_origin", "UNKNOWN"),
            aliases=_tuple(raw_brand.get("aliases")),
            overrides=_overrides(raw_brand.get("overrides")),
        )
        self.brands[brand_id] = brand
        self._models_by_brand[brand_id] = []

        for raw_model in payload.get("models", []):
            self._add_model(brand_id, raw_model, source)

    def _add_model(self, brand_id: str, raw: dict, source: str) -> None:
        model_id = f"{brand_id}.{slug(raw.get('id') or raw['name_en'])}"
        if model_id in self.models:
            raise CatalogError(f"{source}: duplicate model id {model_id!r}")
        body = _facet(BodyType, raw.get("body_type"), BodyType.OTHER)
        model = Model(
            id=model_id,
            brand_id=brand_id,
            name_en=raw["name_en"],
            name_th=raw.get("name_th", ""),
            body_type=body,
            cab_type=_facet(CabType, raw.get("cab_type"), CabType.NOT_APPLICABLE),
            registration_type=_facet(
                RegistrationType, raw.get("registration_type"),
                RegistrationType.RY3 if body is BodyType.PICKUP
                else RegistrationType.RY1),
            aliases=_tuple(raw.get("aliases")),
            notes=raw.get("notes", ""),
            overrides=_overrides(raw.get("overrides")),
        )
        self.models[model_id] = model
        self._models_by_brand[brand_id].append(model_id)
        self._variants_by_model[model_id] = []

        generations = raw.get("generations")
        if not generations:
            raise CatalogError(f"{source}: model {model_id} has no generations")
        for raw_gen in generations:
            self._add_generation(model_id, raw_gen, source)

    def _add_generation(self, model_id: str, raw: dict, source: str) -> None:
        code = raw.get("code") or raw.get("id") or raw.get("launched", "gen")[:4]
        gen_id = f"{model_id}.{slug(code)}"
        if gen_id in self.generations:
            raise CatalogError(f"{source}: duplicate generation id {gen_id!r}")
        gen = Generation(
            id=gen_id,
            model_id=model_id,
            code=raw.get("code", ""),
            segment=_facet(Segment, raw.get("segment"), Segment.UNKNOWN),
            seats=raw.get("seats"),
            launched=raw.get("launched"),
            ended=raw.get("ended"),
            overrides=_overrides(raw.get("overrides")),
        )
        self.generations[gen_id] = gen
        for raw_variant in raw.get("variants", []):
            self._add_variant(gen_id, model_id, raw_variant, source)

    def _add_variant(self, gen_id: str, model_id: str, raw: dict,
                     source: str) -> None:
        variant_id = f"{gen_id}.{slug(raw.get('id') or raw['name'])}"
        if variant_id in self.variants:
            raise CatalogError(f"{source}: duplicate variant id {variant_id!r}")
        variant = Variant(
            id=variant_id,
            generation_id=gen_id,
            name=raw["name"],
            powertrain=_facet(Powertrain, raw.get("powertrain"), Powertrain.UNKNOWN),
            drivetrain=_facet(Drivetrain, raw.get("drivetrain"), Drivetrain.UNKNOWN),
            engine_cc=raw.get("engine_cc"),
            battery_kwh=raw.get("battery_kwh"),
            cab_type=_facet(CabType, raw.get("cab_type"), CabType.NOT_APPLICABLE),
            aliases=_tuple(raw.get("aliases")),
            overrides=_overrides(raw.get("overrides")),
        )
        self.variants[variant_id] = variant
        self._variants_by_model[model_id].append(variant_id)

        periods = raw.get("periods") or []
        if not periods and raw.get("price_thb") is not None:
            periods = [{
                "start": raw.get("start") or self.generations[gen_id].launched
                or "1900-01-01",
                "price_thb": raw.get("price_thb"),
                "import_type": raw.get("import_type"),
                "origin_country": raw.get("origin_country"),
            }]
        parsed = [
            VariantPeriod(
                variant_id=variant_id,
                start=p["start"],
                end=p.get("end"),
                price_thb=p.get("price_thb"),
                import_type=_facet(ImportType, p.get("import_type"),
                                   ImportType.UNKNOWN),
                origin_country=p.get("origin_country", "UNKNOWN"),
                model_year=p.get("model_year"),
                price_note=p.get("price_note", ""),
                overrides=_overrides(p.get("overrides")),
            )
            for p in periods
        ]
        self.periods[variant_id] = sorted(parsed, key=lambda p: p.start)

    # -------------------------------------------------------------- indexes
    def build_indexes(self) -> None:
        self.brand_index = MatchIndex()
        self.model_index = MatchIndex()
        self.variant_index = MatchIndex()
        for brand in self.brands.values():
            self.brand_index.add(brand.id,
                                 [brand.name_en, brand.name_th, brand.id,
                                  *brand.aliases])
        for model in self.models.values():
            brand = self.brands[model.brand_id]
            surfaces = [model.name_en, model.name_th, *model.aliases]
            # Both bare and brand-prefixed spellings appear in DLT exports.
            surfaces += [f"{brand.name_en} {s}" for s in surfaces if s]
            surfaces += [f"{brand.name_th} {s}" for s in surfaces if s and brand.name_th]
            self.model_index.add(model.id, [s for s in surfaces if s])
        for variant in self.variants.values():
            model = self.model_for_variant(variant.id)
            surfaces = [variant.name, *variant.aliases]
            surfaces += [f"{model.name_en} {s}" for s in surfaces if s]
            self.variant_index.add(variant.id, [s for s in surfaces if s])

    # ------------------------------------------------------------ traversal
    def generation_for_variant(self, variant_id: str) -> Generation:
        return self.generations[self.variants[variant_id].generation_id]

    def model_for_variant(self, variant_id: str) -> Model:
        return self.models[self.generation_for_variant(variant_id).model_id]

    def brand_for_variant(self, variant_id: str) -> Brand:
        return self.brands[self.model_for_variant(variant_id).brand_id]

    def models_of(self, brand_id: str) -> list[Model]:
        return [self.models[m] for m in self._models_by_brand.get(brand_id, [])]

    def variants_of(self, model_id: str) -> list[Variant]:
        return [self.variants[v] for v in self._variants_by_model.get(model_id, [])]

    def period_for(self, variant_id: str, as_of: str) -> Optional[VariantPeriod]:
        """The dated record covering ``as_of``.

        Facts older than the first period fall back to the earliest record and
        newer facts to the latest, so a price list that starts mid-history still
        classifies every row instead of dropping it into UNKNOWN.
        """
        periods = self.periods.get(variant_id) or []
        if not periods:
            return None
        for period in periods:
            if period.covers(as_of):
                return period
        if as_of < periods[0].start:
            return periods[0]
        return periods[-1]

    # ------------------------------------------------------------- resolve
    def resolve(self, variant_id: str, as_of: str) -> ResolvedVehicle:
        variant = self.variants[variant_id]
        generation = self.generations[variant.generation_id]
        model = self.models[generation.model_id]
        brand = self.brands[model.brand_id]
        return resolve(brand, model, generation, variant,
                       self.period_for(variant_id, as_of), as_of)

    def iter_resolved(self, as_of: str) -> Iterator[ResolvedVehicle]:
        for variant_id in self.variants:
            yield self.resolve(variant_id, as_of)

    # ------------------------------------------------------------ validate
    def validate(self, as_of: str = "2025-12-31") -> list[str]:
        problems: list[str] = []
        for model in self.models.values():
            if model.body_type is BodyType.OTHER:
                problems.append(f"model {model.id}: body_type not set")
        for variant in self.variants.values():
            problems += variant.validate()
            if not self.periods.get(variant.id):
                problems.append(f"variant {variant.id}: no price period")
        for periods in self.periods.values():
            previous: Optional[VariantPeriod] = None
            for period in periods:
                problems += period.validate()
                if previous is not None and previous.end is None:
                    problems.append(
                        f"period {period.variant_id}: {previous.start} is open-ended "
                        f"but {period.start} follows it")
                elif previous is not None and period.start < (previous.end or ""):
                    problems.append(
                        f"period {period.variant_id}: {previous.start} overlaps "
                        f"{period.start}")
                previous = period
        for resolved in self.iter_resolved(as_of):
            problems += cross_check(resolved)
        return problems

    def coverage(self) -> dict[str, int]:
        return {
            "brands": len(self.brands),
            "models": len(self.models),
            "generations": len(self.generations),
            "variants": len(self.variants),
            "periods": sum(len(p) for p in self.periods.values()),
        }

    # ------------------------------------------------------------- writing
    def brand_payload(self, brand_id: str) -> dict:
        """Round-trip a brand back to the on-disk JSON shape."""
        brand = self.brands[brand_id]
        payload: dict[str, Any] = {
            "brand": {
                "id": brand.id, "name_en": brand.name_en, "name_th": brand.name_th,
                "brand_segment": brand.brand_segment.value,
                "oem_group": brand.oem_group, "brand_origin": brand.brand_origin,
                "aliases": list(brand.aliases),
            },
            "models": [],
        }
        for model in self.models_of(brand_id):
            model_payload: dict[str, Any] = {
                "id": model.id.split(".", 1)[1], "name_en": model.name_en,
                "name_th": model.name_th, "body_type": model.body_type.value,
                "cab_type": model.cab_type.value,
                "registration_type": model.registration_type.value,
                "aliases": list(model.aliases), "generations": [],
            }
            for gen in self.generations.values():
                if gen.model_id != model.id:
                    continue
                gen_payload: dict[str, Any] = {
                    "code": gen.code, "segment": gen.segment.value,
                    "seats": gen.seats, "launched": gen.launched,
                    "ended": gen.ended, "variants": [],
                }
                for variant in self.variants.values():
                    if variant.generation_id != gen.id:
                        continue
                    gen_payload["variants"].append({
                        "name": variant.name,
                        "powertrain": variant.powertrain.value,
                        "drivetrain": variant.drivetrain.value,
                        "engine_cc": variant.engine_cc,
                        "battery_kwh": variant.battery_kwh,
                        "cab_type": variant.cab_type.value,
                        "aliases": list(variant.aliases),
                        "periods": [
                            {"start": p.start, "end": p.end,
                             "price_thb": p.price_thb,
                             "import_type": p.import_type.value,
                             "origin_country": p.origin_country,
                             "model_year": p.model_year}
                            for p in self.periods.get(variant.id, [])
                        ],
                    })
                model_payload["generations"].append(gen_payload)
            payload["models"].append(model_payload)
        return payload

    def save_brand(self, brand_id: str, data_dir: Path | str = DATA_DIR) -> Path:
        path = Path(data_dir) / "models" / f"{brand_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.brand_payload(brand_id), ensure_ascii=False, indent=2)
            + "\n", encoding="utf-8")
        return path
