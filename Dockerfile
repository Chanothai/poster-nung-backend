# syntax=docker/dockerfile:1
# Build once → deploy many. Image เดียว (tag = git sha) ใช้ได้ทุก env
# behavior ต่าง env มาจาก environment variable ตอน runtime เท่านั้น (12-Factor)
FROM python:3.13-slim

# ป้องกัน .pyc + ให้ log ออกทันที (ไม่ buffer) เหมาะกับ container
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ติดตั้ง dependencies ก่อน copy code (cache layer ดีขึ้น)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy เฉพาะสิ่งที่ runtime ต้องใช้
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

# รัน migration ก่อน serve — fail ถ้า migrate ไม่ผ่าน (ไม่ serve ของพัง)
# DATABASE_URL/ENVIRONMENT ฯลฯ inject ตอน deploy ผ่าน env var (ไม่ bake เข้า image)
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
