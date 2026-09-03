#!/usr/bin/env python3
"""One-shot seed for vehreg/data/models/*.json.

After the first run the JSON files are the source of truth - edit those, or use
``python -m vehreg catalog import-csv``. This script exists so the initial Thai
market backbone is reviewable as code rather than hand-typed JSON.

PRICES ARE UNVERIFIED SEED VALUES. Every period is written with
price_note="seed-unverified" so `python -m vehreg catalog audit` can list what
the owner still has to confirm against a real price list.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vehreg.normalize import slug  # noqa: E402

OUT = ROOT / "vehreg" / "data" / "models"

_files: dict[str, dict] = {}
_ctx: dict = {}


def B(bid, name_en, name_th, brand_segment, oem_group, origin, aliases=()):
    payload = {
        "brand": {
            "id": bid, "name_en": name_en, "name_th": name_th,
            "brand_segment": brand_segment, "oem_group": oem_group,
            "brand_origin": origin, "aliases": list(aliases),
        },
        "models": [],
    }
    _files[bid] = payload
    _ctx["brand"] = payload


def M(mid, name_en, name_th, body, cab="NOT_APPLICABLE", reg=None, aliases=(),
      notes=""):
    model = {
        "id": mid, "name_en": name_en, "name_th": name_th, "body_type": body,
        "cab_type": cab,
        "registration_type": reg or ("RY3" if body == "PICKUP" else "RY1"),
        "aliases": list(aliases), "notes": notes, "generations": [],
    }
    _ctx["brand"]["models"].append(model)
    _ctx["model"] = model


def G(code, segment, seats, launched, ended=None):
    gen = {"code": code, "segment": segment, "seats": seats,
           "launched": launched, "ended": ended, "variants": []}
    _ctx["model"]["generations"].append(gen)
    _ctx["gen"] = gen


def V(name, powertrain, drivetrain, cc, kwh, price, import_type, origin,
      start=None, aliases=(), cab="NOT_APPLICABLE", overrides=None):
    gen = _ctx["gen"]
    gen["variants"].append({
        "name": name, "powertrain": powertrain, "drivetrain": drivetrain,
        "engine_cc": cc, "battery_kwh": kwh, "cab_type": cab,
        "aliases": list(aliases), "overrides": overrides or {},
        "periods": [{
            "start": start or gen["launched"], "end": None, "price_thb": price,
            "import_type": import_type, "origin_country": origin,
            "model_year": None, "price_note": "seed-unverified",
        }],
    })


def P(start, price, import_type, origin, end=None, note="seed-unverified"):
    """Add a later dated period to the variant declared just above.

    Use this whenever a car's price, import route or plant changed while the
    same trim stayed on sale - a BYD Atto 3 that switched from Chinese CBU to
    Rayong CKD is one variant with two periods, not two variants.
    """
    variant = _ctx["gen"]["variants"][-1]
    variant["periods"][-1]["end"] = start
    variant["periods"].append({
        "start": start, "end": end, "price_thb": price,
        "import_type": import_type, "origin_country": origin,
        "model_year": None, "price_note": note,
    })


def write() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for bid, payload in _files.items():
        (OUT / f"{bid}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    models = sum(len(p["models"]) for p in _files.values())
    variants = sum(len(v["variants"])
                   for p in _files.values() for m in p["models"]
                   for v in m["generations"])
    print(f"wrote {len(_files)} brands, {models} models, {variants} variants "
          f"to {OUT}")


def seed_japanese() -> None:
    # ---------------------------------------------------------------- Toyota
    B("toyota", "Toyota", "โตโยต้า", "MASS", "Toyota Group", "JP",
      ["โตโยต้า", "toyota motor thailand", "TMT"])
    M("yaris_ativ", "Yaris Ativ", "ยาริส เอทีฟ", "SEDAN",
      aliases=["ativ", "yaris ativ", "ยาริสเอทีฟ"])
    G("MXPA10", "B", 5, "2022-08-09")
    V("1.2 Sport", "ICE", "FWD", 1197, None, 559000, "CKD", "TH")
    V("1.2 Smart", "ICE", "FWD", 1197, None, 609000, "CKD", "TH")
    V("1.2 Premium", "ICE", "FWD", 1197, None, 664000, "CKD", "TH")
    V("1.2 Premium Luxury", "ICE", "FWD", 1197, None, 709000, "CKD", "TH")
    M("yaris", "Yaris", "ยาริส", "HATCHBACK", aliases=["ยาริส"])
    G("MXPA1x", "B", 5, "2023-01-01")
    V("1.2 Sport", "ICE", "FWD", 1197, None, 559000, "CKD", "TH")
    V("1.2 Premium", "ICE", "FWD", 1197, None, 664000, "CKD", "TH")
    M("corolla_altis", "Corolla Altis", "โคโรลล่า อัลติส", "SEDAN",
      aliases=["altis", "corolla"])
    G("E210", "C", 5, "2019-08-01")
    V("1.8 Sport", "ICE", "FWD", 1798, None, 899000, "CKD", "TH")
    V("1.8 HEV Smart", "HEV", "FWD", 1798, 1.3, 979000, "CKD", "TH")
    V("1.8 HEV GR Sport", "HEV", "FWD", 1798, 1.3, 1094000, "CKD", "TH")
    M("camry", "Camry", "คัมรี่", "SEDAN", aliases=["แคมรี่"])
    G("XV80", "D", 5, "2024-11-01")
    V("2.5 HEV Premium", "HEV", "FWD", 2487, 1.0, 1899000, "CKD", "TH")
    V("2.5 HEV Premium Luxury", "HEV", "FWD", 2487, 1.0, 2099000, "CKD", "TH")
    M("corolla_cross", "Corolla Cross", "โคโรลล่า ครอส", "CROSSOVER",
      aliases=["corolla cross"])
    G("XG10", "C", 5, "2020-07-01")
    V("1.8 Smart", "ICE", "FWD", 1798, None, 959000, "CKD", "TH")
    V("1.8 HEV Smart", "HEV", "FWD", 1798, 1.3, 1029000, "CKD", "TH")
    V("1.8 HEV Premium", "HEV", "FWD", 1798, 1.3, 1149000, "CKD", "TH")
    V("1.8 HEV GR Sport", "HEV", "FWD", 1798, 1.3, 1239000, "CKD", "TH")
    M("yaris_cross", "Yaris Cross", "ยาริส ครอส", "CROSSOVER")
    G("AC200", "B", 5, "2023-09-01")
    V("1.5 HEV Smart", "HEV", "FWD", 1490, 0.8, 799000, "CKD", "TH")
    V("1.5 HEV Premium Luxury", "HEV", "FWD", 1490, 0.8, 899000, "CKD", "TH")
    M("fortuner", "Fortuner", "ฟอร์จูนเนอร์", "PPV", aliases=["ฟอร์จูนเนอร์"])
    G("AN160", "D", 7, "2020-06-01")
    V("2.4 V 4x2", "ICE", "RWD", 2393, None, 1399000, "CKD", "TH")
    V("2.8 Legender 4x2", "ICE", "RWD", 2755, None, 1699000, "CKD", "TH")
    V("2.8 GR Sport 4x4", "ICE", "4WD", 2755, None, 1999000, "CKD", "TH")
    M("hilux_revo", "Hilux Revo", "ไฮลักซ์ รีโว่", "PICKUP",
      aliases=["revo", "hilux", "ไฮลักซ์", "revo smart cab", "hilux revo"])
    G("AN120", "F", 5, "2020-06-01")
    V("2.4 Entry Single Cab", "ICE", "RWD", 2393, None, 599000, "CKD", "TH",
      cab="SINGLE_CAB")
    V("2.4 Mid Smart Cab", "ICE", "RWD", 2393, None, 749000, "CKD", "TH",
      cab="SMART_CAB")
    V("2.4 Prerunner Double Cab", "ICE", "RWD", 2393, None, 899000, "CKD", "TH",
      cab="DOUBLE_CAB")
    V("2.8 GR Sport 4x4 Double Cab", "ICE", "4WD", 2755, None, 1359000, "CKD",
      "TH", cab="DOUBLE_CAB")
    M("hilux_champ", "Hilux Champ", "ไฮลักซ์ แชมป์", "PICKUP",
      aliases=["champ", "hilux champ"])
    G("CHAMP", "F", 2, "2023-11-22")
    V("2.0 Single Cab", "ICE", "RWD", 1998, None, 459000, "CKD", "TH",
      cab="SINGLE_CAB")
    V("2.4 Single Cab", "ICE", "RWD", 2393, None, 577000, "CKD", "TH",
      cab="SINGLE_CAB")
    M("innova_zenix", "Innova Zenix", "อินโนว่า ซีนิกซ์", "MPV",
      aliases=["innova", "zenix"])
    G("AW40", "D", 7, "2023-06-01")
    V("2.0 HEV Premium", "HEV", "FWD", 1987, 1.0, 1349000, "CBU", "ID")
    M("veloz", "Veloz", "เวลอซ", "MPV")
    G("W100", "B", 7, "2022-04-01")
    V("1.5 Premium", "ICE", "FWD", 1496, None, 795000, "CBU", "ID")
    M("alphard", "Alphard", "อัลพาร์ด", "MPV")
    G("AH40", "E", 7, "2023-09-01")
    V("2.5 HEV Executive Lounge", "HEV", "AWD", 2487, 1.0, 4599000, "CBU", "JP")
    M("bz4x", "bZ4X", "บีแซดโฟร์เอ็กซ์", "CROSSOVER", aliases=["bz4x"])
    G("EA10", "C", 5, "2022-10-01")
    V("Premium", "BEV", "FWD", None, 71.4, 1836000, "CBU", "JP")
    M("land_cruiser_300", "Land Cruiser 300", "แลนด์ครุยเซอร์ 300", "PPV",
      aliases=["land cruiser", "lc300"])
    G("J300", "E", 7, "2021-08-01")
    V("3.3 D VX", "ICE", "4WD", 3346, None, 5990000, "CBU", "JP")

    # ----------------------------------------------------------------- Honda
    B("honda", "Honda", "ฮอนด้า", "MASS", "Honda", "JP", ["ฮอนด้า", "honda automobile"])
    M("city", "City", "ซิตี้", "SEDAN", aliases=["ซิตี้", "city sedan"])
    G("GN2", "B", 5, "2019-11-25")
    V("1.0 Turbo S+", "ICE", "FWD", 988, None, 609000, "CKD", "TH")
    V("1.0 Turbo SV", "ICE", "FWD", 988, None, 709000, "CKD", "TH")
    V("e:HEV SV", "HEV", "FWD", 1498, 0.7, 839000, "CKD", "TH")
    V("e:HEV RS", "HEV", "FWD", 1498, 0.7, 899000, "CKD", "TH")
    M("city_hatchback", "City Hatchback", "ซิตี้ แฮทช์แบ็ก", "HATCHBACK",
      aliases=["city hatchback", "city hb"])
    G("GN7", "B", 5, "2021-01-01")
    V("1.0 Turbo SV", "ICE", "FWD", 988, None, 749000, "CKD", "TH")
    V("e:HEV RS", "HEV", "FWD", 1498, 0.7, 924000, "CKD", "TH")
    M("civic", "Civic", "ซีวิค", "SEDAN", aliases=["ซีวิค"])
    G("FE", "C", 5, "2021-08-01")
    V("1.5 Turbo EL+", "ICE", "FWD", 1498, None, 1099000, "CKD", "TH")
    V("e:HEV RS", "HEV", "FWD", 1993, 1.1, 1299000, "CKD", "TH")
    M("accord", "Accord", "แอคคอร์ด", "SEDAN")
    G("CY", "D", 5, "2023-04-01")
    V("e:HEV EL", "HEV", "FWD", 1993, 1.1, 1749000, "CKD", "TH")
    M("hrv", "HR-V", "เอชอาร์-วี", "CROSSOVER", aliases=["hrv", "hr v"])
    G("RV", "B", 5, "2022-01-01")
    V("e:HEV E", "HEV", "FWD", 1498, 0.7, 999000, "CKD", "TH")
    V("e:HEV RS", "HEV", "FWD", 1498, 0.7, 1149000, "CKD", "TH")
    M("crv", "CR-V", "ซีอาร์-วี", "CROSSOVER", aliases=["crv", "cr v"])
    G("RS", "C", 7, "2023-11-01")
    V("2.0 e:HEV ES 4WD", "HEV", "AWD", 1993, 1.1, 1729000, "CKD", "TH")
    V("2.0 e:HEV RS", "HEV", "FWD", 1993, 1.1, 1599000, "CKD", "TH")
    M("wrv", "WR-V", "ดับเบิลยูอาร์-วี", "CROSSOVER", aliases=["wrv", "wr v"])
    G("DG", "B", 5, "2023-08-01")
    V("1.5 SV", "ICE", "FWD", 1498, None, 799000, "CKD", "TH")
    V("1.5 RS", "ICE", "FWD", 1498, None, 869000, "CKD", "TH")
    M("brv", "BR-V", "บีอาร์-วี", "MPV", aliases=["brv", "br v"])
    G("DG3", "B", 7, "2022-04-01")
    V("1.5 EL", "ICE", "FWD", 1498, None, 973000, "CKD", "TH")
    M("en1", "e:N1", "อีเอ็น1", "CROSSOVER", aliases=["en1", "e n1"])
    G("EN1", "B", 5, "2024-01-01")
    V("e:N1", "BEV", "FWD", None, 68.8, 1249000, "CKD", "TH")

    # ----------------------------------------------------------------- Isuzu
    B("isuzu", "Isuzu", "อีซูซุ", "MASS", "Isuzu", "JP", ["อีซูซุ", "tri petch isuzu"])
    M("dmax", "D-Max", "ดีแมคซ์", "PICKUP",
      aliases=["dmax", "d max", "ดีแมคซ์", "v-cross", "vcross", "spark", "hi-lander"])
    G("RG", "F", 5, "2019-10-11")
    V("1.9 Spark Single Cab", "ICE", "RWD", 1898, None, 569000, "CKD", "TH",
      cab="SINGLE_CAB")
    V("1.9 Hi-Lander Cab4", "ICE", "RWD", 1898, None, 829000, "CKD", "TH",
      cab="SMART_CAB")
    V("1.9 Hi-Lander Double Cab", "ICE", "RWD", 1898, None, 899000, "CKD", "TH",
      cab="DOUBLE_CAB")
    V("3.0 V-Cross 4x4 Double Cab", "ICE", "4WD", 2999, None, 1329000, "CKD",
      "TH", cab="DOUBLE_CAB")
    M("mux", "MU-X", "มิว-เอ็กซ์", "PPV", aliases=["mux", "mu x", "มิวเอ็กซ์"])
    G("RJ", "D", 7, "2020-10-01")
    V("1.9 Active", "ICE", "RWD", 1898, None, 1199000, "CKD", "TH")
    V("3.0 Ultimate 4x4", "ICE", "4WD", 2999, None, 1699000, "CKD", "TH")

    # ------------------------------------------------------------ Mitsubishi
    B("mitsubishi", "Mitsubishi", "มิตซูบิชิ", "MASS", "Mitsubishi Motors", "JP",
      ["มิตซูบิชิ", "mitsubishi motors"])
    M("triton", "Triton", "ไทรทัน", "PICKUP", aliases=["ไทรทัน", "triton athlete"])
    G("MV", "F", 5, "2023-07-26")
    V("2.4 GL Single Cab", "ICE", "RWD", 2442, None, 569000, "CKD", "TH",
      cab="SINGLE_CAB")
    V("2.4 GLX Club Cab", "ICE", "RWD", 2442, None, 719000, "CKD", "TH",
      cab="SMART_CAB")
    V("2.4 Athlete Double Cab", "ICE", "RWD", 2442, None, 999000, "CKD", "TH",
      cab="DOUBLE_CAB")
    V("2.4 Ultimate 4WD Double Cab", "ICE", "4WD", 2442, None, 1249000, "CKD",
      "TH", cab="DOUBLE_CAB")
    M("pajero_sport", "Pajero Sport", "ปาเจโร สปอร์ต", "PPV",
      aliases=["pajero", "ปาเจโร"])
    G("QF", "D", 7, "2019-07-01")
    V("2.4 GT", "ICE", "RWD", 2442, None, 1399000, "CKD", "TH")
    V("2.4 GT Premium 4WD", "ICE", "4WD", 2442, None, 1729000, "CKD", "TH")
    M("xpander", "Xpander", "เอ็กซ์แพนเดอร์", "MPV", aliases=["เอ็กซ์แพนเดอร์"])
    G("A1", "B", 7, "2018-08-01")
    V("1.5 GT", "ICE", "FWD", 1499, None, 899000, "CBU", "ID")
    V("1.6 HEV GT", "HEV", "FWD", 1600, 0.8, 1099000, "CBU", "ID")
    M("xpander_cross", "Xpander Cross", "เอ็กซ์แพนเดอร์ ครอส", "MPV")
    G("A1C", "B", 7, "2020-01-01")
    V("1.5 GT", "ICE", "FWD", 1499, None, 949000, "CBU", "ID")
    M("attrage", "Attrage", "แอททราจ", "SEDAN", aliases=["แอททราจ"])
    G("A10", "B", 5, "2019-11-01")
    V("1.2 GLS", "ICE", "FWD", 1193, None, 559000, "CKD", "TH")
    M("mirage", "Mirage", "มิราจ", "HATCHBACK", aliases=["มิราจ"])
    G("A05", "A", 5, "2019-11-01")
    V("1.2 GLS", "ICE", "FWD", 1193, None, 519000, "CKD", "TH")
    M("xforce", "Xforce", "เอ็กซ์ฟอร์ซ", "CROSSOVER")
    G("XF", "B", 5, "2024-01-01")
    V("1.5 Ultimate", "ICE", "FWD", 1499, None, 949000, "CBU", "ID")

    # ---------------------------------------------------------------- Nissan
    B("nissan", "Nissan", "นิสสัน", "MASS", "Nissan", "JP", ["นิสสัน"])
    M("almera", "Almera", "อัลเมร่า", "SEDAN", aliases=["อัลเมร่า"])
    G("N18", "B", 5, "2019-11-01")
    V("1.0 Turbo VL", "ICE", "FWD", 999, None, 679000, "CKD", "TH")
    M("kicks", "Kicks e-Power", "คิกส์ อี-พาวเวอร์", "CROSSOVER",
      aliases=["kicks", "คิกส์"])
    G("P15", "B", 5, "2020-05-01")
    V("e-Power VL", "REEV", "FWD", 1198, 2.1, 1029000, "CKD", "TH")
    M("navara", "Navara", "นาวาร่า", "PICKUP", aliases=["นาวาร่า", "np300"])
    G("D23", "F", 5, "2021-01-01")
    V("2.5 S Single Cab", "ICE", "RWD", 2488, None, 569000, "CKD", "TH",
      cab="SINGLE_CAB")
    V("2.5 Pro-4X Double Cab", "ICE", "4WD", 2488, None, 1199000, "CKD", "TH",
      cab="DOUBLE_CAB")
    M("terra", "Terra", "เทอร์ร่า", "PPV")
    G("D23T", "D", 7, "2018-10-01")
    V("2.3 VL 4WD", "ICE", "4WD", 2298, None, 1599000, "CKD", "TH")

    # ----------------------------------------------------------------- Mazda
    B("mazda", "Mazda", "มาสด้า", "MASS", "Mazda", "JP", ["มาสด้า"])
    M("mazda2", "Mazda2", "มาสด้า2", "SEDAN", aliases=["mazda 2", "มาสด้า 2"])
    G("DJ", "B", 5, "2019-11-01")
    V("1.3 S Sedan", "ICE", "FWD", 1298, None, 546000, "CKD", "TH")
    V("1.3 SP Hatchback", "ICE", "FWD", 1298, None, 799000, "CKD", "TH",
      overrides={"body_type": "HATCHBACK"})
    M("mazda3", "Mazda3", "มาสด้า3", "SEDAN", aliases=["mazda 3"])
    G("BP", "C", 5, "2019-05-01")
    V("2.0 SP", "ICE", "FWD", 1998, None, 1199000, "CBU", "JP")
    M("cx3", "CX-3", "ซีเอ็กซ์-3", "CROSSOVER", aliases=["cx 3", "cx3"])
    G("DK", "B", 5, "2020-01-01")
    V("2.0 Base Plus", "ICE", "FWD", 1998, None, 799000, "CKD", "TH")
    M("cx30", "CX-30", "ซีเอ็กซ์-30", "CROSSOVER", aliases=["cx 30", "cx30"])
    G("DM", "C", 5, "2019-10-01")
    V("2.0 SP", "ICE", "FWD", 1998, None, 1199000, "CBU", "JP")
    M("cx5", "CX-5", "ซีเอ็กซ์-5", "CROSSOVER", aliases=["cx 5", "cx5"])
    G("KF", "D", 5, "2017-11-01")
    V("2.0 SP", "ICE", "FWD", 1998, None, 1490000, "CKD", "TH")
    M("cx8", "CX-8", "ซีเอ็กซ์-8", "CROSSOVER", aliases=["cx 8", "cx8"])
    G("KG", "D", 7, "2019-01-01")
    V("2.5 SP", "ICE", "FWD", 2488, None, 1699000, "CKD", "TH")
    M("bt50", "BT-50", "บีที-50", "PICKUP", aliases=["bt 50", "bt50"])
    G("TFR", "F", 5, "2020-11-01")
    V("1.9 S Single Cab", "ICE", "RWD", 1898, None, 559000, "CKD", "TH",
      cab="SINGLE_CAB")
    V("3.0 SP 4x4 Double Cab", "ICE", "4WD", 2999, None, 1249000, "CKD", "TH",
      cab="DOUBLE_CAB")

    # ---------------------------------------------------------------- Suzuki
    B("suzuki", "Suzuki", "ซูซูกิ", "BUDGET", "Suzuki", "JP", ["ซูซูกิ"])
    M("swift", "Swift", "สวิฟท์", "HATCHBACK", aliases=["สวิฟท์"])
    G("AZ", "B", 5, "2018-03-01")
    V("1.2 GLX", "ICE", "FWD", 1197, None, 599000, "CKD", "TH")
    M("ciaz", "Ciaz", "เซียส", "SEDAN")
    G("YL1", "B", 5, "2016-01-01")
    V("1.2 GLX", "ICE", "FWD", 1197, None, 675000, "CKD", "TH")
    M("celerio", "Celerio", "เซเลริโอ", "HATCHBACK")
    G("LF", "A", 5, "2018-01-01")
    V("1.0 GL", "ICE", "FWD", 998, None, 399000, "CKD", "TH")
    M("ertiga", "Ertiga", "เออร์ติก้า", "MPV")
    G("XL6", "B", 7, "2019-01-01")
    V("1.5 GX", "ICE", "FWD", 1462, None, 715000, "CBU", "ID")
    M("xl7", "XL7", "เอ็กซ์แอล7", "MPV", aliases=["xl 7"])
    G("XL7G", "B", 7, "2020-02-01")
    V("1.5 GLX", "ICE", "FWD", 1462, None, 799000, "CBU", "ID")
    M("jimny", "Jimny", "จิมนี่", "SUV", aliases=["จิมนี่"])
    G("JB74", "A", 4, "2019-01-01")
    V("1.5 4WD", "ICE", "4WD", 1462, None, 1550000, "CBU", "JP")
    M("fronx", "Fronx", "ฟรอนซ์", "CROSSOVER")
    G("FRX", "B", 5, "2024-06-01")
    V("1.5 GLX", "ICE", "FWD", 1462, None, 659000, "CBU", "IN")

    # ---------------------------------------------------------------- Subaru
    B("subaru", "Subaru", "ซูบารุ", "MASS", "Subaru", "JP", ["ซูบารุ"])
    M("forester", "Forester", "ฟอเรสเตอร์", "CROSSOVER")
    G("SK", "C", 5, "2019-01-01")
    V("2.0 i-S EyeSight", "ICE", "AWD", 1995, None, 1590000, "CBU", "JP")
    M("crosstrek", "Crosstrek", "ครอสส์เทรค", "CROSSOVER", aliases=["xv"])
    G("GU", "B", 5, "2023-11-01")
    V("2.0 e-Boxer", "MHEV", "AWD", 1995, 0.6, 1290000, "CBU", "JP")


def seed_chinese() -> None:
    # -------------------------------------------------------------------- MG
    B("mg", "MG", "เอ็มจี", "MASS", "SAIC", "CN",
      ["เอ็มจี", "mg sales thailand", "morris garages"])
    M("mg3", "MG3", "เอ็มจี3", "HATCHBACK", aliases=["mg 3"])
    G("MG3H", "B", 5, "2024-07-01")
    V("1.5 HEV+", "HEV", "FWD", 1498, 1.8, 789000, "CBU", "CN")
    M("mg4", "MG4 Electric", "เอ็มจี4", "HATCHBACK", aliases=["mg4", "mg 4"])
    G("MG4E", "C", 5, "2022-11-01")
    V("D 51kWh", "BEV", "RWD", None, 51.0, 769000, "CBU", "CN")
    V("X 64kWh", "BEV", "RWD", None, 64.0, 969000, "CBU", "CN")
    M("mg5", "MG5", "เอ็มจี5", "SEDAN", aliases=["mg 5"])
    G("MG5G", "C", 5, "2021-01-01")
    V("1.5 X", "ICE", "FWD", 1498, None, 679000, "CKD", "TH")
    M("mg_zs", "MG ZS", "เอ็มจี แซดเอส", "CROSSOVER", aliases=["zs"])
    G("ZSG", "B", 5, "2018-01-01")
    V("1.5 X", "ICE", "FWD", 1498, None, 689000, "CKD", "TH")
    M("mg_zs_ev", "MG ZS EV", "เอ็มจี แซดเอส อีวี", "CROSSOVER",
      aliases=["zs ev", "new zs ev"])
    G("ZSEV", "B", 5, "2019-06-01")
    V("Long Range", "BEV", "FWD", None, 51.1, 949000, "CBU", "CN")
    M("mg_hs", "MG HS", "เอ็มจี เอชเอส", "CROSSOVER", aliases=["hs"])
    G("HSG", "C", 5, "2019-01-01")
    V("1.5 Turbo X", "ICE", "FWD", 1490, None, 999000, "CKD", "TH")
    V("PHEV X", "PHEV", "FWD", 1490, 16.6, 1359000, "CKD", "TH")
    M("mg_vs_hev", "MG VS HEV", "เอ็มจี วีเอส เอชอีวี", "CROSSOVER",
      aliases=["vs hev"])
    G("VSH", "B", 5, "2023-08-01")
    V("HEV D", "HEV", "FWD", 1498, 1.8, 899000, "CBU", "CN")
    M("mg_extender", "MG Extender", "เอ็มจี เอ็กซ์เทนเดอร์", "PICKUP",
      aliases=["extender"])
    G("EXT", "F", 5, "2019-10-01")
    V("2.0 Grand Tiger Double Cab", "ICE", "RWD", 1996, None, 799000, "CKD",
      "TH", cab="DOUBLE_CAB")
    V("2.0 Giant Cab", "ICE", "RWD", 1996, None, 649000, "CKD", "TH",
      cab="SMART_CAB")
    M("mg_maxus_9", "MG Maxus 9", "เอ็มจี แม็กซัส 9", "MPV",
      aliases=["maxus 9", "mifa 9"])
    G("MIFA9", "E", 7, "2023-03-01", )
    V("Luxury", "BEV", "FWD", None, 90.0, 2599000, "CBU", "CN")
    M("mg_es", "MG ES", "เอ็มจี อีเอส", "CROSSOVER", aliases=["es5", "mg es5"])
    G("ES5", "C", 5, "2025-01-01")
    V("Long Range", "BEV", "RWD", None, 62.0, 999000, "CBU", "CN")

    # ------------------------------------------------------------------ BYD
    B("byd", "BYD", "บีวายดี", "MASS", "BYD", "CN", ["บีวายดี", "rever automotive"])
    M("atto3", "Atto 3", "แอตโต้ 3", "CROSSOVER", aliases=["atto 3", "yuan plus"])
    G("ATTO3", "B", 5, "2022-10-01")
    V("Extended Range", "BEV", "FWD", None, 60.5, 1199000, "CBU", "CN",
      "2022-10-01")
    P("2023-07-01", 1099000, "CBU", "CN")     # first public price cut
    P("2024-07-04", 899000, "CKD", "TH")      # Rayong plant opens, CBU -> CKD
    M("dolphin", "Dolphin", "ดอลฟิน", "HATCHBACK", aliases=["ดอลฟิน"])
    G("DOL", "B", 5, "2023-05-01")
    V("Standard Range", "BEV", "FWD", None, 44.9, 699000, "CBU", "CN")
    V("Extended Range", "BEV", "FWD", None, 60.5, 859000, "CBU", "CN")
    M("seal", "Seal", "ซีล", "SEDAN", aliases=["ซีล"])
    G("SEAL", "D", 5, "2023-09-01")
    V("Dynamic", "BEV", "RWD", None, 61.4, 1099000, "CBU", "CN")
    V("AWD Performance", "BEV", "AWD", None, 82.5, 1599000, "CBU", "CN")
    M("sealion6", "Sealion 6 DM-i", "ซีไลอ้อน 6", "CROSSOVER",
      aliases=["sealion 6", "seal u"])
    G("SL6", "C", 5, "2024-07-01")
    V("Dynamic DM-i", "PHEV", "FWD", 1498, 18.3, 899000, "CKD", "TH")
    M("sealion7", "Sealion 7", "ซีไลอ้อน 7", "CROSSOVER", aliases=["sealion 7"])
    G("SL7", "D", 5, "2025-01-01")
    V("Premium", "BEV", "RWD", None, 82.5, 1399000, "CKD", "TH")
    M("byd_m6", "BYD M6", "บีวายดี เอ็ม6", "MPV", aliases=["m6", "e6"])
    G("M6", "C", 7, "2024-08-01")
    V("Dynamic", "BEV", "FWD", None, 55.4, 829000, "CKD", "TH")
    M("shark6", "Shark 6", "ชาร์ค 6", "PICKUP", aliases=["shark", "shark 6"])
    G("SHK6", "F", 5, "2025-03-01")
    V("Premium DMO", "PHEV", "AWD", 1498, 29.6, 1599000, "CBU", "CN",
      cab="DOUBLE_CAB")
    M("seagull", "Dolphin Mini", "ดอลฟิน มินิ", "HATCHBACK",
      aliases=["seagull", "dolphin mini"])
    G("SGL", "A", 4, "2024-08-01")
    V("Standard", "BEV", "FWD", None, 38.0, 569000, "CBU", "CN")

    # ------------------------------------------------------------------ GWM
    B("gwm", "GWM", "จีดับเบิลยูเอ็ม", "MASS", "Great Wall Motor", "CN",
      ["great wall", "great wall motor", "เกรทวอลล์", "haval", "ora", "tank"])
    M("haval_h6", "Haval H6", "ฮาวาล เอช6", "CROSSOVER", aliases=["h6", "haval h6"])
    G("H6HEV", "C", 5, "2021-06-01")
    V("HEV Ultra", "HEV", "FWD", 1497, 1.8, 1199000, "CKD", "TH")
    V("PHEV Ultra", "PHEV", "FWD", 1497, 34.0, 1449000, "CBU", "CN")
    M("haval_jolion", "Haval Jolion", "ฮาวาล โจเลี่ยน", "CROSSOVER",
      aliases=["jolion"])
    G("JOL", "B", 5, "2021-11-01")
    V("HEV Ultra", "HEV", "FWD", 1497, 1.7, 879000, "CKD", "TH")
    M("ora_good_cat", "Ora Good Cat", "โอร่า กู๊ดแคท", "HATCHBACK",
      aliases=["good cat", "ora"])
    G("GC", "B", 5, "2021-02-01")
    V("500 Ultra", "BEV", "FWD", None, 63.1, 899000, "CBU", "CN")
    M("ora_03", "Ora 03", "โอร่า 03", "HATCHBACK", aliases=["ora 03"])
    G("O03", "B", 5, "2024-01-01")
    V("500 Ultra", "BEV", "FWD", None, 63.1, 829000, "CBU", "CN")
    M("tank300", "Tank 300", "แทงค์ 300", "PPV", aliases=["tank 300"])
    G("T300", "C", 5, "2023-03-01")
    V("HEV Ultra 4WD", "HEV", "4WD", 1998, 1.8, 1749000, "CBU", "CN")
    M("tank500", "Tank 500", "แทงค์ 500", "PPV", aliases=["tank 500"])
    G("T500", "E", 7, "2024-03-01")
    V("HEV Ultra 4WD", "HEV", "4WD", 1998, 1.8, 2999000, "CBU", "CN")

    # ----------------------------------------------------------------- Neta
    B("neta", "Neta", "เนต้า", "BUDGET", "Hozon", "CN", ["เนต้า", "hozon"])
    M("neta_v", "Neta V", "เนต้า วี", "CROSSOVER", aliases=["neta v", "v-ii"])
    G("NV", "A", 5, "2022-11-01")
    V("Standard", "BEV", "FWD", None, 40.7, 549000, "CBU", "CN")
    M("neta_x", "Neta X", "เนต้า เอ็กซ์", "CROSSOVER", aliases=["neta x"])
    G("NX", "B", 5, "2024-06-01")
    V("Smart", "BEV", "FWD", None, 52.5, 799000, "CKD", "TH")

    # -------------------------------------------------------------- Changan
    B("changan", "Changan", "ฉางอาน", "MASS", "Changan", "CN",
      ["ฉางอาน", "deepal", "ดีพัล", "avatr"])
    M("deepal_s07", "Deepal S07", "ดีพัล เอส07", "CROSSOVER",
      aliases=["deepal s07", "s07"])
    G("S07", "C", 5, "2024-03-01")
    V("Long Range", "BEV", "RWD", None, 79.9, 1359000, "CKD", "TH")
    M("deepal_l07", "Deepal L07", "ดีพัล แอล07", "SEDAN", aliases=["l07"])
    G("L07", "D", 5, "2024-06-01")
    V("Long Range", "BEV", "RWD", None, 79.9, 1099000, "CKD", "TH")

    # ------------------------------------------------------------- GAC Aion
    B("aion", "Aion", "ไอออน", "MASS", "GAC", "CN", ["gac aion", "ไอออน"])
    M("aion_y_plus", "Aion Y Plus", "ไอออน วาย พลัส", "CROSSOVER",
      aliases=["aion y", "y plus"])
    G("AYP", "B", 5, "2023-07-01")
    V("Premium 490", "BEV", "FWD", None, 63.2, 949000, "CKD", "TH")
    M("aion_es", "Aion ES", "ไอออน อีเอส", "SEDAN", aliases=["aion es"])
    G("AES", "C", 5, "2024-04-01")
    V("Standard", "BEV", "FWD", None, 55.0, 699000, "CKD", "TH")
    M("aion_v", "Aion V", "ไอออน วี", "CROSSOVER", aliases=["aion v"])
    G("AV", "C", 5, "2025-01-01")
    V("Luxury", "BEV", "FWD", None, 75.3, 1199000, "CKD", "TH")

    # ---------------------------------------------------------------- Chery
    B("chery", "Chery", "เชอรี่", "MASS", "Chery", "CN", ["omoda", "jaecoo", "jetour"])
    M("omoda_c5", "Omoda C5", "โอโมดา ซี5", "CROSSOVER", aliases=["omoda c5", "c5"])
    G("OC5", "B", 5, "2024-04-01")
    V("EV Luxury", "BEV", "FWD", None, 61.0, 989000, "CBU", "CN")
    M("jaecoo_j7", "Jaecoo J7", "เจคู เจ7", "CROSSOVER", aliases=["jaecoo j7", "j7"])
    G("J7", "C", 5, "2024-09-01")
    V("PHEV Luxury", "PHEV", "FWD", 1498, 18.3, 1099000, "CKD", "TH")

    # ---------------------------------------------------------------- Zeekr
    B("zeekr", "Zeekr", "ซีเคอร์", "PREMIUM_TECH", "Geely", "CN", ["ซีเคอร์"])
    M("zeekr_x", "Zeekr X", "ซีเคอร์ เอ็กซ์", "CROSSOVER", aliases=["zeekr x"])
    G("ZX", "B", 5, "2024-05-01")
    V("Long Range RWD", "BEV", "RWD", None, 66.0, 1199000, "CBU", "CN")
    M("zeekr_009", "Zeekr 009", "ซีเคอร์ 009", "MPV", aliases=["009"])
    G("Z009", "E", 6, "2024-05-01")
    V("Long Range", "BEV", "AWD", None, 116.0, 3999000, "CBU", "CN")

    # ---------------------------------------------------------------- XPeng
    B("xpeng", "XPeng", "เอ็กซ์เผิง", "PREMIUM_TECH", "XPeng", "CN", ["xpeng"])
    M("xpeng_g6", "XPeng G6", "เอ็กซ์เผิง จี6", "CROSSOVER", aliases=["g6"])
    G("G6", "D", 5, "2024-07-01")
    V("Long Range", "BEV", "RWD", None, 87.5, 1359000, "CKD", "TH")


def seed_korean_western() -> None:
    # -------------------------------------------------------------- Hyundai
    B("hyundai", "Hyundai", "ฮุนได", "MASS", "Hyundai Motor Group", "KR", ["ฮุนได"])
    M("creta", "Creta", "เครต้า", "CROSSOVER")
    G("SU2", "B", 5, "2023-01-01")
    V("1.5 SEL", "ICE", "FWD", 1497, None, 999000, "CBU", "ID")
    M("stargazer", "Stargazer", "สตาร์เกเซอร์", "MPV")
    G("KS", "B", 7, "2023-01-01")
    V("1.5 Smart", "ICE", "FWD", 1497, None, 799000, "CBU", "ID")
    M("ioniq5", "Ioniq 5", "ไอออนิค 5", "CROSSOVER", aliases=["ioniq 5"])
    G("NE", "C", 5, "2022-03-01")
    V("Exclusive", "BEV", "RWD", None, 72.6, 1849000, "CBU", "KR")
    M("ioniq6", "Ioniq 6", "ไอออนิค 6", "SEDAN", aliases=["ioniq 6"])
    G("CE", "D", 5, "2023-06-01")
    V("Exclusive", "BEV", "RWD", None, 77.4, 2299000, "CBU", "KR")
    M("staria", "Staria", "สตาเรีย", "MPV", reg="RY2")
    G("US4", "E", 11, "2021-10-01")
    V("2.2 D Premium", "ICE", "FWD", 2199, None, 1899000, "CBU", "KR")

    # ------------------------------------------------------------------ Kia
    B("kia", "Kia", "เกีย", "MASS", "Hyundai Motor Group", "KR", ["เกีย"])
    M("carnival", "Carnival", "คาร์นิวัล", "MPV", reg="RY2")
    G("KA4", "E", 11, "2021-06-01")
    V("2.2 D SXL", "ICE", "FWD", 2151, None, 2399000, "CBU", "KR")
    M("ev6", "EV6", "อีวี6", "CROSSOVER", aliases=["ev 6"])
    G("CV", "C", 5, "2022-01-01")
    V("GT-Line", "BEV", "RWD", None, 77.4, 2199000, "CBU", "KR")
    M("ev9", "EV9", "อีวี9", "SUV", aliases=["ev 9"])
    G("MV", "E", 7, "2024-01-01")
    V("GT-Line AWD", "BEV", "AWD", None, 99.8, 3490000, "CBU", "KR")

    # ----------------------------------------------------------------- Ford
    B("ford", "Ford", "ฟอร์ด", "MASS", "Ford", "US", ["ฟอร์ด"])
    M("ranger", "Ranger", "เรนเจอร์", "PICKUP", aliases=["เรนเจอร์", "ranger raptor"])
    G("P703", "F", 5, "2022-06-01")
    V("2.0 XL Single Cab", "ICE", "RWD", 1996, None, 649000, "CKD", "TH",
      cab="SINGLE_CAB")
    V("2.0 XLT Open Cab", "ICE", "RWD", 1996, None, 849000, "CKD", "TH",
      cab="SMART_CAB")
    V("2.0 Wildtrak 4x4 Double Cab", "ICE", "4WD", 1996, None, 1329000, "CKD",
      "TH", cab="DOUBLE_CAB")
    V("3.0 Raptor Double Cab", "ICE", "4WD", 2956, None, 1999000, "CKD", "TH",
      cab="DOUBLE_CAB")
    M("everest", "Everest", "เอเวอเรสต์", "PPV", aliases=["เอเวอเรสต์"])
    G("U704", "D", 7, "2022-06-01")
    V("2.0 Titanium+ 4x2", "ICE", "RWD", 1996, None, 1699000, "CKD", "TH")
    V("2.0 Platinum 4x4", "ICE", "4WD", 1996, None, 2199000, "CKD", "TH")
    M("mustang", "Mustang", "มัสแตง", "COUPE")
    G("S650", "D", 4, "2024-01-01")
    V("5.0 GT", "ICE", "RWD", 5038, None, 5999000, "CBU", "US")

    # ---------------------------------------------------------------- Tesla
    B("tesla", "Tesla", "เทสลา", "PREMIUM_TECH", "Tesla", "US", ["เทสลา"])
    M("model3", "Model 3", "โมเดล 3", "SEDAN", aliases=["model 3"])
    G("M3H", "D", 5, "2022-12-07")
    V("RWD", "BEV", "RWD", None, 60.0, 1599000, "CBU", "CN")
    V("Long Range AWD", "BEV", "AWD", None, 79.0, 1899000, "CBU", "CN")
    M("modely", "Model Y", "โมเดล วาย", "CROSSOVER", aliases=["model y"])
    G("MY", "D", 5, "2022-12-07")
    V("RWD", "BEV", "RWD", None, 60.0, 1799000, "CBU", "CN")
    V("Performance", "BEV", "AWD", None, 79.0, 2509000, "CBU", "CN")

    # ---------------------------------------------------------------- Volvo
    B("volvo", "Volvo", "วอลโว่", "PREMIUM_LUXURY", "Geely", "SE", ["วอลโว่"])
    M("xc40", "XC40", "เอ็กซ์ซี40", "CROSSOVER", aliases=["xc 40", "xc40 recharge"])
    G("XC40G", "C", 5, "2018-01-01")
    V("Recharge Pure Electric", "BEV", "AWD", None, 78.0, 2590000, "CKD", "TH")
    M("xc60", "XC60", "เอ็กซ์ซี60", "CROSSOVER", aliases=["xc 60"])
    G("XC60G", "D", 5, "2018-01-01")
    V("T8 Recharge Ultimate", "PHEV", "AWD", 1969, 18.8, 3390000, "CKD", "TH")
    M("xc90", "XC90", "เอ็กซ์ซี90", "SUV", aliases=["xc 90"])
    G("XC90G", "E", 7, "2016-01-01")
    V("T8 Recharge Ultimate", "PHEV", "AWD", 1969, 18.8, 4990000, "CKD", "TH")
    M("ex30", "EX30", "อีเอ็กซ์30", "CROSSOVER", aliases=["ex 30"])
    G("EX30G", "B", 5, "2024-05-01")
    V("Ultra Single Motor", "BEV", "RWD", None, 69.0, 1590000, "CBU", "CN")

    # ------------------------------------------------------------------ BMW
    B("bmw", "BMW", "บีเอ็มดับเบิลยู", "PREMIUM_LUXURY", "BMW Group", "DE",
      ["บีเอ็มดับเบิลยู", "bmw thailand"])
    M("bmw_3", "3 Series", "ซีรีส์ 3", "SEDAN", aliases=["320d", "330e", "series 3"])
    G("G20", "D", 5, "2019-01-01")
    V("330e M Sport", "PHEV", "RWD", 1998, 12.0, 2799000, "CKD", "TH")
    M("bmw_5", "5 Series", "ซีรีส์ 5", "SEDAN", aliases=["530e", "series 5"])
    G("G60", "E", 5, "2024-01-01")
    V("530e M Sport", "PHEV", "RWD", 1998, 19.4, 3999000, "CKD", "TH")
    M("bmw_x1", "X1", "เอ็กซ์1", "CROSSOVER", aliases=["x 1"])
    G("U11", "C", 5, "2023-01-01")
    V("sDrive18i xLine", "ICE", "FWD", 1499, None, 2399000, "CKD", "TH")
    M("bmw_x3", "X3", "เอ็กซ์3", "CROSSOVER", aliases=["x 3"])
    G("G45", "D", 5, "2024-11-01")
    V("20 xDrive M Sport", "MHEV", "AWD", 1998, 0.5, 3999000, "CKD", "TH")
    M("bmw_ix3", "iX3", "ไอเอ็กซ์3", "CROSSOVER", aliases=["ix 3"])
    G("G08", "D", 5, "2021-08-01")
    V("Inspiring", "BEV", "RWD", None, 80.0, 3399000, "CBU", "CN")
    M("bmw_i4", "i4", "ไอ4", "SEDAN", aliases=["i 4"])
    G("G26", "D", 5, "2022-03-01")
    V("eDrive40 M Sport", "BEV", "RWD", None, 83.9, 3999000, "CBU", "DE")

    # -------------------------------------------------------- Mercedes-Benz
    B("mercedes_benz", "Mercedes-Benz", "เมอร์เซเดส-เบนซ์", "PREMIUM_LUXURY",
      "Mercedes-Benz Group", "DE", ["benz", "เบนซ์", "mercedes"])
    M("mb_c_class", "C-Class", "ซี-คลาส", "SEDAN", aliases=["c class", "c220d", "c350e"])
    G("W206", "D", 5, "2022-01-01")
    V("C350e AMG Dynamic", "PHEV", "RWD", 1999, 25.4, 3399000, "CKD", "TH")
    M("mb_e_class", "E-Class", "อี-คลาส", "SEDAN", aliases=["e class", "e220d"])
    G("W214", "E", 5, "2024-01-01")
    V("E220d AMG Dynamic", "MHEV", "RWD", 1993, 0.9, 4290000, "CKD", "TH")
    M("mb_gla", "GLA", "จีแอลเอ", "CROSSOVER")
    G("H247", "B", 5, "2020-01-01")
    V("GLA200 AMG Dynamic", "ICE", "FWD", 1332, None, 2590000, "CKD", "TH")
    M("mb_glc", "GLC", "จีแอลซี", "CROSSOVER")
    G("X254", "D", 5, "2023-01-01")
    V("GLC300e AMG Dynamic", "PHEV", "AWD", 1999, 24.8, 4290000, "CKD", "TH")
    M("mb_eqs", "EQS", "อีคิวเอส", "SEDAN")
    G("V297", "E", 5, "2022-01-01")
    V("EQS500 4Matic AMG", "BEV", "AWD", None, 107.8, 8090000, "CKD", "TH")

    # ----------------------------------------------------------------- Audi
    B("audi", "Audi", "เอาดี้", "PREMIUM_LUXURY", "Volkswagen Group", "DE", ["เอาดี้"])
    M("audi_q3", "Q3", "คิว3", "CROSSOVER", aliases=["q 3"])
    G("F3", "C", 5, "2019-01-01")
    V("35 TFSI S line", "ICE", "FWD", 1498, None, 2799000, "CBU", "DE")
    M("audi_q5", "Q5", "คิว5", "CROSSOVER", aliases=["q 5"])
    G("FY", "D", 5, "2018-01-01")
    V("45 TFSI quattro S line", "MHEV", "AWD", 1984, 0.5, 3999000, "CBU", "DE")

    # --------------------------------------------------------------- Lexus
    B("lexus", "Lexus", "เล็กซัส", "PREMIUM_LUXURY", "Toyota Group", "JP", ["เล็กซัส"])
    M("lexus_es", "ES", "อีเอส", "SEDAN", aliases=["es300h"])
    G("XZ10", "E", 5, "2018-01-01")
    V("ES300h Grand Luxury", "HEV", "FWD", 2487, 1.0, 3690000, "CBU", "JP")
    M("lexus_nx", "NX", "เอ็นเอ็กซ์", "CROSSOVER", aliases=["nx350h", "nx450h"])
    G("AZ20", "D", 5, "2022-01-01")
    V("NX350h Premium", "HEV", "AWD", 2487, 1.0, 3690000, "CBU", "JP")
    M("lexus_rx", "RX", "อาร์เอ็กซ์", "CROSSOVER", aliases=["rx350h"])
    G("AL30", "E", 5, "2023-01-01")
    V("RX350h Premium", "HEV", "AWD", 2487, 1.0, 4790000, "CBU", "JP")
    M("lexus_lm", "LM", "แอลเอ็ม", "MPV", aliases=["lm350h", "lm500h"])
    G("AH40L", "E", 4, "2024-01-01")
    V("LM350h Executive", "HEV", "FWD", 2487, 1.0, 7990000, "CBU", "JP")

    # -------------------------------------------------------------- Porsche
    B("porsche", "Porsche", "ปอร์เช่", "PERFORMANCE", "Volkswagen Group", "DE",
      ["ปอร์เช่"])
    M("macan", "Macan", "มาคัน", "CROSSOVER")
    G("95B", "D", 5, "2019-01-01")
    V("Macan", "ICE", "AWD", 1984, None, 5300000, "CBU", "DE")
    M("cayenne", "Cayenne", "คาเยน", "SUV")
    G("E3", "E", 5, "2018-01-01")
    V("Cayenne E-Hybrid", "PHEV", "AWD", 2995, 25.9, 9500000, "CBU", "SK")
    M("porsche_911", "911", "911", "COUPE", aliases=["nine eleven"])
    G("992", "D", 4, "2019-01-01")
    V("Carrera", "ICE", "RWD", 2981, None, 12500000, "CBU", "DE")

    # ----------------------------------------------------------------- Mini
    B("mini", "MINI", "มินิ", "PREMIUM_LUXURY", "BMW Group", "GB", ["มินิ"])
    M("mini_cooper", "Cooper", "คูเปอร์", "HATCHBACK", aliases=["mini cooper"])
    G("J01", "B", 4, "2024-06-01")
    V("Cooper SE", "BEV", "FWD", None, 54.2, 2299000, "CBU", "CN")
    M("countryman", "Countryman", "คันทรีแมน", "CROSSOVER")
    G("U25", "C", 5, "2024-06-01")
    V("Countryman E", "BEV", "FWD", None, 66.5, 2799000, "CBU", "DE")


def main() -> None:
    seed_japanese()
    seed_chinese()
    seed_korean_western()
    write()


if __name__ == "__main__":
    main()
