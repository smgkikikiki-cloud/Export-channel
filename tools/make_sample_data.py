#!/usr/bin/env python3
"""Generate SYNTHETIC DLT-shaped exports for 2026 so the pipeline can be
exercised offline. These are NOT real registration figures - they exist only to
prove the loader, the class scoping, the review queue and the cube. Replace with
real DLT downloads before reading anything into the numbers.

Rows stop at the nameplate, with no trim column, because that is what DLT
actually publishes - there is no public trim-level registration data.

Two files are written, because that is how DLT publishes and how the double-cab
split resolves:

    sample_dlt_ry1_2026.csv   รย.1 - passenger cars and double-cab pickups
    sample_dlt_ry3_2026.csv   รย.3 - single cab and smart cab pickups
"""

from __future__ import annotations

import csv
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vehreg.catalog import DEFAULT_YEAR, Catalog  # noqa: E402

OUT_DIR = ROOT / "data" / "raw"
YEAR = DEFAULT_YEAR
PERIODS = [f"{YEAR}-{m:02d}" for m in range(1, 13)]
HEADER = ["เดือน", "ยี่ห้อ", "แบบรถ", "จำนวน"]

# Rough monthly scale by segment so the synthetic mix is not uniform noise.
SCALE = {"A": 300, "B": 1400, "C": 900, "D": 400, "E": 120, "F": 1200,
         "UNKNOWN": 100}
# A halo model still shows up in DLT, just barely - which is the whole reason
# market_scope exists rather than deleting those rows.
SCOPE_WEIGHT = {"CORE": 1.0, "NICHE": 0.01, "GREY": 0.01, "UNKNOWN": 0.5}
BRAND_WEIGHT = {"toyota": 3.0, "isuzu": 2.4, "honda": 1.6, "ford": 1.0,
                "mitsubishi": 0.9, "nissan": 0.5, "byd": 1.1, "mg": 0.7,
                "gwm": 0.4, "mazda": 0.4}

# Words DLT usually leaves out of the "แบบรถ" cell, which is exactly why the
# รย. class has to scope the match.
CAB_WORDS = re.compile(
    r"\s+(single cab|double cab|smart cab|club cab|king cab|open cab|"
    r"freestyle cab|giant cab|cab4|spark)$", re.IGNORECASE)

# Labels DLT prints that the seeded catalog cannot place, so the review queue is
# never empty in a demo - that is the honest default state of this pipeline.
UNKNOWN_LABELS = [
    ("DEEPAL", "S05"), ("WULING", "BINGO EV"), ("JETOUR", "DASHING"),
    ("FOTON", "TUNLAND G7"), ("", "รถยนต์นั่งอื่น ๆ"),
]


def main() -> None:
    random.seed(20260903)
    catalog = Catalog.load()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows: dict[str, list[dict]] = {"RY1": [], "RY2": [], "RY3": []}

    for model in catalog.models.values():
        brand = catalog.brands[model.brand_id]
        variants = catalog.variants_of(model.id)
        if not variants:
            continue
        gen = catalog.generation_for_variant(variants[0].id)
        base = (SCALE.get(gen.segment.value, 100)
                * BRAND_WEIGHT.get(brand.id, 0.25)
                * SCOPE_WEIGHT.get(model.market_scope.value, 1.0))
        trend = random.uniform(-0.4, 0.6)
        bucket = rows.setdefault(model.registration_type.value, [])

        for index, period in enumerate(PERIODS):
            drift = 1 + trend * (index / len(PERIODS))
            units = max(0, int(random.gauss(base * drift, base * 0.28)))
            if units == 0:
                continue
            # DLT drops the cab word about half the time; the รย. class of the
            # file is then the only thing that can resolve it.
            label = model.name_en
            if random.random() < 0.4:
                label = CAB_WORDS.sub("", label) or model.name_en
            bucket.append({"เดือน": period, "ยี่ห้อ": brand.name_en,
                           "แบบรถ": label, "จำนวน": units})

    for brand_label, model_label in UNKNOWN_LABELS:
        for period in PERIODS[::3]:
            rows["RY1"].append({"เดือน": period, "ยี่ห้อ": brand_label,
                                "แบบรถ": model_label,
                                "จำนวน": random.randint(20, 260)})

    for reg, bucket in rows.items():
        if not bucket:
            continue
        path = OUT_DIR / f"sample_dlt_{reg.lower()}_{YEAR}.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADER)
            writer.writeheader()
            writer.writerows(bucket)
        print(f"wrote {len(bucket):>5} synthetic {reg} rows to {path}")


if __name__ == "__main__":
    main()
