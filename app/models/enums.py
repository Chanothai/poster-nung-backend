"""Python enums ที่ map ตรงกับ PostgreSQL ENUM types (ดู docs/database-design.md §3).

ค่าต้องตรงกับ openapi.yaml components.schemas เป๊ะ — เป็น contract เดียวกัน
"""

import enum


class PosterStatus(str, enum.Enum):
    available = "available"
    reserved = "reserved"
    sold = "sold"


class ReservationStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    converted = "converted"


class OtpPurpose(str, enum.Enum):
    registration = "registration"
    login = "login"


class PosterCondition(str, enum.Enum):
    mint = "mint"
    near_mint = "near_mint"
    very_fine = "very_fine"
    fine = "fine"
    very_good = "very_good"
    good = "good"
    fair = "fair"
    poor = "poor"


class OAuthProvider(str, enum.Enum):
    google = "google"
