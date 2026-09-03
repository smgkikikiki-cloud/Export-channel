# โครงสร้าง category ของ vehreg

เอกสารนี้อธิบายว่า "ทุกปัจจัย" ที่เจ้าของระบุ ถูกเก็บไว้ที่ชั้นไหน และทำไม
ชื่อ facet ทุกตัวเป็นภาษาอังกฤษเพราะมันคือชื่อคอลัมน์จริงในฐานข้อมูล

## หลักการเดียวที่ทั้งระบบยึด

**facet แต่ละตัวเป็นอิสระต่อกัน** `segment` ไม่บอกอะไรเกี่ยวกับ `body_type`
และ `market_position` ไม่ได้เดาจากชื่อรุ่น แต่คำนวณจากราคา ณ เดือนนั้น
เมื่อทุกแกนตั้งฉากกัน มันจึง cross กันได้ทุกคู่โดยไม่ต้องเขียนเคสพิเศษ
`--by segment,powertrain,import_type,brand_segment` ทำงานได้เหมือนกันหมด

## 5 ชั้นของตัวตน (identity layers)

```
Brand  →  Model  →  Generation  →  Variant  →  VariantPeriod (มีวันที่)
ยี่ห้อ     รุ่น        โฉม           รุ่นย่อย      ช่วงราคา/ช่วงการนำเข้า
```

| ชั้น | เก็บ facet อะไร | เหตุผล |
|---|---|---|
| `Brand` | `brand_segment`, `oem_group`, `brand_origin` | คงที่ทั้งยี่ห้อ |
| `Model` | `body_type`, `registration_type` | Yaris เป็นแฮทช์แบ็กเสมอ |
| `Generation` | `segment`, `seats` | โฉมใหม่ย้าย segment ได้ ไม่ควรทับประวัติเดิม |
| `Variant` | `powertrain`, `drivetrain`, `engine_cc`, `battery_kwh`, `cab_type` | ต่างกันในรุ่นย่อยเดียวกัน |
| `VariantPeriod` | `price_thb` → `market_position`, `import_type`, `origin_country`, `model_year` | เปลี่ยนได้ระหว่างที่รุ่นย่อยเดิมยังขายอยู่ |

### การ override เป็นชั้น ๆ

`resolve()` ไล่จากชั้นที่เฉพาะเจาะจงที่สุดออกไป — period → variant → generation
→ model → brand — เจอค่าแรกที่ถูกกรอกก็ใช้ค่านั้น ค่าที่เป็น `None`/`""`/`UNKNOWN`
ไม่นับว่ากรอก จึงตกไปใช้ชั้นบนแทน ไม่ใช่ลบทิ้ง

ผลคือกรอกข้อมูลตรงชั้นที่มันจริงได้เลย เช่น
* Mazda2 เป็น `SEDAN` ที่ระดับ model แต่รุ่นย่อย Hatchback override เป็น `HATCHBACK`
* Hilux Revo เป็น `PICKUP` ที่ระดับ model ส่วน `cab_type` อยู่ที่รุ่นย่อย
  (ตอนเดียว / แค็บ / 4 ประตู)
* ถ้าวันหนึ่ง Toyota GR ต้องเป็น `PERFORMANCE` ก็ override `brand_segment`
  ที่ระดับ variant ได้โดยไม่ต้องแตกยี่ห้อใหม่

ทุกค่าที่ resolve ได้ จะมี **provenance** ติดมาว่ามาจากชั้นไหน
(`python -m vehreg catalog show yaris_ativ` แสดงให้ดูทีละบรรทัด)

### facet ที่คำนวณเอง ไม่เก็บ

`powertrain_group`, `is_electrified`, `is_plug_in`, `is_locally_assembled`,
`market_position` — คำนวณจาก facet อื่นทุกครั้ง จึงขัดแย้งกับต้นทางไม่ได้เลย

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
| `registration_type` | RY1, RY2, RY3, RY12, OTHER |
| `drivetrain` | FWD, RWD, AWD, 4WD, UNKNOWN |

## กติกาข้ามแกน (cross-facet rules)

ตรวจอัตโนมัติทุกครั้งที่ validate หรือ import แล้วบล็อกไม่ให้เขียนลงดิสก์ถ้าผิด

* `body_type = PICKUP` ⇔ `segment = F` และต้องมี `cab_type`
* `cab_type` ใช้ได้เฉพาะกับ PICKUP
* `BEV` ห้ามมี `engine_cc`; `PHEV`/`REEV` ต้องมีทั้ง `engine_cc` และ `battery_kwh`
* `ICE` ล้วน ห้ามมี `battery_kwh`
* `CKD`/`SKD` ต้องมี `origin_country = TH`
* กระบะควรเป็น `RY3` ไม่ใช่ `RY1`
* ช่วง period ของรุ่นย่อยเดียวกันต้องไม่ทับกันและไม่มีช่องว่าง

## 7 ข้อที่กูตัดสินใจแทน — เจ้าของต้องยืนยัน

1. **รย.1 ไม่ครอบคลุมกระบะ** รย.1 คือรถยนต์นั่งส่วนบุคคลไม่เกิน 7 คน
   กระบะจดเป็น รย.3 ส่วน PPV (Fortuner / MU-X / Pajero Sport) ส่วนใหญ่อยู่ รย.1
   ถ้าดึงเฉพาะ รย.1 segment F จะหายไปทั้งหมด ระบบจึงเก็บ `registration_type`
   เป็นคอลัมน์จริง และ ingest ได้ทั้ง รย.1/รย.2/รย.3 — **ต้องดึง รย.3 มาด้วย**
2. **Segment F = กระบะ** ตามที่สั่ง แต่ทำให้ไม่มีที่ให้รถใหญ่มาก
   (Land Cruiser 300, LX, S-Class, Alphard) ตอนนี้กูวางไว้ที่ `E` ทั้งหมด
   ถ้าอยากแยก ต้องเพิ่มค่าใหม่ (เช่น `G`) ไม่ใช่ยัดกลับเข้า F
3. **ช่องว่างราคา 1.8–2.0 ล้าน** โจทย์เขียน "1–1.8 ล้าน" แล้วข้ามไป "2 ล้าน+"
   กูปิดช่องที่ 1.8 ล้าน ดังนั้น `LUXURY` = 1.8 ล้านขึ้นไป
   แก้ได้ที่เดียวคือ `PRICE_BAND_EDGES` ใน `vehreg/taxonomy.py`
4. **เพิ่ม MHEV** รถ 48V เยอะขึ้นเรื่อย ๆ และมันไม่ใช่ HEV จริง
   ถ้าไม่อยากแยก ให้จัดเป็น ICE ตอนกรอก แล้วมันจะไม่โผล่มาเอง
5. **ราคาใน seed ยังไม่ยืนยัน** ทุก period ติดโน้ต `seed-unverified`
   `python -m vehreg catalog audit` ลิสต์ให้ว่าเหลืออันไหนต้องเช็ค
6. **DLT ไม่ประกาศถึงรุ่นย่อย** ข้อมูลสาธารณะละเอียดสุดคือระดับ "แบบรถ"
   ระบบจึงบันทึก grain ของทุกแถว และรายงาน `MIXED` อย่างซื่อสัตย์
   จนกว่าจะมี allocation profile (ดู `docs/VEHREG.md`)
7. **ยังไม่มีตัวโหลดอัตโนมัติจากเว็บ DLT** กูไม่เขียน scraper เดา endpoint
   เจ้าของโหลดไฟล์มาเอง แล้ว ingest บันทึก sha256 + URL ที่ระบุไว้เป็นหลักฐาน

## ตอนนี้ seed มีอะไรอยู่

28 ยี่ห้อ / 127 รุ่น / 176 รุ่นย่อย ครอบคลุมแบรนด์หลักที่ขายในไทยปี 2023–2025
เป็นโครงตั้งต้น ไม่ใช่ฐานข้อมูลสมบูรณ์ — เติมด้วย
`python -m vehreg catalog import <ไฟล์.csv>` ทีละหลายร้อยแถวได้
