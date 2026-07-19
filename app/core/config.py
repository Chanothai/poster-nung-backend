"""Application settings — อ่านค่าจาก .env / environment variables ผ่าน pydantic-settings.

12-Factor: config มาจาก environment เท่านั้น — build ครั้งเดียว deploy ได้ทุก env
ห้ามใส่ค่า default ที่ดูใช้งานได้จริงสำหรับ secret (JWT_SECRET ฯลฯ) — ต้องมาจาก env
"""

from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Environment (required — fail fast ถ้าขาด/ผิดค่า) ----
    ENVIRONMENT: Literal["sit", "uat", "production"]

    # ---- Database ----
    DATABASE_URL: str

    # ---- JWT / Auth ----
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # ---- OTP / Rate-limit (Global Rule 5) ----
    OTP_RATE_LIMIT_PER_10MIN: int = 5
    OTP_MAX_ATTEMPTS: int = 5

    # ---- Reservation (F3 — ยังไม่มี consumer, เตรียม config ไว้) ----
    RESERVE_TTL_MINUTES: int = 15

    # ---- OAuth / Social login ----
    # ว่างได้ (ยังไม่ตั้งค่า) — endpoint จะ fail ด้วย error ชัดเจนแทนที่จะข้าม
    # audience check เงียบๆ ถ้าไม่ได้ตั้ง (ดู auth_service.google_login)
    GOOGLE_CLIENT_ID: str = ""

    # ---- CORS ----
    # NoDecode = ข้าม JSON-decode ของ pydantic-settings ให้ raw string ถึง validator
    # (env var เป็น comma-separated ไม่ใช่ JSON)
    CORS_ORIGINS: Annotated[list[str], NoDecode] = []

    # ---- App ----
    DEBUG: bool = False
    DOCS_ENABLED: bool = True

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, v: object) -> object:
        """รองรับค่าจาก env เป็น comma-separated string (pydantic-settings default
        บังคับ JSON สำหรับ list ซึ่งไม่สะดวกกับ env var)."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> "Settings":
        """Guardrail รวมศูนย์ที่ config layer (ไม่ใช่ if env==production กระจายใน
        business logic): production ห้ามเปิด debug/docs — misconfig ต้อง fail fast
        ตอน boot ไม่ใช่หลุดขึ้น production เงียบๆ."""
        if self.ENVIRONMENT == "production":
            if self.DEBUG:
                raise ValueError("DEBUG ต้องเป็น false ใน production")
            if self.DOCS_ENABLED:
                raise ValueError("DOCS_ENABLED ต้องเป็น false ใน production")
        return self


settings = Settings()
