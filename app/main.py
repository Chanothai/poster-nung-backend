"""FastAPI entrypoint — wiring router, exception handlers, rate-limit middleware."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.auth import router as auth_router
from app.core.exceptions import AppError
from app.core.limiter import limiter

app = FastAPI(title="Poster Nung API", version="0.1.0")

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.include_router(auth_router, prefix="/api/v1")


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {"field": ".".join(str(p) for p in err["loc"][1:]), "message": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "ข้อมูลที่ส่งมาไม่ถูกต้อง",
            "details": details,
        },
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    # แยก error_code ตาม endpoint ตาม docs/api-contract-f1-f3.md §5
    if request.url.path.endswith("/verify-otp"):
        error_code = "OTP_RATE_LIMITED"
        message = "ขอรหัส OTP บ่อยเกินไป กรุณาลองใหม่ภายหลัง"
    else:
        error_code = "LOGIN_RATE_LIMITED"
        message = "พยายามเข้าสู่ระบบบ่อยเกินไป กรุณาลองใหม่ภายหลัง"

    response = JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error_code": error_code, "message": message, "details": None},
    )
    return limiter._inject_headers(response, request.state.view_rate_limit)
