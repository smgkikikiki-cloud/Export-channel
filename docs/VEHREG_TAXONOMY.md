# โครงสร้าง category ของ vehreg

เอกสารนี้อธิบายว่า "ทุกปัจจัย" ที่เจ้าของระบุ ถูกเก็บไว้ที่ชั้นไหน และทำไม
ชื่อ facet ทุกตัวเป็นภาษาอังกฤษเพราะมันคือชื่อคอลัมน์จริงในฐานข้อมูล

## กติกา 3 ข้อที่ทั้งระบบยึด

**1. facet แต่ละตัวเป็นอิสระต่อกัน** `segment` ไม่บอกอะไรเกี่ยวกับ `body_type`
และ `market_position` ไม่ได้เดาจากชื่อรุ่น แต่คำนวณจากราคา เมื่อทุกแกนตั้งฉากกัน
มันจึง cross กันได้ทุกคู่โดยไม่ต้องเขียนเคสพิเศษ

**2. แยกปี ไม่ยุ่งกับอดีต** catalog หนึ่งชุด = หนึ่งปี อยู่คนละโฟลเดอร์
ยอดปี 2026 ถูกจัดด้วย catalog 2026 เท่านั้น ไม่มีการอ่านข้ามปี ไม่มีการย้อนราคา
ปีที่ปิดไปแล้วไม่ขยับ ปีหน้าคือ `catalog fork` ออกมาแล้วแก้

**3. หนึ่งรุ่น = หนึ่ง body** ชื่อเดียวขายสองบอดี้ = คนละรุ่นไปเลย
(Mazda2 Sedan / Mazda2 Hatchback) กระบะก็แยกตามแค็บ
(Revo Single Cab / Smart Cab / Double Cab) เพราะแค็บเป็นตัวกำหนดประเภทจดทะเบียน

## 4 ชั้นของตัวตน (identity layers)

```
Brand  →  Model  →  Generation  →  Variant        ทั้งหมดอยู่ในปีเดียว
ยี่ห้อ     รุ่น+บอดี้    โฉม           รุ่นย่อย
```

| ชั้น | เก็บ facet อะไร | เหตุผล |
|---|---|---|
| `Brand` | `brand_segment`, `oem_group`, `brand_origin` | คงที่ทั้งยี่ห้อ |
| `Model` | `body_type`, `cab_type`, `registration_type` | นิยามว่า "รุ่นนี้คืออะไร" — ล็อกไว้ ห้าม override ที่ชั้นล่าง |
| `Generation` | `segment`, `seats` | โฉมใหม่ย้าย segment ได้ในปีเดียวกัน |
| `Variant` | `powertrain`, `drivetrain`, `engine_cc`, `battery_kwh`, `price_thb` → `market_position`, `import_type`, `origin_country` | ต่างกันในรุ่นย่อย |

### การ override เป็นชั้น ๆ

`resolve()` ไล่จากชั้นที่เฉพาะเจาะจงที่สุดออกไป — variant → generation → model →
brand — เจอค่าแรกที่ถูกกรอกก็ใช้ค่านั้น ค่าที่เป็น `None`/`""`/`UNKNOWN`
ไม่นับว่ากรอก จึงตกไปใช้ชั้นบนแทน ไม่ใช่ลบทิ้ง

ยกเว้น `body_type` กับ `cab_type` ที่ล็อกไว้ที่ชั้น model — ถ้ามีคนพยายาม override
ที่รุ่นย่อย ระบบจะฟ้องและไม่ยอมเขียนลงดิสก์ เพราะนั่นแปลว่ามันควรเป็นคนละรุ่น

ทุกค่าที่ resolve ได้ จะมี **provenance** ติดมาว่ามาจากชั้นไหน
(`python -m vehreg catalog show revo_double`)

### facet ที่คำนวณเอง ไม่เก็บ

`market_position`, `powertrain_group`, `is_electrified`, `is_plug_in`,
`is_locally_assembled` — คำนวณจาก facet อื่นทุกครั้ง จึงขัดแย้งกับต้นทางไม่ได้เลย
`registration_type` ก็ derive จาก body + cab ถ้าไม่กรอก

## Vocabulary ทั้งหมด

ดูรายการเต็มพร้อมคำแปลไทยด้วย `python -m vehreg facets`

| facet | ค่า |
|---|---|
| `segment` | A, B, C, D, E, F, UNKNOWN |
| `body_type` | HATCHBACK, SEDAN, CROSSOVER, SUV, PPV, COUPE, MPV, PICKUP, OTHER |
| `cab_type` | DOUBLE_CAB, SMART_CAB, SINGLE_CAB, NOT_APPLICABLE |
| `market_position` | ENTRY, VOLUME, UPPER, LUXURY, UNKNOWN |
| `powertrain` | ICE, MHEV, HEV, PHEV, REEV, BEV, FCEV, UNKNOWN |
| `powertrain_group` | COMBUSTION, HYBRID, ZERO_EMISSION |
| `import_type` | CBU, SKD, CKD, UNKNOWN |
| `origin_country` | ISO-2: TH, CN, ID, MY, JP, KR, IN, DE, … |
| `brand_segment` | BUDGET, MASS, PREMIUM_TECH, PERFORMANCE, PREMIUM_LUXURY |
| `registration_type` | RY1, RY2, RY3, OTHER |
| `drivetrain` | FWD, RWD, AWD, 4WD, UNKNOWN |

## กระบะ กับ ประเภทจดทะเบียน

| แค็บ | ประเภท | เหตุผล |
|---|---|---|
| Double cab (4 ประตู) | **รย.1** | กรมฯ นับเป็นรถยนต์นั่งส่วนบุคคล |
| Smart / space / club cab | รย.3 | รถยนต์บรรทุกส่วนบุคคล |
| Single cab (ตอนเดียว) | รย.3 | รถยนต์บรรทุกส่วนบุคคล |

เพราะฉะนั้น **แต่ละแค็บเป็นคนละรุ่นในระบบ** ไม่ใช่รุ่นย่อยของรุ่นเดียวกัน
ไฟล์ รย.1 กับ รย.3 ที่โหลดมาจึงแยกกันโดยธรรมชาติ และนั่นคือสิ่งที่ทำให้ระบบ
แกะออกได้ว่า `REVO` ในไฟล์ไหนหมายถึงคันไหน (ดูหัวข้อถัดไป)

PPV (Fortuner / MU-X / Pajero Sport / Everest) เป็น `body_type = PPV` และเป็น
รย.1 — ไม่ใช่กระบะ แม้จะใช้แชสซีร่วมกัน

## การจับคู่ชื่อจากไฟล์ DLT

DLT พิมพ์ `แบบรถ` มาแค่ `REVO` ไม่ได้บอกแค็บ ระบบจึงทำงานสองจังหวะ:

1. จับคู่กับ**ทุกรุ่นของยี่ห้อนั้น** — ถ้าฉลากบอกแค็บมาเอง (`REVO DOUBLE CAB`)
   ก็จบตรงนี้ และชื่อจริงของรุ่นชนะ alias ที่ระบบสร้างให้เสมอ
   (`CITY` = City ซีดาน ไม่ใช่ City Hatchback)
2. ถ้าฉลากเข้าได้หลายรุ่นเท่ากัน ใช้**ประเภทจดทะเบียนของไฟล์**ตัดสิน
   * `REVO` ในไฟล์ รย.1 → เหลือ Double Cab ตัวเดียว → จับคู่ได้
   * `REVO` ในไฟล์ รย.3 → เหลือ Single + Smart → **ไม่เดา** ส่งเข้าคิว review
     พร้อมบอกว่าตัวเลือกคืออะไรบ้าง ยอดยังถูกนับไว้ที่ระดับยี่ห้อ ไม่หายไปไหน

สอนครั้งเดียวจบ และสอนแยกตามประเภทได้:

```bash
python -m vehreg review --map "model:TOYOTA REVO=toyota.hilux_revo_smart_cab" --reg RY3
```

## 5 ข้อที่กูตัดสินใจแทน — เจ้าของต้องยืนยัน

1. **Segment F = กระบะ** ตามที่สั่ง แต่ทำให้ไม่มีที่ให้รถใหญ่มาก
   (Land Cruiser 300, LX, S-Class, Alphard) ตอนนี้วางไว้ที่ `E` ทั้งหมด
2. **ช่องว่างราคา 1.8–2.0 ล้าน** โจทย์เขียน "1–1.8 ล้าน" แล้วข้ามไป "2 ล้าน+"
   ปิดช่องที่ 1.8 ล้าน ดังนั้น `LUXURY` = 1.8 ล้านขึ้นไป
   แก้ได้ที่เดียวคือ `PRICE_BAND_EDGES` ใน `vehreg/taxonomy.py`
3. **เพิ่ม MHEV** รถ 48V ไม่ใช่ HEV จริง ถ้าไม่อยากแยก ให้กรอกเป็น ICE
4. **ราคาใน seed ยังไม่ยืนยัน** ทุกรุ่นย่อยติดโน้ต `seed-unverified`
   `python -m vehreg catalog audit` ลิสต์ให้
5. **ยังไม่มีตัวโหลดอัตโนมัติจากเว็บ DLT** ไม่เขียน scraper เดา endpoint
   เจ้าของโหลดไฟล์มาเอง แล้วระบบบันทึก sha256 + URL ที่ระบุไว้เป็นหลักฐาน

การจัดว่ารถคันไหนอยู่ segment / brand_segment ไหน เป็นของเจ้าของทั้งหมด
seed เป็นแค่จุดตั้งต้น แก้ผ่าน `catalog export` → แก้ใน Excel → `catalog import`

## ตอนนี้ seed ปี 2026 มีอะไรอยู่

28 ยี่ห้อ / 141 รุ่น / 180 รุ่นย่อย — ในนั้นเป็นกระบะ 22 รุ่น
(double cab 8 = รย.1, smart cab 7 + single cab 7 = รย.3)
