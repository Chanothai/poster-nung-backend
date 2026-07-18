# Docker Commands Reference

> คำสั่ง Docker/Compose ที่ใช้จริงในโปรเจกต์นี้ — รวมไว้ที่เดียวให้ copy-paste ได้
> เรื่อง **นโยบาย/สถาปัตยกรรม** (ทำไม base+override, 12-factor, secrets) อยู่ที่
> [`.claude/rules/environments.md`](../.claude/rules/environments.md) — ไฟล์นี้เน้น
> **คำสั่ง** ล้วนๆ

---

## ไฟล์ที่เกี่ยวข้อง

| ไฟล์ | หน้าที่ |
|---|---|
| `Dockerfile` | build image เดียว ใช้ได้ทุก environment (build once, deploy many) |
| `docker-compose.yml` | base stack — service `app` + `db` |
| `docker-compose.dev.yml` | override สำหรับ dev แบบ hot-reload (volume mount + `--reload`) |
| `docker-compose.sit.yml` / `.uat.yml` / `.production.yml` | override ต่อ environment ตอน deploy |
| `.dockerignore` | กัน `.git/`, `.env*`, `tests/`, secrets ฯลฯ หลุดเข้า image |

---

## 1. Local Development

มี 2 แบบ เลือกใช้ตามสะดวก — **ไม่ต้องรันพร้อมกัน**

### 1.1 รัน uvicorn บนเครื่อง + db ใน container (เบาสุด, default)
```bash
docker compose up -d db          # PostgreSQL อย่างเดียว ที่ localhost:5432
source venv/bin/activate
uvicorn app.main:app --reload    # รันบนเครื่องตรงๆ, reload จาก IDE/filesystem ปกติ
```
`.env` ตั้ง `DATABASE_URL=...@localhost:5432/...` ไว้สำหรับโหมดนี้อยู่แล้ว

### 1.2 รันทุกอย่างใน container พร้อม hot-reload
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```
- mount `app/`, `alembic/`, `alembic.ini` เป็น volume — แก้โค้ดบนเครื่องแล้ว container reload ให้เองทันที ไม่ต้อง rebuild image
- ใช้เมื่อไม่อยากตั้ง Python env บนเครื่อง หรืออยากทดสอบว่ารันใน container จริงได้
- ใช้ `db` container/volume เดียวกับข้อ 1.1 (ไม่สร้างซ้ำ)
- รันแบบ background: เติม `-d`

---

## 2. คำสั่งที่ใช้บ่อย (day-to-day)

> ตัวอย่างด้านล่างใช้ค่า default (`docker compose up -d db` หรือ dev override) —
> ถ้ากำลังทำงานกับ environment อื่น ต้องแนบ `-f docker-compose.<env>.yml --env-file .env.<env>` ด้วยเสมอ (ดู §4)

| ต้องการ | คำสั่ง |
|---|---|
| ดู container ที่รันอยู่ | `docker compose ps` |
| ดู log แบบ real-time | `docker compose logs -f app` |
| ดู log ของ db | `docker compose logs -f db` |
| เข้าไปรันคำสั่งใน container | `docker compose exec app <command>` |
| เปิด shell ใน container | `docker compose exec app sh` |
| restart service เดียว (ไม่ rebuild) | `docker compose restart app` |
| หยุด (คง container/volume ไว้) | `docker compose stop` |
| หยุด + ลบ container (คง volume/data ไว้) | `docker compose down` |
| rebuild image หลังแก้ `requirements.txt`/`Dockerfile` | `docker compose up -d --build` |

---

## 3. Migration / Database

รันผ่าน `exec` เข้า container ที่มีโค้ด/alembic (เช่น dev override ข้อ 1.2):
```bash
# ดู revision ปัจจุบัน
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec app alembic current

# สร้าง migration ใหม่จาก model ที่แก้ (autogenerate) — sync กลับมาที่ host ผ่าน volume mount
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec app \
  alembic revision --autogenerate -m "add xxx column"

# apply migration ล่าสุด
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec app alembic upgrade head
```
เข้า psql ตรงๆ:
```bash
docker compose exec db psql -U poster_nung_app -d poster_nung_db
```

> ⚠️ **ห้ามรัน `alembic downgrade` หรือ `DROP TABLE` โดยไม่ถาม** (CLAUDE.md Global Rule 7)

---

## 4. Build & Deploy ต่อ Environment

Image เดียว build ครั้งเดียว (CI ทำให้ tag=git sha) แล้ว promote sha เดิมข้าม sit → uat → production — รายละเอียด flow เต็มอยู่ที่ [`environments.md`](../.claude/rules/environments.md)

### Build เอง (local, ไม่ผ่าน CI)
```bash
docker build -t posternung:local .
```

### Deploy (รันบน target host — pull image ที่ CI build ไว้ ไม่ build ใหม่)
```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.<env>.yml \
  --env-file .env.<env> \
  pull app

docker compose \
  -f docker-compose.yml \
  -f docker-compose.<env>.yml \
  --env-file .env.<env> \
  up -d --no-build
```
`<env>` = `sit` / `uat` / `production` — ต้องมีไฟล์ `.env.<env>` (secret, gitignored) provision ไว้ที่ host ก่อน (ดู manual checklist ใน `environments.md`)

ดู log ของ environment ที่ deploy อยู่:
```bash
docker compose -f docker-compose.yml -f docker-compose.<env>.yml --env-file .env.<env> logs -f app
```

---

## 5. Troubleshooting

| อาการ | สาเหตุที่พบบ่อย | แก้ |
|---|---|---|
| `port is already allocated` | มี stack อื่นรัน port 8000/5432 ค้างอยู่ (เช่น dev + sit พร้อมกัน) | `docker ps` ดูว่าตัวไหนถือ port อยู่ แล้ว `docker compose down` ตัวที่ไม่ใช้ |
| แก้ `requirements.txt` แล้วโค้ด/dep ไม่อัปเดตใน container | image ยัง cache layer เก่า (`up` เฉยๆ ไม่ rebuild) | `docker compose up -d --build` |
| dev hot-reload ไม่ทำงาน | รัน `docker compose up` แบบไม่มี `-f docker-compose.dev.yml` (ใช้ base เฉยๆ ไม่มี volume mount/`--reload`) | เช็คว่าแนบ `-f docker-compose.dev.yml` ครบ |
| app ต่อ db ไม่ได้ตอนรันใน container (`localhost` refused) | `.env`'s `DATABASE_URL` ชี้ `localhost` (ใช้กับ uvicorn บน host) แต่ container ต้องใช้ hostname `db` | ใช้ dev override (ตั้ง `DATABASE_URL` ให้แล้ว) หรือดู `.env.<env>` |
| migration fail ตอน container start | DB ยังไม่ healthy ตอน app เริ่ม | เช็ค `depends_on: db: condition: service_healthy` ยังอยู่ในไฟล์ที่ merge (base มีอยู่แล้ว) |

---

## 6. คำสั่งอันตราย — อ่านก่อนรัน

คำสั่งกลุ่มนี้ **ลบข้อมูลจริง** อย่าใช้บนเครื่องที่มี dev data ที่ยังต้องใช้ โดยเฉพาะห้ามรันบน sit/uat/production เด็ดขาดโดยไม่ถามก่อน

| คำสั่ง | ผลกระทบ |
|---|---|
| `docker compose down -v` | ลบ **volume** ด้วย — ข้อมูลใน Postgres หายทั้งหมด |
| `docker volume rm <name>` | ลบ volume เจาะจง — ตรวจชื่อให้ดีก่อน (`docker volume ls`) |
| `docker system prune -a` | ลบ image/container/network ที่ไม่ได้ใช้ **ทั้งเครื่อง** ไม่ใช่แค่โปรเจกต์นี้ |
| `docker compose exec db psql ... -c "DROP TABLE ..."` | ตรงตัว — ห้ามโดยไม่ถามตาม CLAUDE.md |

ถ้าต้องการ "เริ่ม dev db ใหม่จากศูนย์" แบบตั้งใจ (ยอมรับว่า data หาย):
```bash
docker compose down -v      # ลบ container + volume ของ default project เท่านั้น
docker compose up -d db     # สร้างใหม่ (migration ต้องรันใหม่หลังจากนี้)
```
