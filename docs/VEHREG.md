# vehreg — คู่มือใช้งาน

ระบบดูดยอดจดทะเบียนรถใหม่ของกรมการขนส่งทางบก แล้วแจงเป็น dynamic big data
ที่ cross ได้ทุกแกน: ยี่ห้อ × รุ่น × รุ่นย่อย × segment × body type ×
market position × powertrain × ประเทศผลิต × CBU/SKD/CKD × brand segment

**ทำงานเป็นรายปี** ตอนนี้คือปี **2026** catalog แต่ละปีแยกโฟลเดอร์กันสนิท
ไม่มีการอ่านข้ามปี ปีหน้าค่อย `catalog fork` ออกไปแก้

ใช้ Python standard library ล้วน ไม่ต้อง pip install ไม่ต้องมี server
ฐานข้อมูลเป็นไฟล์ SQLite ไฟล์เดียว

## เริ่มใช้ใน 4 คำสั่ง

```bash
python -m vehreg facets                       # ดู vocabulary ทั้งหมด
python -m vehreg init                         # ตรวจ catalog 2026 + สร้าง warehouse
python -m vehreg ingest data/raw/<ไฟล์ รย.1>.csv --registration-type RY1
python -m vehreg ingest data/raw/<ไฟล์ รย.3>.csv --registration-type RY3
python -m vehreg cube --by segment,powertrain
```

ในรีโปมีไฟล์ตัวอย่าง **สังเคราะห์** `data/raw/sample_dlt_ry{1,2,3}_2026.csv`
(สร้างจาก `tools/make_sample_data.py`) ไว้ลองท่อทั้งเส้นแบบออฟไลน์
ตัวเลขในนั้นไม่ใช่ยอดจดทะเบียนจริง อย่าเอาไปอ่านผล

## ขั้นตอนจริง

### 1. หาไฟล์ข้อมูลมาก่อน

กรมการขนส่งทางบกเผยแพร่สถิติจดทะเบียนรายเดือนที่หน้า "สถิติการขนส่ง"
และบางชุดอยู่บน data.go.th โหลดไฟล์เอง (Excel → Save As CSV UTF-8)
แล้วเก็บไว้ใน `data/raw/`

**สำคัญ:** กระบะกระจายอยู่สองไฟล์
* **รย.1** — double cab (4 ประตู) รวมอยู่กับรถยนต์นั่ง
* **รย.3** — single cab กับ smart/space cab

ต้องดึงมาทั้งคู่ถึงจะเห็นกระบะครบ และตอน ingest ต้องบอกประเภทให้ถูก
เพราะระบบใช้ประเภทนี้เป็นตัวตัดสินว่า `REVO` ในไฟล์นั้นคือแค็บไหน

### 2. ingest

รองรับสองทรง:

```bash
# ทรงยาว: หนึ่งแถวต่อหนึ่งเดือน
python -m vehreg ingest data/raw/ry1_2026.csv --registration-type RY1

# ทรงกว้าง: เดือนเป็นคอลัมน์ (ทรงที่ DLT ใช้บ่อย)
python -m vehreg ingest data/raw/ry3_2026.csv --wide --registration-type RY3
```

หัวคอลัมน์ไทย/อังกฤษเดาให้อัตโนมัติ (`เดือน`, `ยี่ห้อ`, `แบบรถ`, `จำนวน`, …)
ถ้าเดาผิดสั่งตรง ๆ ได้: `--col-period เดือน --col-brand ยี่ห้อ --col-units จำนวน`

ทุกแถวจบที่อย่างใดอย่างหนึ่งเสมอ — เป็น fact ที่จับคู่ได้ พร้อมบันทึกว่าจับคู่ด้วยวิธีไหน
คะแนนเท่าไหร่ หรือเข้าคิว review พร้อมเหตุผล **ไม่มีการเดาให้ไปลงรุ่นที่ใกล้ที่สุด**
ยอดรวมจึงกระทบยอดกับไฟล์ต้นทางได้เสมอ

ingest ไฟล์เดิมซ้ำไม่ทำให้ตัวเลขคูณสอง (มี UNIQUE key ต่อ source)
แถวที่เป็นปีอื่นซึ่งยังไม่มี catalog จะเข้าคิว `no-catalog-for-year` ไม่ถูกจัดมั่ว

### 3. เคลียร์คิว review

```bash
python -m vehreg review                       # ดูว่าอะไรจับคู่ไม่ได้ กี่คัน
python -m vehreg review --map "model:DEEPAL S05=changan.deepal_s07"

# กระบะที่ฉลากไม่บอกแค็บ: สอนแยกตามประเภทจดทะเบียนได้
python -m vehreg review --map "model:TOYOTA REVO=toyota.hilux_revo_smart_cab" --reg RY3
```

คิว review จะบอกตัวเลือกมาให้เลยเวลามันกำกวม เช่น

```
Toyota Hilux Revo   model-ambiguous: toyota.hilux_revo_single_cab | toyota.hilux_revo_smart_cab
```

สอนครั้งเดียว ครั้งต่อไปจับคู่เอง (เก็บในตาราง `alias_override`)
ระหว่างที่ยังไม่สอน ยอดไม่หาย — มันถูกนับไว้ที่ระดับยี่ห้อ (grain = BRAND)
ถ้ามันคือรถที่ยังไม่มีใน catalog ให้ไปเพิ่มใน catalog แทน (ข้อ 5)

### 4. ถามข้อมูล

```bash
# ทุก segment × powertrain
python -m vehreg cube --by segment,powertrain

# เฉพาะกระบะ แจงตามแค็บ × ประเภทจดทะเบียน × ช่วงราคา
python -m vehreg cube --by cab_type,registration_type,market_position \
    --filter body_type=PICKUP --allocate

# BEV จีน CBU เทียบ BEV ประกอบไทย
python -m vehreg cube --by brand,import_type,origin_country --filter powertrain=BEV

# รายไตรมาส / รายเดือน
python -m vehreg cube --by powertrain_group,quarter
python -m vehreg cube --by brand,period --from 2026-01 --to 2026-06

# เทียบครึ่งปี
python -m vehreg growth --by brand_segment --base 2026-01 --compare 2026-06

# ส่งออกไป Excel / Looker
python -m vehreg cube --by brand,model,powertrain,market_position --csv out.csv
```

กรองด้วย `--filter <facet>=<ค่า>[,<ค่า>]` ได้ทุก facet และ group ด้วย `--by`
ได้ทุก facet เช่นกัน รวม `period`, `quarter`, `year`, `province`, `grain`

### 5. เติม catalog (ตรงนี้คือของที่อยู่ในหัวเจ้าของ)

```bash
python -m vehreg catalog export mycars.csv     # เอาของที่มีอยู่ออกมาแก้
# หรือเริ่มจากศูนย์:
python -m vehreg catalog template mycars.csv   # ไฟล์เปล่าพร้อมตัวอย่าง 2 แถว

# กรอกใน Excel: หนึ่งแถว = หนึ่งรุ่นย่อย
python -m vehreg catalog import mycars.csv --dry-run
python -m vehreg catalog import mycars.csv
python -m vehreg init                          # rebuild dimension
```

กติกาตอนกรอกที่ต้องรู้:

* **หนึ่งชื่อรุ่น = หนึ่ง body** ถ้ากรอกชื่อเดิมแต่ body ใหม่ ระบบจะฟ้องและ
  ไม่เขียนอะไรเลย ให้ตั้งชื่อแยก เช่น `Mazda2 Sedan` กับ `Mazda2 Hatchback`
* **กระบะแยกตามแค็บ** ตั้งชื่อรุ่นแยก แล้วกรอก `cab_type` ให้ถูก
  (`SINGLE_CAB` / `SMART_CAB` / `DOUBLE_CAB`)
* **ปล่อย `registration_type` ว่างไว้** ระบบเติมให้เอง — double cab เป็น รย.1
  ที่เหลือเป็น รย.3
* **`generation` ปล่อยว่างได้** ถ้าไม่แยกโฉม
* import ซ้ำได้ปลอดภัย แถวที่ชี้รุ่นย่อยเดิมจะอัปเดตทับ ไม่สร้างซ้ำ
* ถ้าแถวไหนทำให้ catalog ผิดกติกา **ไม่เขียนลงดิสก์เลย** และบอกว่าแถวไหนผิด

คำสั่งอื่น:

```bash
python -m vehreg catalog stats                 # นับว่ามีอะไรอยู่เท่าไหร่
python -m vehreg catalog validate              # ตรวจกติกาข้ามแกนทั้งหมด
python -m vehreg catalog audit                 # ราคาไหนยังไม่ได้ยืนยัน
python -m vehreg catalog show revo_double      # ดูว่าแต่ละ facet มาจากชั้นไหน
python -m vehreg catalog years                 # มี catalog ปีไหนบ้าง
```

### 6. ขึ้นปีใหม่

```bash
python -m vehreg catalog fork --to 2027        # ก๊อป 2026 ไปเป็นจุดตั้งต้น
python -m vehreg --year 2027 catalog import newprices.csv
python -m vehreg --year 2027 init              # เพิ่ม dimension ของ 2027
```

2026 ไม่ขยับเลย ยอดปี 2026 ยังถูกจัดด้วยราคาและ segment ของปี 2026 ตลอดไป

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

`grain = BRAND` คือแถวที่รู้แค่ยี่ห้อ (จับคู่รุ่นไม่ได้หรือกำกวม)
ยอดยังอยู่ครบ แต่ตอบคำถามระดับรุ่นไม่ได้จนกว่าจะเคลียร์คิว review

ยอดรวมไม่เปลี่ยน แต่ผลลัพธ์จะบอกชัดว่ากี่คันเป็น "ค่าประมาณจากการปันส่วน"
ไม่ใช่ตัวเลขที่ต้นทางรายงานมาจริง

`python -m vehreg coverage` บอกว่าตอนนี้ข้อมูลลึกถึงรุ่นย่อยกี่ %
และเหลือค้างคิว review กี่คัน

## โครงไฟล์

```
vehreg/
  taxonomy.py       vocabulary + กติกาข้ามแกน + ช่วงราคา + กติกา รย.
  entities.py       4 ชั้น + ตัว resolve และ provenance
  catalog.py        โหลด/ตรวจ/index catalog รายปี + fork ปีใหม่
  authoring.py      import/export CSV แบบแบน
  normalize.py      fold ข้อความไทย-อังกฤษ + จับคู่ชื่อ + ตรวจความกำกวม
  db.py             SQLite: dimension รายปี + fact + คิว review
  ingest.py         DLT export → fact, ใช้ประเภท รย. ตัดสินความกำกวม
  allocate.py       ปันส่วนยอดระดับรุ่นลงรุ่นย่อย
  cube.py           cross-tab
  cli.py            `python -m vehreg`
  data/2026/models/ catalog รายยี่ห้อของปี 2026 (JSON, แก้มือได้ diff ได้)
tools/
  seed_catalog.py       สร้าง catalog 2026 ตั้งต้น (รันครั้งเดียว)
  make_sample_data.py   สร้างไฟล์ตัวอย่างสังเคราะห์ แยกตาม รย.
tests/test_vehreg.py    42 เทสต์ ออฟไลน์ล้วน
docs/VEHREG_TAXONOMY.md เหตุผลการออกแบบ + ข้อที่เจ้าของต้องตัดสินใจ
```

รันเทสต์: `python -m unittest tests.test_vehreg`

## ที่ยังไม่ได้ทำ (จงใจ)

* ไม่มีตัวโหลดอัตโนมัติจากเว็บ DLT — ไม่เดา endpoint
* ไม่มี dashboard / web UI — ออก CSV แล้วต่อ Excel หรือ Looker เอาเอง
* ไม่มีข้อมูลยอดขายจากค่าย (wholesale) — คนละตัวเลขกับยอดจดทะเบียน
* ไม่มีข้อมูลปีเก่า และไม่เทียบข้ามปีอัตโนมัติ — ถ้าจะเทียบ 2026 กับ 2027
  ต้องมี catalog ทั้งสองปีและ ingest ทั้งสองปีเข้าฐานเดียวกัน
* catalog ยังเป็นโครงตั้งต้น ราคายังไม่ยืนยัน
