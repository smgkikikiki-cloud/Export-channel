#!/usr/bin/env python3
"""Generate a SYNTHETIC DLT-shaped export so the pipeline can be exercised
offline. These are NOT real registration figures - they exist only to prove the
loader, the review queue and the cube. Replace with a real DLT download before
reading anything into the numbers.
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vehreg.catalog import Catalog  # noqa: E402

OUT = ROOT / "data" / "raw" / "sample_dlt_registrations.csv"
PERIODS = [f"{y}-{m:02d}" for y in (2023, 2024, 2025) for m in range(1, 13)]

# Rough monthly scale by segment so the synthetic mix is not uniform noise.
SCALE = {"A": 300, "B": 1400, "C": 900, "D": 400, "E": 120, "F": 3000,
         "UNKNOWN": 100}
BRAND_WEIGHT = {"toyota": 3.0, "isuzu": 2.4, "honda": 1.6, "ford": 1.0,
                "mitsubishi": 0.9, "nissan": 0.5, "byd": 1.1, "mg": 0.7,
                "gwm": 0.4, "mazda": 0.4}

# Labels DLT prints that the seeded catalog cannot place, so the review queue is
# never empty in a demo - that is the honest default state of this pipeline.
UNKNOWN_LABELS = [
    ("DEEPAL", "S05"), ("WULING", "BINGO EV"), ("JETOUR", "DASHING"),
    ("FOTON", "TUNLAND G7"), ("", "รถยนต์นั่งอื่น ๆ"),
]


def main() -> None:
    random.seed(20260903)
    catalog = Catalog.load()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for model in catalog.models.values():
        brand = catalog.brands[model.brand_id]
        variants = catalog.variants_of(model.id)
        if not variants:
            continue
        gen = catalog.generation_for_variant(variants[0].id)
        base = SCALE.get(gen.segment.value, 100) * BRAND_WEIGHT.get(brand.id, 0.25)
        trend = random.uniform(-0.4, 0.6)
        for index, period in enumerate(PERIODS):
            if gen.launched and period < gen.launched[:7]:
                continue
            drift = 1 + trend * (index / len(PERIODS))
            units = max(0, int(random.gauss(base * drift, base * 0.28)))
            if units == 0:
                continue
            # Most months arrive at model grain; some sources break out a trim.
            if random.random() < 0.35:
                variant = random.choice(variants)
                rows.append({
                    "เดือน": period, "ยี่ห้อ": brand.name_en,
                    "แบบรถ": model.name_en, "รุ่นย่อย": variant.name,
                    "ประเภท": model.registration_type.value,
                    "จำนวน": units,
                })
            else:
                rows.append({
                    "เดือน": period, "ยี่ห้อ": brand.name_en,
                    "แบบรถ": model.name_en, "รุ่นย่อย": "",
                    "ประเภท": model.registration_type.value,
                    "จำนวน": units,
                })

    for brand_label, model_label in UNKNOWN_LABELS:
        for period in PERIODS[::4]:
            rows.append({"เดือน": period, "ยี่ห้อ": brand_label,
                         "แบบรถ": model_label, "รุ่นย่อย": "",
                         "ประเภท": "RY1", "จำนวน": random.randint(20, 260)})

    with open(OUT, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["เดือน", "ยี่ห้อ", "แบบรถ", "รุ่นย่อย",
                                "ประเภท", "จำนวน"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} synthetic rows to {OUT}")


if __name__ == "__main__":
    main()
