"""slowapi Limiter instance ที่ใช้ร่วมกันระหว่าง main.py และ endpoint ที่ต้อง rate-limit."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# headers_enabled=True — docs/openapi.yaml กำหนดว่าทุก 429 ต้องมี Retry-After header
# (default ของ slowapi คือ False ซึ่งจะไม่ใส่ header ใดๆ เลย)
limiter = Limiter(key_func=get_remote_address, headers_enabled=True)
