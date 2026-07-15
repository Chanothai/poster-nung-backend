# API Contract — F1–F3 (Poster Nung Backend)

> สรุปภาษาคนของ [`openapi.yaml`](./openapi.yaml) — spec ฉบับเต็ม (paths/schemas/security) อยู่ในไฟล์นั้น
> Schema ฐานข้อมูลอ้างอิงที่ [`database-design.md`](./database-design.md)
> ขอบเขต: **F1 Authentication · F2 Poster Catalog · F3 Cart & Reservation** (contract-first ก่อนเขียน FastAPI code จริง)

---

## 1. Convention ที่ใช้ทุก endpoint

- **Base path:** `/api/v1`
- **Auth:** `Authorization: Bearer <access_token>` (JWT) — endpoint ที่ต้อง login ระบุไว้ในตารางด้านล่าง
- **Error envelope (ใช้กับทุก 4xx/5xx แบบเดียวกันหมด):**
  ```json
  {
    "error_code": "POSTER_NOT_AVAILABLE",
    "message": "โปสเตอร์นี้ถูกจองหรือขายไปแล้ว",
    "details": null
  }
  ```
  `details` เป็น array ของ `{field, message}` เฉพาะกรณี `422 VALIDATION_ERROR` เท่านั้น นอกนั้นเป็น `null`
- **429 ทุกตัว** ใส่ header `Retry-After` (วินาที) มาด้วย

---

## 2. Endpoint Table

### Auth — `/auth` (public)

| Method | Path | Request body | Success | Error status → code |
|---|---|---|---|---|
| POST | `/auth/register` | `email, password, phone?` | `201` UserResponse | `409` EMAIL_ALREADY_REGISTERED · `422` VALIDATION_ERROR |
| POST | `/auth/verify-otp` | `email, code` | `200` TokenResponse *(verify ผ่าน = auto-login)* | `400` OTP_INVALID · `400` OTP_EXPIRED · `429` OTP_LOCKED · `429` OTP_RATE_LIMITED · `404` USER_NOT_FOUND |
| POST | `/auth/login` | `email, password` | `200` TokenResponse | `401` INVALID_CREDENTIALS · `403` ACCOUNT_NOT_VERIFIED · `429` LOGIN_RATE_LIMITED |
| POST | `/auth/refresh` | `refresh_token` | `200` TokenResponse | `401` REFRESH_TOKEN_INVALID |

### Posters — `/posters` (public)

| Method | Path | Query params | Success | Error status → code |
|---|---|---|---|---|
| GET | `/posters` | `era_decade?, condition_grade?, min_price?, max_price?, in_stock_only?, limit=20(max100), offset=0` | `200` `{items[], total, limit, offset}` | `422` VALIDATION_ERROR |
| GET | `/posters/{poster_id}` | — | `200` PosterDetailResponse | `404` POSTER_NOT_FOUND |

### Cart — `/cart` ⚠️ ต้อง login (Bearer JWT)

| Method | Path | Success | Error status → code |
|---|---|---|---|
| POST | `/cart/reserve/{poster_id}` | `201` ReservationResponse | `401` UNAUTHORIZED · `404` POSTER_NOT_FOUND · **`409` POSTER_NOT_AVAILABLE** · `429` RESERVE_RATE_LIMITED |
| DELETE | `/cart/reservation/{reservation_id}` | `204` No Content | `401` UNAUTHORIZED · `403` FORBIDDEN · `404` RESERVATION_NOT_FOUND · `409` RESERVATION_NOT_ACTIVE |

---

## 3. Error Code Catalog (รวมทุก endpoint — FE เปิดตารางเดียวจับ error ได้ครบ)

| error_code | HTTP | เกิดที่ endpoint | ความหมาย |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | ทุก endpoint ที่รับ body/query | field ไม่ผ่าน validation — ดู `details[]` |
| `EMAIL_ALREADY_REGISTERED` | 409 | `POST /auth/register` | email ซ้ำในระบบ |
| `OTP_INVALID` | 400 | `POST /auth/verify-otp` | กรอกรหัส OTP ผิด |
| `OTP_EXPIRED` | 400 | `POST /auth/verify-otp` | รหัส OTP หมดอายุ |
| `OTP_LOCKED` | 429 | `POST /auth/verify-otp` | กรอกผิดเกิน 5 ครั้งของ**โค้ดเดียว** → โค้ดนั้นถูก invalidate ต้องขอใหม่ |
| `OTP_RATE_LIMITED` | 429 | `POST /auth/verify-otp` | ขอโค้ดใหม่เกิน 5 ครั้ง/10 นาที |
| `USER_NOT_FOUND` | 404 | `POST /auth/verify-otp` | ไม่พบ user ตาม email |
| `INVALID_CREDENTIALS` | 401 | `POST /auth/login` | email/password ผิด (ข้อความเดียวกันทั้ง 2 กรณี กัน enumeration) |
| `ACCOUNT_NOT_VERIFIED` | 403 | `POST /auth/login` | ยังไม่ยืนยัน OTP |
| `LOGIN_RATE_LIMITED` | 429 | `POST /auth/login` | login ถี่เกินไป |
| `REFRESH_TOKEN_INVALID` | 401 | `POST /auth/refresh` | token ผิด/หมดอายุ/ถูก revoke |
| `POSTER_NOT_FOUND` | 404 | `GET /posters/{id}`, `POST /cart/reserve/{id}` | ไม่มีโปสเตอร์นี้ |
| `UNAUTHORIZED` | 401 | ทุก endpoint ที่ต้อง login | ไม่มี/token ผิด |
| **`POSTER_NOT_AVAILABLE`** | **409** | `POST /cart/reserve/{id}` | **โปสเตอร์ถูกจอง/ขายไปแล้ว — ผลตรงของ concurrency defense (`FOR UPDATE`)** |
| `RESERVE_RATE_LIMITED` | 429 | `POST /cart/reserve/{id}` | จองถี่เกินไป |
| `FORBIDDEN` | 403 | `DELETE /cart/reservation/{id}` | ไม่ใช่เจ้าของ reservation (ownership check) |
| `RESERVATION_NOT_FOUND` | 404 | `DELETE /cart/reservation/{id}` | ไม่มี reservation นี้ |
| `RESERVATION_NOT_ACTIVE` | 409 | `DELETE /cart/reservation/{id}` | ยกเลิกซ้ำ/หมดอายุ/converted ไปแล้ว |

รวม **18 error_code**

---

## 4. จุดวิกฤต — `409 POSTER_NOT_AVAILABLE`

`POST /cart/reserve/{poster_id}` คือ endpoint ที่แปลง race-condition defense จาก [`database-design.md` §6](./database-design.md#6-race-condition-strategy-f3--หัวใจของ-design) เป็น HTTP contract โดยตรง:

1. Service เปิด transaction เดียว → `SELECT status FROM posters WHERE id=:id FOR UPDATE`
2. ถ้า `status != 'available'` → rollback → คืน **409 POSTER_NOT_AVAILABLE**
3. ถ้า available → update เป็น `reserved` + insert `reservations` (status=`active`, expires_at=+15min) → คืน **201**

**Acceptance test ที่ต้องมี (ตาม CLAUDE.md F3):** ยิง `POST /cart/reserve/{poster_id}` พร้อมกัน 2 request (คนละ user) ไปยัง poster เดียวกัน → ต้องได้ `201` แค่ 1 ฝั่ง อีกฝั่งได้ `409 POSTER_NOT_AVAILABLE` เท่านั้น (ห้ามได้ `500` จาก unique-violation ที่ไม่ได้ catch — DB partial unique index เป็นแค่ safety net ชั้นที่ 2 ไม่ใช่ error path หลัก)

---

## 5. จุดวิกฤต — `429` ของ OTP (2 ความหมายที่ต้องแยก)

| สถานการณ์ | error_code | trigger จาก |
|---|---|---|
| ผู้ใช้กรอกรหัส OTP ผิดซ้ำๆ กับโค้ดเดียวกัน | `OTP_LOCKED` | `otp_codes.attempt_count >= 5` ของ row เดียว → invalidate โค้ดนั้น |
| ผู้ใช้กดขอ OTP ใหม่ถี่เกินไป | `OTP_RATE_LIMITED` | นับจำนวน row ใน `otp_codes` ของ user ใน window 10 นาที ≥ 5 |

ทั้งคู่คืน HTTP 429 เหมือนกัน แต่ **`error_code` ต้องต่างกัน** เพราะ FE ต้องแสดงข้อความ/ปุ่ม action ต่างกัน (LOCKED → ให้กดขอรหัสใหม่, RATE_LIMITED → ให้รอ `Retry-After`)

---

## 6. Schema สรุป (รายละเอียดเต็มใน `openapi.yaml` → `components.schemas`)

- **Request:** `RegisterRequest`, `LoginRequest`, `OTPVerifyRequest`, `RefreshRequest`
- **Response:** `UserResponse` (ไม่มี `hashed_password`), `TokenResponse`, `PosterListItem`, `PosterDetailResponse` (extends `PosterListItem` + authenticity/provenance/images), `PaginatedPosterList`, `ReservationResponse`
- **Error:** `ErrorResponse{error_code, message, details}`, `ValidationErrorDetail{field, message}`
- **Enum ที่ใช้ตรงกับ `database-design.md`:** `PosterStatus`, `ReservationStatus`, `PosterCondition`

---

## 7. Verification checklist

- [ ] Lint `docs/openapi.yaml` ผ่าน (`npx @redocly/cli lint docs/openapi.yaml` หรือ validator อื่น)
- [ ] เปิด spec ใน Swagger Editor / VS Code OpenAPI preview — ทุก path มี response ตรงตามตารางข้อ 2
- [ ] `409 POSTER_NOT_AVAILABLE` และ `429 OTP_LOCKED` / `429 OTP_RATE_LIMITED` มี error_code แยกกันชัดเจนตามข้อ 4–5
- [ ] เทียบ field ใน schema กับ `database-design.md` ตรงกัน (โดยเฉพาะ enum `condition_grade`/`poster_condition`)
- [ ] ไม่มี field รหัสผ่าน/บัตร/CVV หลุดเข้า response schema ใดๆ
