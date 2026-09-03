"""The five identity layers and the facet-resolution chain.

    Brand  ->  Model  ->  Generation  ->  Variant  ->  VariantPeriod(date)

Each layer declares only the facets that are genuinely constant at that layer.
A lower layer may override anything a higher layer said. ``resolve()`` walks the
chain from the most specific layer outwards, takes the first non-empty value,
and records which layer supplied it, so any number in a report can be traced
back to the row that asserted it.

Why the layers exist:

* ``Brand``       - brand_segment, oem_group, brand origin. One row per marque.
* ``Model``       - the nameplate. Body type lives here (a Yaris is a hatch).
* ``Generation``  - the "โฉม". Segment and seat count can move between
                    generations; a facelift that repositions a car is a new
                    generation row, not an edit of history.
* ``Variant``     - the รุ่นย่อย. Powertrain, drivetrain, engine, battery.
* ``VariantPeriod`` - everything that moves while the trim is on sale: list
                    price (hence market position), import route, assembly
                    country, model year. Dated, so a 2023 fact is classified
                    with the 2023 price and a 2025 fact with the 2025 price.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Iterator, Optional

from .taxonomy import (
    BodyType, BrandSegment, CabType, Drivetrain, ImportType, MarketPosition,
    Powertrain, PowertrainGroup, RegistrationType, Segment,
    check_body_segment, check_origin, check_powertrain, is_electrified,
    is_locally_assembled, is_plug_in, market_position_for_price,
    normalize_country, powertrain_group,
)

#: Facet -> the layer that normally owns it. Used only for validation messages
#: and for the "where should I put this?" hint in the CLI; resolution itself is
#: driven by the chain order below, so an override at any layer still works.
FACET_HOME_LAYER: dict[str, str] = {
    "brand_segment": "brand",
    "oem_group": "brand",
    "brand_origin": "brand",
    "body_type": "model",
    "cab_type": "variant",
    "registration_type": "model",
    "segment": "generation",
    "seats": "generation",
    "powertrain": "variant",
    "drivetrain": "variant",
    "engine_cc": "variant",
    "battery_kwh": "variant",
    "price_thb": "period",
    "import_type": "period",
    "origin_country": "period",
    "model_year": "period",
}

#: Most specific first. This is the whole override mechanism.
RESOLUTION_CHAIN: tuple[str, ...] = ("period", "variant", "generation", "model", "brand")

_UNSET = (None, "", "UNKNOWN")


def _is_set(value: Any) -> bool:
    if value in _UNSET:
        return False
    if hasattr(value, "value") and value.value == "UNKNOWN":
        return False
    return True


@dataclass(frozen=True, slots=True)
class Brand:
    id: str                                   # stable slug, e.g. "toyota"
    name_en: str
    name_th: str
    brand_segment: BrandSegment = BrandSegment.UNKNOWN
    oem_group: str = "UNKNOWN"                # e.g. "Toyota Group", "Geely"
    brand_origin: str = "UNKNOWN"             # ISO-2 of the marque's home market
    aliases: tuple[str, ...] = ()
    overrides: dict[str, Any] = field(default_factory=dict)

    def facets(self) -> dict[str, Any]:
        out = {
            "brand": self.name_en,
            "brand_segment": self.brand_segment,
            "oem_group": self.oem_group,
            "brand_origin": normalize_country(self.brand_origin),
        }
        out.update(self.overrides)
        return out


@dataclass(frozen=True, slots=True)
class Model:
    id: str                                   # "toyota.yaris_ativ"
    brand_id: str
    name_en: str
    name_th: str = ""
    body_type: BodyType = BodyType.OTHER
    cab_type: CabType = CabType.NOT_APPLICABLE
    registration_type: RegistrationType = RegistrationType.RY1
    aliases: tuple[str, ...] = ()
    notes: str = ""
    overrides: dict[str, Any] = field(default_factory=dict)

    def facets(self) -> dict[str, Any]:
        out = {
            "model": self.name_en,
            "body_type": self.body_type,
            "cab_type": self.cab_type,
            "registration_type": self.registration_type,
        }
        out.update(self.overrides)
        return out


@dataclass(frozen=True, slots=True)
class Generation:
    id: str                                   # "toyota.yaris_ativ.2022"
    model_id: str
    code: str = ""                            # factory code, e.g. "MXPA10"
    segment: Segment = Segment.UNKNOWN
    seats: Optional[int] = None
    launched: Optional[str] = None            # ISO date, first Thai sale
    ended: Optional[str] = None
    overrides: dict[str, Any] = field(default_factory=dict)

    def facets(self) -> dict[str, Any]:
        out: dict[str, Any] = {"generation": self.code or self.id.rsplit(".", 1)[-1],
                               "segment": self.segment}
        if self.seats:
            out["seats"] = self.seats
        out.update(self.overrides)
        return out


@dataclass(frozen=True, slots=True)
class Variant:
    id: str                                   # "toyota.yaris_ativ.2022.smart"
    generation_id: str
    name: str                                 # trim as marketed, e.g. "1.2 Smart"
    powertrain: Powertrain = Powertrain.UNKNOWN
    drivetrain: Drivetrain = Drivetrain.UNKNOWN
    engine_cc: Optional[int] = None
    battery_kwh: Optional[float] = None
    cab_type: CabType = CabType.NOT_APPLICABLE
    aliases: tuple[str, ...] = ()
    overrides: dict[str, Any] = field(default_factory=dict)

    def facets(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "variant": self.name,
            "powertrain": self.powertrain,
            "drivetrain": self.drivetrain,
        }
        if self.cab_type is not CabType.NOT_APPLICABLE:
            out["cab_type"] = self.cab_type
        if self.engine_cc:
            out["engine_cc"] = self.engine_cc
        if self.battery_kwh:
            out["battery_kwh"] = self.battery_kwh
        out.update(self.overrides)
        return out

    def validate(self) -> list[str]:
        return [f"variant {self.id}: {p}"
                for p in check_powertrain(self.powertrain, self.battery_kwh,
                                          self.engine_cc)]


@dataclass(frozen=True, slots=True)
class VariantPeriod:
    """Dated commercial facts for one trim. Half-open interval [start, end)."""

    variant_id: str
    start: str                                # ISO date, inclusive
    end: Optional[str] = None                 # ISO date, exclusive; None = current
    price_thb: Optional[float] = None
    import_type: ImportType = ImportType.UNKNOWN
    origin_country: str = "UNKNOWN"
    model_year: Optional[int] = None
    price_note: str = ""
    overrides: dict[str, Any] = field(default_factory=dict)

    def covers(self, when: str) -> bool:
        if when < self.start:
            return False
        return self.end is None or when < self.end

    def facets(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "price_thb": self.price_thb,
            "market_position": market_position_for_price(self.price_thb),
            "import_type": self.import_type,
            "origin_country": normalize_country(self.origin_country),
        }
        if self.model_year:
            out["model_year"] = self.model_year
        out.update(self.overrides)
        return out

    def validate(self) -> list[str]:
        problems = [f"period {self.variant_id}@{self.start}: {p}"
                    for p in check_origin(self.import_type, self.origin_country)]
        if self.end is not None and self.end <= self.start:
            problems.append(f"period {self.variant_id}@{self.start}: end <= start")
        return problems


@dataclass(frozen=True, slots=True)
class ResolvedVehicle:
    """One fully cross-classified row: every facet plus where it came from."""

    variant_id: str
    as_of: str
    facets: dict[str, Any]
    provenance: dict[str, str]

    def __getitem__(self, key: str) -> Any:
        return self.facets.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self.facets.get(key, default)

    def as_row(self) -> dict[str, Any]:
        row = {}
        for key, value in self.facets.items():
            row[key] = value.value if hasattr(value, "value") else value
        row["variant_id"] = self.variant_id
        row["as_of"] = self.as_of
        return row


def resolve(brand: Brand, model: Model, generation: Generation, variant: Variant,
            period: Optional[VariantPeriod], as_of: str) -> ResolvedVehicle:
    """Collapse the five layers into one classified row.

    The first layer in ``RESOLUTION_CHAIN`` that asserts a facet wins. Values
    that are ``None``/``""``/``UNKNOWN`` do not count as asserted, so a lower
    layer leaving a field blank falls through to the layer above instead of
    erasing it.
    """
    layers = {
        "period": period.facets() if period else {},
        "variant": variant.facets(),
        "generation": generation.facets(),
        "model": model.facets(),
        "brand": brand.facets(),
    }

    facets: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    for layer_name in RESOLUTION_CHAIN:
        for key, value in layers[layer_name].items():
            if key in facets:
                continue
            if _is_set(value):
                facets[key] = value
                provenance[key] = layer_name

    # Derived facets. They are computed, never stored, so they can never
    # disagree with the layer that produced their input.
    pt = facets.get("powertrain", Powertrain.UNKNOWN)
    facets["powertrain_group"] = powertrain_group(pt)
    facets["is_electrified"] = is_electrified(pt)
    facets["is_plug_in"] = is_plug_in(pt)
    facets.setdefault("market_position", MarketPosition.UNKNOWN)
    facets.setdefault("segment", Segment.UNKNOWN)
    facets.setdefault("body_type", BodyType.OTHER)
    facets.setdefault("cab_type", CabType.NOT_APPLICABLE)
    facets.setdefault("import_type", ImportType.UNKNOWN)
    facets.setdefault("origin_country", "UNKNOWN")
    facets["is_locally_assembled"] = is_locally_assembled(
        facets["import_type"], facets["origin_country"]
    )
    for derived in ("powertrain_group", "is_electrified", "is_plug_in",
                    "is_locally_assembled"):
        provenance[derived] = "derived"

    return ResolvedVehicle(variant.id, as_of, facets, provenance)


def cross_check(resolved: ResolvedVehicle) -> list[str]:
    """Rules that only make sense once the layers are combined."""
    f = resolved.facets
    body = BodyType.parse(f["body_type"])
    reg = RegistrationType.parse(f["registration_type"])
    problems = check_body_segment(body, f["cab_type"], f["segment"])
    problems += check_powertrain(f.get("powertrain", Powertrain.UNKNOWN),
                                 f.get("battery_kwh"), f.get("engine_cc"))
    problems += check_origin(f["import_type"], f["origin_country"])
    if body is BodyType.PICKUP and reg not in {RegistrationType.RY3,
                                               RegistrationType.OTHER}:
        problems.append(f"pickup is normally registered รย.3, not {reg.value}")
    return [f"{resolved.variant_id}@{resolved.as_of}: {p}" for p in problems]


def to_jsonable(obj: Any) -> Any:
    """dataclass -> plain JSON types, with enums flattened to their key."""
    if hasattr(obj, "value") and not isinstance(obj, (str, int, float)):
        return obj.value
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    return obj
