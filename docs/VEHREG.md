# vehreg — คู่มือใช้งาน

ระบบดูดยอดจดทะเบียนรถใหม่ของกรมการขนส่งทางบก แล้วแจงเป็น dynamic big data
ที่ cross ได้ทุกแกน: ยี่ห้อ × รุ่น × รุ่นย่อย × segment × body type ×
market position × powertrain × ประเทศผลิต × CBU/SKD/CKD × brand segment

ใช้ Python standard library ล้วน ไม่ต้อง pip install ไม่ต้องมี server
ฐานข้อมูลเป็นไฟล์ SQLite ไฟล์เดียว

## เริ่มใช้ใน 4 คำสั่ง

```bash
python -m vehreg facets                       # ดู vocabulary ทั้งหมด
python -m vehreg init                         # ตรวจ catalog + สร้าง warehouse
python -m vehreg ingest data/raw/<ไฟล์ DLT>.csv
python -m vehreg cube --by segment,powertrain --from 2023-01 --to 2025-12
```

ในรีโปมีไฟล์ตัวอย่าง **สังเคราะห์** `data/raw/sample_dlt_registrations.csv`
(สร้างจาก `tools/make_sample_data.py`) ไว้ลองท่อทั้งเส้นแบบออฟไลน์
ตัวเลขในนั้นไม่ใช่ยอดจดทะเบียนจริง อย่าเอาไปอ่านผล

## ขั้นตอนจริง

### 1. หาไฟล์ข้อมูลมาก่อน

กรมการขนส่งทางบกเผยแพร่สถิติจดทะเบียนรายเดือนที่หน้า "สถิติการขนส่ง"
และบางชุดอยู่บน data.go.th โหลดไฟล์เอง (Excel → Save As CSV UTF-8)
แล้วเก็บไว้ใน `data/raw/`

**สำคัญ:** ถ้าอยากได้กระบะ (segment F) ต้องดึง **รย.3** มาด้วย
รย.1 คือรถยนต์นั่งส่วนบุคคลไม่เกิน 7 คน กระบะไม่ได้อยู่ในนั้น
ตอน ingest ระบุด้วย `--registration-type RY3`

### 2. ingest

รองรับสองทรง:

```bash
# ทรงยาว: หนึ่งแถวต่อหนึ่งเดือน
python -m vehreg ingest data/raw/ry1_2023.csv --registration-type RY1

# ทรงกว้าง: เดือนเป็นคอลัมน์ (ทรงที่ DLT ใช้บ่อย)
python -m vehreg ingest data/raw/ry3_2023.csv --wide --registration-type RY3
```

หัวคอลัมน์ไทย/อังกฤษเดาให้อัตโนมัติ (`เดือน`, `ยี่ห้อ`, `แบบรถ`, `จำนวน`, …)
ถ้าเดาผิดสั่งตรง ๆ ได้: `--col-period เดือน --col-brand ยี่ห้อ --col-units จำนวน`

ทุกแถวจบที่อย่างใดอย่างหนึ่งเสมอ — เป็น fact ที่จับคู่ได้ พร้อมบันทึกว่าจับคู่ด้วยวิธีไหน
คะแนนเท่าไหร่ หรือเข้าคิว review พร้อมเหตุผล **ไม่มีการเดาให้ไปลงรุ่นที่ใกล้ที่สุด**
ยอดรวมจึงกระทบยอดกับไฟล์ต้นทางได้เสมอ

ingest ไฟล์เดิมซ้ำไม่ทำให้ตัวเลขคูณสอง (มี UNIQUE key ต่อ source)

### 3. เคลียร์คิว review

```bash
python -m vehreg review                       # ดูว่าอะไรจับคู่ไม่ได้ กี่คัน
python -m vehreg review --map "model:DEEPAL S05=changan.deepal_s07"
```

สอนครั้งเดียว ครั้งต่อไปจับคู่เอง (เก็บในตาราง `alias_override`)
ถ้ามันคือรถที่ยังไม่มีใน catalog ให้ไปเพิ่มใน catalog แทน (ข้อ 5)

### 4. ถามข้อมูล

```bash
# ทุก segment × powertrain ปี 2025
python -m vehreg cube --by segment,powertrain --from 2025-01 --to 2025-12

# เฉพาะกระบะ แจงตามแค็บ × ช่วงราคา
python -m vehreg cube --by cab_type,market_position --filter body_type=PICKUP

# BEV จีน CBU เทียบ BEV ประกอบไทย
python -m vehreg cube --by brand,import_type,origin_country \
    --filter powertrain=BEV --from 2024-01 --to 2025-12

# รายไตรมาส
python -m vehreg cube --by powertrain_group,quarter --from 2023-01

# โต 2 ปี
python -m vehreg growth --by brand_segment --base 2023 --compare 2025

# ส่งออกไป Excel / Looker
python -m vehreg cube --by brand,model,powertrain,market_position --csv out.csv
```

กรองด้วย `--filter <facet>=<ค่า>[,<ค่า>]` ได้ทุก facet และ group ด้วย `--by`
ได้ทุก facet เช่นกัน รวม `period`, `quarter`, `year`, `province`, `grain`

### 5. เติม catalog (ตรงนี้คือของที่อยู่ในหัวเจ้าของ)

```bash
python -m vehreg catalog template mycars.csv   # ได้ไฟล์เปล่าพร้อมตัวอย่าง
# กรอกใน Excel หนึ่งแถว = หนึ่งรุ่นย่อย หนึ่งช่วงราคา
python -m vehreg catalog import mycars.csv --dry-run
python -m vehreg catalog import mycars.csv
python -m vehreg init                          # rebuild dimension
```

import ซ้ำได้ปลอดภัย: แถวที่ชี้รุ่นย่อยเดิมจะอัปเดตทับ ไม่สร้างซ้ำ
และแถวที่ `start` ใหม่กว่าจะกลายเป็น **period ใหม่** ไม่ทับราคาเดิม
(ราคาย้อนหลังจึงไม่หาย — ยอดปี 2023 ยังถูกจัดตามราคาปี 2023)

ถ้าแถวไหนทำให้ catalog ผิดกติกา ระบบจะไม่เขียนลงดิสก์เลยและบอกว่าแถวไหนผิด

คำสั่งอื่น:

```bash
python -m vehreg catalog stats                 # นับว่ามีอะไรอยู่เท่าไหร่
python -m vehreg catalog validate              # ตรวจกติกาข้ามแกนทั้งหมด
python -m vehreg catalog audit                 # ราคาไหนยังไม่ได้ยืนยัน
python -m vehreg catalog show yaris_ativ       # ดูว่าแต่ละ facet มาจากชั้นไหน
python -m vehreg catalog export flat.csv       # แบนออกมาทั้ง catalog
```

## เรื่อง grain กับ MIXED — อ่านก่อนเชื่อตัวเลข

DLT ประกาศละเอียดสุดแค่ระดับ "แบบรถ" ไม่ใช่รุ่นย่อย ทุก fact จึงบันทึกว่ามันมาถึง
ระดับไหน (`BRAND` / `MODEL` / `VARIANT`)

เวลา cross แกนที่รุ่นหนึ่งมีหลายค่า (เช่น Corolla Cross มีทั้ง ICE และ HEV)
แถวระดับ MODEL จะรายงานเป็น `MIXED` **ไม่ใช่เดาเลือกข้างใดข้างหนึ่ง**

ถ้าอยากให้แตกออกมา ใช้สัดส่วนที่ข้อมูลชุดนั้นเองแสดงไว้:

```bash
python -m vehreg allocate --fallback year      # คำนวณ mix จากแถวระดับรุ่นย่อยที่มี
python -m vehreg cube --by powertrain --allocate
```

ยอดรวมไม่เปลี่ยน แต่ผลลัพธ์จะบอกชัดว่ากี่คันเป็น "ค่าประมาณจากการปันส่วน"
ไม่ใช่ตัวเลขที่ต้นทางรายงานมาจริง

`python -m vehreg coverage` บอกว่าตอนนี้ข้อมูลลึกถึงรุ่นย่อยกี่ %
และเหลือค้างคิว review กี่คัน

## โครงไฟล์

```
vehreg/
  taxonomy.py     vocabulary + กติกาข้ามแกน + ช่วงราคา
  entities.py     5 ชั้น + ตัว resolve และ provenance
  catalog.py      โหลด/ตรวจ/index catalog
  authoring.py    import/export CSV แบบแบน
  normalize.py    fold ข้อความไทย-อังกฤษ + จับคู่ชื่อ
  db.py           SQLite: dimension แบบ type-2 + fact + คิว review
  ingest.py       DLT export → fact
  allocate.py     ปันส่วนยอดระดับรุ่นลงรุ่นย่อย
  cube.py         cross-tab
  cli.py          `python -m vehreg`
  data/models/    catalog รายยี่ห้อ (JSON, แก้มือได้ diff ได้)
tools/
  seed_catalog.py       สร้าง catalog ตั้งต้น (รันครั้งเดียว)
  make_sample_data.py   สร้างไฟล์ตัวอย่างสังเคราะห์
tests/test_vehreg.py    32 เทสต์ ออฟไลน์ล้วน
docs/VEHREG_TAXONOMY.md เหตุผลการออกแบบ + ข้อที่เจ้าของต้องตัดสินใจ
```

รันเทสต์: `python -m unittest tests.test_vehreg`

## ที่ยังไม่ได้ทำ (จงใจ)

* ไม่มีตัวโหลดอัตโนมัติจากเว็บ DLT — ไม่เดา endpoint
* ไม่มี dashboard / web UI — ออก CSV แล้วต่อ Excel หรือ Looker เอาเอง
* ไม่มีข้อมูลยอดขายจากค่าย (wholesale) — คนละตัวเลขกับยอดจดทะเบียน
* catalog ยังเป็นโครงตั้งต้น ราคายังไม่ยืนยัน
