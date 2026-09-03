"""Offline tests for the registration warehouse. No network, no paid calls."""

import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from vehreg import allocate, authoring, cube, db, entities, normalize, taxonomy
from vehreg.catalog import Catalog, CatalogError
from vehreg.ingest import Resolver, ingest_csv, teach_alias
from vehreg.taxonomy import (
    BodyType, BrandSegment, CabType, Drivetrain, Grain, ImportType,
    MarketPosition, Powertrain, RegistrationType, Segment,
)

REPO = Path(__file__).resolve().parents[1]


def tiny_payload():
    return {
        "brand": {"id": "acme", "name_en": "Acme", "name_th": "แอคมี่",
                  "brand_segment": "MASS", "oem_group": "Acme Group",
                  "brand_origin": "TH", "aliases": ["แอคมี่"]},
        "models": [
            {"id": "runner", "name_en": "Runner", "name_th": "รันเนอร์",
             "body_type": "PICKUP", "registration_type": "RY3",
             "aliases": ["รันเนอร์"],
             "generations": [{
                 "code": "R1", "segment": "F", "seats": 5,
                 "launched": "2022-01-01",
                 "variants": [
                     {"name": "2.4 Base", "powertrain": "ICE", "drivetrain": "RWD",
                      "engine_cc": 2400, "cab_type": "SINGLE_CAB",
                      "periods": [{"start": "2022-01-01", "end": "2024-01-01",
                                   "price_thb": 480000, "import_type": "CKD",
                                   "origin_country": "TH"},
                                  {"start": "2024-01-01", "price_thb": 520000,
                                   "import_type": "CKD", "origin_country": "TH"}]},
                     {"name": "2.4 Double Cab 4x4", "powertrain": "ICE",
                      "drivetrain": "4WD", "engine_cc": 2400,
                      "cab_type": "DOUBLE_CAB",
                      "periods": [{"start": "2022-01-01", "price_thb": 1250000,
                                   "import_type": "CKD", "origin_country": "TH"}]},
                 ]}]},
            {"id": "volt", "name_en": "Volt", "name_th": "โวลต์",
             "body_type": "CROSSOVER",
             "generations": [{
                 "code": "V1", "segment": "B", "seats": 5,
                 "launched": "2023-03-01",
                 "variants": [
                     {"name": "EV Standard", "powertrain": "BEV",
                      "drivetrain": "FWD", "battery_kwh": 50.0,
                      "periods": [{"start": "2023-03-01", "end": "2024-06-01",
                                   "price_thb": 1050000, "import_type": "CBU",
                                   "origin_country": "CN"},
                                  {"start": "2024-06-01", "price_thb": 899000,
                                   "import_type": "CKD", "origin_country": "TH"}]},
                     {"name": "1.5 Petrol", "powertrain": "ICE",
                      "drivetrain": "FWD", "engine_cc": 1500,
                      "periods": [{"start": "2023-03-01", "price_thb": 749000,
                                   "import_type": "CKD", "origin_country": "TH"}]},
                 ]}]},
        ],
    }


def tiny_catalog():
    catalog = Catalog()
    catalog.add_brand_payload(tiny_payload(), source="<test>")
    catalog.build_indexes()
    return catalog


class TaxonomyTests(unittest.TestCase):
    def test_price_bands_are_contiguous_and_total(self):
        self.assertIs(taxonomy.market_position_for_price(0), MarketPosition.ENTRY)
        self.assertIs(taxonomy.market_position_for_price(499_999),
                      MarketPosition.ENTRY)
        self.assertIs(taxonomy.market_position_for_price(500_000),
                      MarketPosition.VOLUME)
        self.assertIs(taxonomy.market_position_for_price(999_999),
                      MarketPosition.VOLUME)
        self.assertIs(taxonomy.market_position_for_price(1_000_000),
                      MarketPosition.UPPER)
        # The brief's 1.8M-2.0M gap is closed rather than left unclassified.
        self.assertIs(taxonomy.market_position_for_price(1_900_000),
                      MarketPosition.LUXURY)
        self.assertIs(taxonomy.market_position_for_price(None),
                      MarketPosition.UNKNOWN)

    def test_powertrain_rollups(self):
        self.assertIs(taxonomy.powertrain_group(Powertrain.REEV),
                      taxonomy.PowertrainGroup.HYBRID)
        self.assertIs(taxonomy.powertrain_group(Powertrain.MHEV),
                      taxonomy.PowertrainGroup.COMBUSTION)
        self.assertTrue(taxonomy.is_plug_in(Powertrain.PHEV))
        self.assertFalse(taxonomy.is_plug_in(Powertrain.HEV))
        self.assertTrue(taxonomy.is_electrified(Powertrain.MHEV))
        self.assertFalse(taxonomy.is_electrified(Powertrain.ICE))

    def test_facets_parse_common_aliases(self):
        self.assertIs(Powertrain.parse("ev"), Powertrain.BEV)
        self.assertIs(Powertrain.parse("Plug-in Hybrid"), Powertrain.PHEV)
        self.assertIs(BodyType.parse("body on frame suv"), BodyType.PPV)
        self.assertIs(CabType.parse("space cab"), CabType.SMART_CAB)
        self.assertIs(ImportType.parse("imported"), ImportType.CBU)
        self.assertIs(RegistrationType.parse("รย.3"), RegistrationType.RY3)
        with self.assertRaises(ValueError):
            Powertrain.parse("steam")

    def test_cross_facet_rules_reject_impossible_combinations(self):
        self.assertTrue(taxonomy.check_body_segment(
            BodyType.PICKUP, CabType.NOT_APPLICABLE, Segment.F))
        self.assertTrue(taxonomy.check_body_segment(
            BodyType.SEDAN, CabType.DOUBLE_CAB, Segment.C))
        self.assertTrue(taxonomy.check_body_segment(
            BodyType.SEDAN, CabType.NOT_APPLICABLE, Segment.F))
        self.assertFalse(taxonomy.check_body_segment(
            BodyType.PICKUP, CabType.DOUBLE_CAB, Segment.F))
        self.assertTrue(taxonomy.check_powertrain(Powertrain.BEV, 60.0, 1500))
        self.assertTrue(taxonomy.check_powertrain(Powertrain.PHEV, None, 1500))
        self.assertTrue(taxonomy.check_origin(ImportType.CKD, "CN"))
        self.assertFalse(taxonomy.check_origin(ImportType.CKD, "TH"))


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = tiny_catalog()

    def test_every_facet_resolves_with_provenance(self):
        resolved = self.catalog.resolve("acme.runner.r1.2_4_double_cab_4x4",
                                        "2023-05-01")
        self.assertEqual(resolved["brand"], "Acme")
        self.assertIs(resolved["segment"], Segment.F)
        self.assertIs(resolved["body_type"], BodyType.PICKUP)
        self.assertIs(resolved["cab_type"], CabType.DOUBLE_CAB)
        self.assertIs(resolved["market_position"], MarketPosition.UPPER)
        self.assertIs(resolved["import_type"], ImportType.CKD)
        self.assertIs(resolved["brand_segment"], BrandSegment.MASS)
        self.assertEqual(resolved.provenance["brand_segment"], "brand")
        self.assertEqual(resolved.provenance["body_type"], "model")
        self.assertEqual(resolved.provenance["segment"], "generation")
        self.assertEqual(resolved.provenance["cab_type"], "variant")
        self.assertEqual(resolved.provenance["market_position"], "period")
        self.assertEqual(resolved.provenance["powertrain_group"], "derived")

    def test_lower_layer_overrides_higher_layer(self):
        payload = tiny_payload()
        payload["models"][0]["generations"][0]["variants"][0]["overrides"] = {
            "brand_segment": "BUDGET"}
        catalog = Catalog()
        catalog.add_brand_payload(payload)
        catalog.build_indexes()
        resolved = catalog.resolve("acme.runner.r1.2_4_base", "2023-05-01")
        self.assertIs(resolved["brand_segment"], BrandSegment.BUDGET)
        self.assertEqual(resolved.provenance["brand_segment"], "variant")

    def test_classification_follows_the_dated_period(self):
        before = self.catalog.resolve("acme.volt.v1.ev_standard", "2024-01-15")
        after = self.catalog.resolve("acme.volt.v1.ev_standard", "2024-09-15")
        self.assertIs(before["market_position"], MarketPosition.UPPER)
        self.assertIs(before["import_type"], ImportType.CBU)
        self.assertEqual(before["origin_country"], "CN")
        self.assertIs(after["market_position"], MarketPosition.VOLUME)
        self.assertIs(after["import_type"], ImportType.CKD)
        self.assertEqual(after["origin_country"], "TH")
        self.assertFalse(before["is_locally_assembled"])
        self.assertTrue(after["is_locally_assembled"])

    def test_dates_outside_every_period_still_classify(self):
        early = self.catalog.resolve("acme.volt.v1.ev_standard", "2020-01-01")
        self.assertIs(early["import_type"], ImportType.CBU)

    def test_seeded_catalog_is_internally_consistent(self):
        catalog = Catalog.load()
        self.assertEqual(catalog.validate(), [])
        self.assertGreater(catalog.coverage()["models"], 100)

    def test_duplicate_ids_are_rejected(self):
        catalog = Catalog()
        catalog.add_brand_payload(tiny_payload())
        with self.assertRaises(CatalogError):
            catalog.add_brand_payload(tiny_payload())


class NormalisationTests(unittest.TestCase):
    def test_period_parsing_handles_thai_and_buddhist_era(self):
        self.assertEqual(normalize.period_key("2024-03"), "2024-03")
        self.assertEqual(normalize.period_key("มี.ค. 2567"), "2024-03")
        self.assertEqual(normalize.period_key("03/2567"), "2024-03")
        self.assertEqual(normalize.period_key("Mar 2024"), "2024-03")
        with self.assertRaises(ValueError):
            normalize.period_key("ไม่ระบุ")

    def test_longest_name_wins_over_a_shorter_prefix(self):
        index = normalize.MatchIndex()
        index.add("yaris", ["Yaris"])
        index.add("yaris_ativ", ["Yaris Ativ"])
        key, _, how = index.lookup("YARIS ATIV 1.2 SMART")
        self.assertEqual(key, "yaris_ativ")
        self.assertEqual(how, "contains")
        self.assertEqual(index.lookup("YARIS 1.2 PLAY")[0], "yaris")

    def test_ambiguous_labels_match_nothing(self):
        index = normalize.MatchIndex()
        index.add("a", ["Seal"])
        index.add("b", ["Seal"])
        self.assertEqual(index.lookup("Seal"), ("a", 1.0, "exact"))
        index2 = normalize.MatchIndex()
        index2.add("a", ["Alpha One"])
        index2.add("b", ["Beta One"])
        self.assertIsNone(index2.lookup("Gamma Two")[0])


class WarehouseTests(unittest.TestCase):
    def setUp(self):
        self.catalog = tiny_catalog()
        self.conn = db.connect(":memory:")
        db.rebuild_dimension(self.conn, self.catalog)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    def write_csv(self, rows, name="dlt.csv",
                  header=("เดือน", "ยี่ห้อ", "แบบรถ", "รุ่นย่อย", "จำนวน")):
        path = self.dir / name
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        return path

    def test_dimension_is_type_2_over_price_changes(self):
        rows = self.conn.execute(
            "SELECT valid_from, valid_to, market_position, import_type "
            "FROM dim_unit WHERE unit_id = 'acme.volt.v1.ev_standard' "
            "ORDER BY valid_from").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["valid_to"], "2024-06")
        self.assertEqual(rows[0]["market_position"], "UPPER")
        self.assertEqual(rows[1]["market_position"], "VOLUME")
        self.assertIsNone(rows[1]["valid_to"])

    def test_model_grain_row_reports_mixed_only_where_trims_disagree(self):
        row = self.conn.execute(
            "SELECT * FROM dim_unit WHERE unit_id = 'acme.volt' "
            "AND grain = 'MODEL' ORDER BY valid_from DESC LIMIT 1").fetchone()
        self.assertEqual(row["body_type"], "CROSSOVER")   # both trims agree
        self.assertEqual(row["segment"], "B")
        self.assertEqual(row["powertrain"], db.MIXED)     # BEV vs ICE

    def test_ingest_matches_and_preserves_totals(self):
        path = self.write_csv([
            ("2024-02", "Acme", "Runner", "2.4 Double Cab 4x4", "120"),
            ("2024-02", "แอคมี่", "รันเนอร์", "", "300"),
            ("ก.พ. 2567", "Acme", "Volt", "EV Standard", "80"),
            ("2024-02", "Nonexist", "Ghost", "", "45"),
        ])
        report = ingest_csv(self.conn, self.catalog, path, "test")
        self.assertEqual(report.rows_read, 4)
        self.assertEqual(report.units_matched, 500.0)
        self.assertEqual(report.units_review, 45.0)
        self.assertEqual(report.units_total, 545.0)
        self.assertEqual(report.by_grain["VARIANT"], 2)
        self.assertEqual(report.by_grain["MODEL"], 1)

    def test_reingesting_the_same_file_does_not_double_count(self):
        path = self.write_csv([("2024-02", "Acme", "Runner", "", "300")])
        ingest_csv(self.conn, self.catalog, path, "test")
        ingest_csv(self.conn, self.catalog, path, "test")
        total = self.conn.execute(
            "SELECT SUM(units) AS u FROM fact_registration").fetchone()["u"]
        self.assertEqual(total, 300.0)

    def test_unmatched_rows_are_queued_never_guessed(self):
        path = self.write_csv([("2024-02", "Nonexist", "Ghost", "", "45")])
        ingest_csv(self.conn, self.catalog, path, "test")
        rows = self.conn.execute(
            "SELECT raw_label, reason, units FROM ingest_review").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "brand-not-found")
        self.assertEqual(rows[0]["units"], 45.0)
        self.assertIsNone(self.conn.execute(
            "SELECT SUM(units) AS u FROM fact_registration").fetchone()["u"])

    def test_taught_alias_is_used_on_the_next_ingest(self):
        path = self.write_csv([("2024-02", "ACME MOTOR CO", "RNR", "", "60")])
        ingest_csv(self.conn, self.catalog, path, "first")
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) AS n FROM ingest_review").fetchone()["n"], 1)
        teach_alias(self.conn, "model", "ACME MOTOR CO RNR", "acme.runner")
        report = ingest_csv(self.conn, self.catalog, path, "second")
        self.assertEqual(report.units_matched, 60.0)
        self.assertEqual(report.by_grain["MODEL"], 1)

    def test_brand_scoping_stops_a_cross_brand_match(self):
        resolver = Resolver(self.catalog, self.conn)
        unit_id, grain, _, _, reason = resolver.resolve("Acme", "Volt")
        self.assertEqual(unit_id, "acme.volt")
        unit_id, grain, _, _, reason = resolver.resolve("Nonexist", "Volt")
        self.assertIsNone(unit_id)
        self.assertEqual(reason, "brand-not-found")

    def test_wide_layout_is_unpivoted(self):
        path = self.dir / "wide.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ยี่ห้อ", "แบบรถ", "ม.ค. 2567", "ก.พ. 2567"])
            writer.writerow(["Acme", "Runner", "100", "150"])
        report = ingest_csv(self.conn, self.catalog, path, "wide", wide=True)
        self.assertEqual(report.units_matched, 250.0)
        periods = [r["period"] for r in self.conn.execute(
            "SELECT DISTINCT period FROM fact_registration ORDER BY period")]
        self.assertEqual(periods, ["2024-01", "2024-02"])


class CubeTests(unittest.TestCase):
    def setUp(self):
        self.catalog = tiny_catalog()
        self.conn = db.connect(":memory:")
        db.rebuild_dimension(self.conn, self.catalog)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / "facts.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["เดือน", "ยี่ห้อ", "แบบรถ", "รุ่นย่อย", "จำนวน"])
            writer.writerows([
                ("2023-05", "Acme", "Runner", "2.4 Base", "300"),
                ("2023-05", "Acme", "Runner", "2.4 Double Cab 4x4", "100"),
                ("2023-05", "Acme", "Volt", "", "200"),
                ("2024-09", "Acme", "Runner", "2.4 Base", "400"),
                ("2024-09", "Acme", "Volt", "EV Standard", "150"),
                ("2024-09", "Acme", "Volt", "1.5 Petrol", "50"),
            ])
        ingest_csv(self.conn, self.catalog, path, "facts")

    def test_any_facet_crosses_any_other(self):
        result = cube.run(self.conn, ["body_type", "market_position"])
        self.assertEqual(result.total_units, 1200.0)
        keys = {(r["body_type"], r["market_position"]) for r in result.rows}
        self.assertIn(("PICKUP", "ENTRY"), keys)
        self.assertIn(("PICKUP", "UPPER"), keys)

    def test_price_band_follows_the_month_of_the_fact(self):
        early = cube.run(self.conn, ["market_position"],
                         filters={"variant": "2.4 Base"}, period_to="2023-12")
        late = cube.run(self.conn, ["market_position"],
                        filters={"variant": "2.4 Base"}, period_from="2024-01")
        self.assertEqual(early.rows[0]["market_position"], "ENTRY")
        self.assertEqual(late.rows[0]["market_position"], "VOLUME")

    def test_model_grain_volume_shows_as_mixed_not_as_a_guess(self):
        result = cube.run(self.conn, ["powertrain"], period_to="2023-12")
        mixed = [r for r in result.rows if r["powertrain"] == db.MIXED]
        self.assertEqual(mixed[0]["units"], 200.0)
        self.assertEqual(result.mixed_units, 200.0)

    def test_allocation_splits_mixed_and_conserves_the_total(self):
        allocate.derive_weights(self.conn, fallback="all")
        plain = cube.run(self.conn, ["powertrain"])
        split = cube.run(self.conn, ["powertrain"], allocate=True)
        self.assertAlmostEqual(plain.total_units, split.total_units)
        self.assertEqual(split.mixed_units, 0.0)
        self.assertGreater(split.estimated_units, 0.0)
        bev = next(r for r in split.rows if r["powertrain"] == "BEV")
        # 150 reported + 3/4 of the 200 model-grain row (150 BEV : 50 ICE).
        self.assertAlmostEqual(bev["units"], 300.0)

    def test_growth_compares_two_years(self):
        rows = cube.growth(self.conn, "brand", base="2023", compare="2024")
        acme = next(r for r in rows if r["brand"] == "Acme")
        self.assertEqual(acme["units_base"], 600.0)
        self.assertEqual(acme["units_compare"], 600.0)
        self.assertEqual(acme["growth"], 0.0)

    def test_unknown_group_by_is_rejected(self):
        with self.assertRaises(ValueError):
            cube.run(self.conn, ["colour"])
        with self.assertRaises(ValueError):
            cube.run(self.conn, ["brand"], filters={"1=1; DROP TABLE x": 1})

    def test_pivot_reshapes_without_losing_units(self):
        result = cube.run(self.conn, ["body_type", "powertrain"])
        _, rows = cube.pivot(result, "powertrain")
        self.assertAlmostEqual(sum(r["total"] for r in rows), result.total_units)


class AuthoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        (self.dir / "models").mkdir()
        (self.dir / "models" / "acme.json").write_text(
            json.dumps(tiny_payload(), ensure_ascii=False), encoding="utf-8")

    def write_rows(self, rows):
        path = self.dir / "add.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(authoring.COLUMNS))
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_csv_import_creates_the_whole_nesting(self):
        path = self.write_rows([{
            "brand": "Zeta", "model": "Comet", "generation": "C1",
            "variant": "Long Range", "brand_segment": "PREMIUM_TECH",
            "brand_origin": "CN", "body_type": "SEDAN", "segment": "D",
            "seats": "5", "launched": "2024-02-01", "powertrain": "BEV",
            "drivetrain": "RWD", "battery_kwh": "80", "start": "2024-02-01",
            "price_thb": "1990000", "import_type": "CBU", "origin_country": "CN",
        }])
        applied, problems, written = authoring.import_csv(path, self.dir)
        self.assertEqual(applied, 1)
        self.assertEqual([p for p in problems if p.startswith("line ")], [])
        self.assertTrue(written)
        catalog = Catalog.load(self.dir)
        resolved = catalog.resolve("zeta.comet.c1.long_range", "2024-06-01")
        self.assertIs(resolved["market_position"], MarketPosition.LUXURY)
        self.assertIs(resolved["brand_segment"], BrandSegment.PREMIUM_TECH)

    def test_second_import_adds_a_period_instead_of_overwriting(self):
        path = self.write_rows([{
            "brand": "Acme", "model": "Volt", "generation": "V1",
            "variant": "EV Standard", "start": "2025-01-01",
            "price_thb": "849000", "import_type": "CKD", "origin_country": "TH",
        }])
        authoring.import_csv(path, self.dir)
        catalog = Catalog.load(self.dir)
        periods = catalog.periods["acme.volt.v1.ev_standard"]
        self.assertEqual([p.start for p in periods],
                         ["2023-03-01", "2024-06-01", "2025-01-01"])
        self.assertEqual(periods[1].end, "2025-01-01")
        self.assertEqual(catalog.validate(), [])

    def test_a_row_that_would_break_the_catalog_is_not_written(self):
        path = self.write_rows([{
            "brand": "Acme", "model": "Volt", "generation": "V1",
            "variant": "Broken", "powertrain": "BEV", "engine_cc": "1500",
            "start": "2024-01-01", "price_thb": "900000",
            "import_type": "CKD", "origin_country": "TH",
        }])
        applied, problems, written = authoring.import_csv(path, self.dir)
        self.assertTrue(any("must not declare engine_cc" in p for p in problems))
        catalog = Catalog.load(self.dir)
        self.assertNotIn("acme.volt.v1.broken", catalog.variants)

    def test_round_trip_export_import_is_stable(self):
        catalog = Catalog.load(self.dir)
        out = self.dir / "flat.csv"
        authoring.export_csv(catalog, out)
        before = json.loads((self.dir / "models" / "acme.json").read_text())
        authoring.import_csv(out, self.dir)
        after = Catalog.load(self.dir)
        self.assertEqual(sorted(after.variants), sorted(catalog.variants))
        self.assertEqual(after.validate(), [])
        self.assertEqual(len(before["models"]), len(after.models_of("acme")))


if __name__ == "__main__":
    unittest.main()
