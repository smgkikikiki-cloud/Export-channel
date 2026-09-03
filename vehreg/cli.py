"""Command line for the registration warehouse.

    python -m vehreg init
    python -m vehreg ingest data/raw/dlt_2023_2025.csv --wide
    python -m vehreg cube --by segment,powertrain --from 2023-01 --to 2025-12
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Optional

from . import allocate as allocate_mod, authoring, cube as cube_mod
from .catalog import DATA_DIR, Catalog, CatalogError
from .db import connect, rebuild_dimension, unmatched_summary
from .ingest import ColumnMap, ingest_csv, teach_alias
from .taxonomy import (
    BodyType, BrandSegment, CabType, Drivetrain, ImportType, MarketPosition,
    Powertrain, PowertrainGroup, RegistrationType, Segment, THAI_LABELS,
    PRICE_BAND_EDGES,
)

DEFAULT_DB = Path("data/vehreg.sqlite3")


def _catalog(args) -> Catalog:
    return Catalog.load(args.data_dir)


def _conn(args):
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    return connect(args.db)


def _parse_filters(raw: list[str]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for item in raw or []:
        if "=" not in item:
            raise SystemExit(f"--filter expects key=value, got {item!r}")
        key, _, value = item.partition("=")
        values = [v for v in value.split(",") if v]
        filters[key.strip()] = values if len(values) > 1 else (
            values[0] if values else "")
    return filters


def _write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames,
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# --------------------------------------------------------------------- verbs
def cmd_facets(args) -> int:
    groups = [
        ("Segment", Segment), ("BodyType", BodyType), ("CabType", CabType),
        ("MarketPosition", MarketPosition), ("Powertrain", Powertrain),
        ("PowertrainGroup", PowertrainGroup), ("ImportType", ImportType),
        ("BrandSegment", BrandSegment), ("Drivetrain", Drivetrain),
        ("RegistrationType", RegistrationType),
    ]
    for name, enum_cls in groups:
        print(f"\n{name}")
        for member in enum_cls:
            print(f"  {member.value:<16} {THAI_LABELS[name].get(member.value, '')}")
    print("\nPrice bands (THB, upper bound exclusive)")
    previous = 0
    for edge, band in PRICE_BAND_EDGES:
        print(f"  {band.value:<16} {previous:>10,} - {edge - 1:>10,}")
        previous = edge
    print(f"  LUXURY           {previous:>10,} +")
    return 0


def cmd_init(args) -> int:
    catalog = _catalog(args)
    problems = catalog.validate()
    if problems and not args.force:
        print(f"catalog has {len(problems)} problems; fix them or pass --force")
        for problem in problems[:20]:
            print(f"  - {problem}")
        return 1
    conn = _conn(args)
    rows = rebuild_dimension(conn, catalog)
    print(f"catalog: {catalog.coverage()}")
    print(f"dimension rows: {rows}")
    print(f"database: {args.db}")
    return 0


def cmd_catalog(args) -> int:
    if args.catalog_cmd == "template":
        print(f"wrote {authoring.template(args.path)}")
        return 0
    if args.catalog_cmd == "import":
        applied, problems, written = authoring.import_csv(
            args.path, args.data_dir, dry_run=args.dry_run)
        print(f"rows applied: {applied}")
        for problem in problems[:40]:
            print(f"  - {problem}")
        if len(problems) > 40:
            print(f"  ... {len(problems) - 40} more")
        if args.dry_run:
            print("dry run: nothing written")
        else:
            for path in written:
                print(f"wrote {path}")
        return 1 if any(p.startswith("line ") for p in problems) else 0

    catalog = _catalog(args)
    if args.catalog_cmd == "stats":
        for key, value in catalog.coverage().items():
            print(f"{key:<12} {value}")
        return 0
    if args.catalog_cmd == "validate":
        problems = catalog.validate()
        for problem in problems:
            print(f"  - {problem}")
        print(f"{len(problems)} problems")
        return 1 if problems else 0
    if args.catalog_cmd == "audit":
        unverified = [
            (vid, p) for vid, periods in catalog.periods.items()
            for p in periods
            if p.price_thb is None or "unverified" in (p.price_note or "")
        ]
        for vid, period in unverified[:args.limit]:
            print(f"  {vid} @{period.start} price={period.price_thb} "
                  f"({period.price_note or 'no note'})")
        print(f"{len(unverified)} periods still need an owner-confirmed price")
        return 0
    if args.catalog_cmd == "export":
        count = authoring.export_csv(catalog, args.path)
        print(f"wrote {count} rows to {args.path}")
        return 0
    if args.catalog_cmd == "show":
        as_of = args.as_of
        matches = [vid for vid in catalog.variants if args.query.lower() in vid]
        if not matches:
            print(f"no variant id contains {args.query!r}")
            return 1
        for vid in matches[:args.limit]:
            resolved = catalog.resolve(vid, as_of)
            print(f"\n{vid}  (as of {as_of})")
            for key, value in resolved.as_row().items():
                if key in {"variant_id", "as_of"}:
                    continue
                origin = resolved.provenance.get(key, "-")
                print(f"  {key:<22} {str(value):<28} <- {origin}")
        return 0
    return 1


def cmd_ingest(args) -> int:
    catalog = _catalog(args)
    conn = _conn(args)
    if not conn.execute("SELECT 1 FROM dim_unit LIMIT 1").fetchone():
        rebuild_dimension(conn, catalog)
    colmap = ColumnMap(period=args.col_period, brand=args.col_brand,
                       model=args.col_model, variant=args.col_variant,
                       units=args.col_units, province=args.col_province,
                       registration_type=args.col_regtype)
    if not any(vars(colmap).values()):
        colmap = None
    report = ingest_csv(conn, catalog, args.path, args.source, wide=args.wide,
                        colmap=colmap,
                        default_registration_type=args.registration_type,
                        url=args.url, notes=args.notes)
    print(report.render())
    return 0


def cmd_review(args) -> int:
    conn = _conn(args)
    if args.map:
        scope, _, rest = args.map.partition(":")
        raw, _, target = rest.rpartition("=")
        if not (scope and raw and target):
            raise SystemExit("--map expects scope:raw label=target_id")
        teach_alias(conn, scope, raw, target)
        print(f"taught {scope}: {raw!r} -> {target}")
        return 0
    print("open review rows by reason:")
    for row in unmatched_summary(conn):
        print(f"  {row['reason']:<20} rows={row['rows']:<6} "
              f"units={(row['units'] or 0):,.0f}")
    print("\ntop unmatched labels:")
    for row in conn.execute(
            "SELECT raw_label, reason, SUM(units) AS units, COUNT(*) AS n "
            "FROM ingest_review WHERE status='open' GROUP BY raw_label, reason "
            "ORDER BY units DESC LIMIT ?", (args.limit,)):
        print(f"  {(row['raw_label'] or '')[:44]:<46} {row['reason']:<18} "
              f"{(row['units'] or 0):,.0f}")
    return 0


def cmd_cube(args) -> int:
    conn = _conn(args)
    result = cube_mod.run(
        conn, [d.strip() for d in args.by.split(",") if d.strip()],
        filters=_parse_filters(args.filter), period_from=getattr(args, "from"),
        period_to=args.to, grains=args.grain, allocate=args.allocate,
        limit=args.limit)
    if args.json:
        print(json.dumps(result.rows, ensure_ascii=False, indent=2))
    elif args.csv:
        _write_csv(args.csv, result.dimensions + ["units", "share"], result.rows)
        print(f"wrote {len(result.rows)} rows to {args.csv}")
    else:
        print(result.render(limit=args.limit or 40))
    return 0


def cmd_growth(args) -> int:
    conn = _conn(args)
    rows = cube_mod.growth(conn, args.by, base=args.base, compare=args.compare,
                           filters=_parse_filters(args.filter),
                           allocate=args.allocate)
    header = f"{args.by:<26} {args.base:>12} {args.compare:>12} {'chg':>10} " \
             f"{'growth':>9} {'share pp':>9}"
    print(header)
    print("-" * len(header))
    for row in rows[:args.limit]:
        growth_pct = "n/a" if row["growth"] is None else f"{row['growth']:.1%}"
        print(f"{str(row[args.by])[:26]:<26} {row['units_base']:>12,.0f} "
              f"{row['units_compare']:>12,.0f} {row['units_change']:>10,.0f} "
              f"{growth_pct:>9} {row['share_change_pp']:>+9.2f}")
    return 0


def cmd_allocate(args) -> int:
    conn = _conn(args)
    covered, total = allocate_mod.derive_weights(conn, fallback=args.fallback)
    print(f"model-periods with a derived trim mix: {covered} / {total}")
    bad = allocate_mod.weight_health(conn)
    if bad:
        print(f"warning: {len(bad)} model-periods do not sum to 1.0")
    print("run `cube --allocate` to split model-grain volume with these weights")
    return 0


def cmd_coverage(args) -> int:
    conn = _conn(args)
    report = cube_mod.coverage_report(conn)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


# --------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vehreg",
        description="Thai new-vehicle registration intelligence warehouse")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("facets", help="print every facet vocabulary")
    p.set_defaults(func=cmd_facets)

    p = sub.add_parser("init", help="validate the catalog and build the warehouse")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("catalog", help="inspect or edit the catalog")
    csub = p.add_subparsers(dest="catalog_cmd", required=True)
    csub.add_parser("stats").set_defaults(func=cmd_catalog)
    csub.add_parser("validate").set_defaults(func=cmd_catalog)
    c = csub.add_parser("audit", help="periods with no owner-confirmed price")
    c.add_argument("--limit", type=int, default=30)
    c.set_defaults(func=cmd_catalog)
    c = csub.add_parser("show", help="resolve one variant and show provenance")
    c.add_argument("query")
    c.add_argument("--as-of", default="2025-06-15")
    c.add_argument("--limit", type=int, default=5)
    c.set_defaults(func=cmd_catalog)
    c = csub.add_parser("template", help="write a blank authoring CSV")
    c.add_argument("path")
    c.set_defaults(func=cmd_catalog)
    c = csub.add_parser("import", help="merge an authoring CSV into the catalog")
    c.add_argument("path")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=cmd_catalog)
    c = csub.add_parser("export", help="flatten the catalog to CSV")
    c.add_argument("path")
    c.set_defaults(func=cmd_catalog)

    p = sub.add_parser("ingest", help="load a DLT export")
    p.add_argument("path")
    p.add_argument("--source", help="name for this source (defaults to filename)")
    p.add_argument("--wide", action="store_true",
                   help="months are columns rather than rows")
    p.add_argument("--registration-type", default="RY1")
    p.add_argument("--url", default="")
    p.add_argument("--notes", default="")
    for name in ("period", "brand", "model", "variant", "units", "province"):
        p.add_argument(f"--col-{name}", dest=f"col_{name}")
    p.add_argument("--col-regtype", dest="col_regtype")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("review", help="see and resolve unmatched labels")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--map", help="scope:raw label=target_id")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("cube", help="cross-tab any facets")
    p.add_argument("--by", required=True, help="comma-separated facets")
    p.add_argument("--from", dest="from", help="YYYY-MM")
    p.add_argument("--to", help="YYYY-MM")
    p.add_argument("--filter", action="append", default=[],
                   help="facet=value[,value]")
    p.add_argument("--grain", action="append",
                   choices=["BRAND", "MODEL", "VARIANT"])
    p.add_argument("--allocate", action="store_true",
                   help="split model-grain volume with the loaded weights")
    p.add_argument("--limit", type=int)
    p.add_argument("--csv")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cube)

    p = sub.add_parser("growth", help="compare two periods on one facet")
    p.add_argument("--by", required=True)
    p.add_argument("--base", required=True, help="YYYY or YYYY-MM")
    p.add_argument("--compare", required=True)
    p.add_argument("--filter", action="append", default=[])
    p.add_argument("--allocate", action="store_true")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_growth)

    p = sub.add_parser("allocate",
                       help="derive a trim mix from the trim-level rows present")
    p.add_argument("--fallback", choices=list(allocate_mod.FALLBACKS),
                   default="year")
    p.set_defaults(func=cmd_allocate)

    p = sub.add_parser("coverage", help="how much volume is classified how deeply")
    p.set_defaults(func=cmd_coverage)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (CatalogError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
