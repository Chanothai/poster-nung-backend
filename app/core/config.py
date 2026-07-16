"""Application settings — อ่านค่าจาก .env ผ่าน pydantic-settings.

ห้ามใส่ค่า default ที่ดูใช้งานได้จริงสำหรับ secret (JWT_SECRET ฯลฯ) — ต้องมาจาก .env เท่านั้น
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- Database ----
    DATABASE_URL: str

    # ---- JWT / Auth ----
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # ---- App ----
    DEBUG: bool = False


settings = Settings()
