"""SQLite warehouse: a type-2 dimension over the catalog plus a fact table.

The dimension is rebuilt from the catalog, never hand-edited. Because prices and
import routes are dated, a variant produces one dimension row per stretch of
months during which its classification was constant. A March-2023 registration
therefore joins the March-2023 price band, not today's.

DLT does not always publish down to the trim. A fact row records the grain it
actually arrived at - ``BRAND``, ``MODEL`` or ``VARIANT`` - and joins a
dimension row of the same grain. Where a model spans several powertrains, the
model-grain row reports ``MIXED`` for that facet rather than picking one; the
cube can then either show MIXED honestly or split it with an allocation
profile.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence

from .catalog import Catalog
from .taxonomy import Grain

MIXED = "MIXED"

#: Facet columns materialised on every dimension row.
DIM_FACETS: tuple[str, ...] = (
    "brand", "model", "variant", "generation", "segment", "body_type",
    "cab_type", "market_position", "powertrain", "powertrain_group",
    "origin_country", "import_type", "brand_segment", "oem_group",
    "brand_origin", "drivetrain", "registration_type",
)
DIM_NUMERIC: tuple[str, ...] = ("price_thb", "seats", "engine_cc", "battery_kwh")
DIM_FLAGS: tuple[str, ...] = ("is_electrified", "is_plug_in", "is_locally_assembled")

SCHEMA = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_unit (
    unit_id        TEXT NOT NULL,
    grain          TEXT NOT NULL,
    valid_from     TEXT NOT NULL,           -- inclusive 'YYYY-MM'
    valid_to       TEXT,                    -- exclusive 'YYYY-MM', NULL = open
    lifecycle_from TEXT,                    -- real first month on sale
    {", ".join(f"{c} TEXT" for c in DIM_FACETS)},
    {", ".join(f"{c} REAL" for c in DIM_NUMERIC)},
    {", ".join(f"{c} INTEGER" for c in DIM_FLAGS)},
    PRIMARY KEY (unit_id, valid_from)
);
CREATE INDEX IF NOT EXISTS ix_dim_unit_grain ON dim_unit(grain, valid_from);

CREATE TABLE IF NOT EXISTS dim_source (
    source_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    publisher   TEXT,
    url         TEXT,
    file_name   TEXT,
    file_sha256 TEXT,
    fetched_at  TEXT,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS fact_registration (
    fact_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    period            TEXT NOT NULL,         -- 'YYYY-MM'
    registration_type TEXT NOT NULL,
    province          TEXT NOT NULL DEFAULT 'ALL',
    unit_id           TEXT NOT NULL,
    grain             TEXT NOT NULL,
    units             REAL NOT NULL,
    source_id         INTEGER NOT NULL REFERENCES dim_source(source_id),
    raw_label         TEXT,
    match_how         TEXT,
    match_score       REAL,
    UNIQUE (period, registration_type, province, unit_id, source_id, raw_label)
);
CREATE INDEX IF NOT EXISTS ix_fact_period ON fact_registration(period);
CREATE INDEX IF NOT EXISTS ix_fact_unit ON fact_registration(unit_id, period);

-- Raw labels the owner has taught the matcher. Applied before fuzzy matching.
CREATE TABLE IF NOT EXISTS alias_override (
    scope     TEXT NOT NULL,                -- 'brand' | 'model' | 'variant'
    raw       TEXT NOT NULL,
    target_id TEXT NOT NULL,
    added_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (scope, raw)
);

-- Anything the ingest refused to guess at. Never dropped, never auto-resolved.
CREATE TABLE IF NOT EXISTS ingest_review (
    review_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id  INTEGER NOT NULL REFERENCES dim_source(source_id),
    period     TEXT,
    raw_brand  TEXT,
    raw_model  TEXT,
    raw_label  TEXT,
    units      REAL,
    reason     TEXT NOT NULL,
    best_guess TEXT,
    score      REAL,
    status     TEXT NOT NULL DEFAULT 'open'  -- open | mapped | ignored
);

-- Optional variant mix used to split a model-grain fact. Weights per model and
-- month; rows produced this way are flagged estimated in the cube.
CREATE TABLE IF NOT EXISTS allocation_weight (
    model_id  TEXT NOT NULL,
    period    TEXT NOT NULL,
    unit_id   TEXT NOT NULL,
    weight    REAL NOT NULL,
    PRIMARY KEY (model_id, period, unit_id)
);

CREATE VIEW IF NOT EXISTS fact_classified AS
SELECT f.fact_id, f.period, f.registration_type AS fact_registration_type,
       f.province, f.grain, f.units, f.raw_label, f.source_id,
       f.match_how, f.match_score,
       d.unit_id, d.lifecycle_from,
       {", ".join(f"d.{c}" for c in DIM_FACETS)},
       {", ".join(f"d.{c}" for c in DIM_NUMERIC)},
       {", ".join(f"d.{c}" for c in DIM_FLAGS)}
FROM fact_registration f
LEFT JOIN dim_unit d
       ON d.unit_id = f.unit_id
      AND d.grain = f.grain
      AND f.period >= d.valid_from
      AND (d.valid_to IS NULL OR f.period < d.valid_to);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# --------------------------------------------------------------------------
# Dimension build
# --------------------------------------------------------------------------
def _month(iso_date: Optional[str]) -> Optional[str]:
    return iso_date[:7] if iso_date else None


def _consensus(values: Sequence[Any]) -> Any:
    kept = [v for v in values if v is not None]
    if not kept:
        return None
    first = kept[0]
    return first if all(v == first for v in kept) else MIXED


def _flat(resolved) -> dict[str, Any]:
    row = resolved.as_row()
    return {c: row.get(c) for c in DIM_FACETS + DIM_NUMERIC + DIM_FLAGS}


def _active_variants(catalog: Catalog, model_id: str, month: str) -> list[str]:
    out = []
    for variant in catalog.variants_of(model_id):
        gen = catalog.generations[variant.generation_id]
        start = _month(gen.launched) or "0000-00"
        end = _month(gen.ended)
        if month >= start and (end is None or month < end):
            out.append(variant.id)
    return out


def _change_months(catalog: Catalog, variant_ids: Iterable[str]) -> list[str]:
    months: set[str] = set()
    for vid in variant_ids:
        gen = catalog.generation_for_variant(vid)
        for value in (gen.launched, gen.ended):
            if value:
                months.add(value[:7])
        for period in catalog.periods.get(vid, []):
            months.add(period.start[:7])
            if period.end:
                months.add(period.end[:7])
    return sorted(m for m in months if m)


#: Lower sentinel for the first dimension row of any unit. A fact dated before
#: a car's first known month still has to join *something* - otherwise it would
#: silently drop out of every cross-tab - so the earliest classification is
#: extended backwards. ``lifecycle_from`` keeps the real date for anyone who
#: wants to spot pre-launch rows as the data-quality signal they are.
OPEN_START = "0000-00"


def _collapse(rows: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Merge consecutive months whose facets are identical into one SCD row."""
    out: list[dict[str, Any]] = []
    for month, facets in rows:
        if out and all(out[-1].get(k) == v for k, v in facets.items()):
            continue
        if out:
            out[-1]["valid_to"] = month
        row = dict(facets)
        row["valid_from"] = month
        row["valid_to"] = None
        out.append(row)
    if out:
        out[0]["lifecycle_from"] = out[0]["valid_from"]
        out[0]["valid_from"] = OPEN_START
    for row in out[1:]:
        row["lifecycle_from"] = out[0]["lifecycle_from"]
    return out


def build_dimension(catalog: Catalog) -> list[dict[str, Any]]:
    """Materialise variant-, model- and brand-grain dimension rows."""
    rows: list[dict[str, Any]] = []

    for variant_id in catalog.variants:
        months = _change_months(catalog, [variant_id]) or ["1900-01"]
        snapshots = [(m, _flat(catalog.resolve(variant_id, f"{m}-15")))
                     for m in months]
        for row in _collapse(snapshots):
            row.update(unit_id=variant_id, grain=Grain.VARIANT.value)
            rows.append(row)

    for model_id, model in catalog.models.items():
        variant_ids = [v.id for v in catalog.variants_of(model_id)]
        months = _change_months(catalog, variant_ids) or ["1900-01"]
        snapshots = []
        for month in months:
            active = _active_variants(catalog, model_id, month) or variant_ids
            flats = [_flat(catalog.resolve(vid, f"{month}-15")) for vid in active]
            merged = {c: _consensus([f[c] for f in flats])
                      for c in DIM_FACETS + DIM_NUMERIC + DIM_FLAGS}
            merged["variant"] = None          # a model row has no single trim
            merged["generation"] = _consensus([f["generation"] for f in flats])
            snapshots.append((month, merged))
        for row in _collapse(snapshots):
            row.update(unit_id=model_id, grain=Grain.MODEL.value)
            rows.append(row)

    for brand_id, brand in catalog.brands.items():
        variant_ids = [v.id for m in catalog.models_of(brand_id)
                       for v in catalog.variants_of(m.id)]
        months = _change_months(catalog, variant_ids) or ["1900-01"]
        snapshots = []
        for month in months:
            flats = [_flat(catalog.resolve(vid, f"{month}-15")) for vid in variant_ids]
            merged = {c: _consensus([f[c] for f in flats])
                      for c in DIM_FACETS + DIM_NUMERIC + DIM_FLAGS}
            merged["variant"] = None
            merged["model"] = None
            merged["generation"] = None
            merged["brand"] = brand.name_en
            merged["brand_segment"] = brand.brand_segment.value
            merged["oem_group"] = brand.oem_group
            snapshots.append((month, merged))
        for row in _collapse(snapshots):
            row.update(unit_id=brand_id, grain=Grain.BRAND.value)
            rows.append(row)

    return rows


DIM_COLUMNS: tuple[str, ...] = (
    ("unit_id", "grain", "valid_from", "valid_to", "lifecycle_from")
    + DIM_FACETS + DIM_NUMERIC + DIM_FLAGS
)


def rebuild_dimension(conn: sqlite3.Connection, catalog: Catalog) -> int:
    rows = build_dimension(catalog)
    placeholders = ", ".join("?" for _ in DIM_COLUMNS)
    with conn:
        conn.execute("DELETE FROM dim_unit")
        conn.executemany(
            f"INSERT INTO dim_unit ({', '.join(DIM_COLUMNS)}) "
            f"VALUES ({placeholders})",
            [tuple(row.get(c) for c in DIM_COLUMNS) for row in rows],
        )
    return len(rows)


def register_source(conn: sqlite3.Connection, name: str, **fields: Any) -> int:
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO dim_source (name, publisher, url, file_name, "
            "file_sha256, fetched_at, notes) VALUES (?,?,?,?,?,?,?)",
            (name, fields.get("publisher"), fields.get("url"),
             fields.get("file_name"), fields.get("file_sha256"),
             fields.get("fetched_at"), fields.get("notes")),
        )
    row = conn.execute("SELECT source_id FROM dim_source WHERE name = ?",
                       (name,)).fetchone()
    return int(row["source_id"])


def unmatched_summary(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT reason, COUNT(*) AS rows, SUM(units) AS units "
        "FROM ingest_review WHERE status = 'open' GROUP BY reason "
        "ORDER BY units DESC"
    ).fetchall()
