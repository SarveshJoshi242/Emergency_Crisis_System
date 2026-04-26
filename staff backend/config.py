# ============================================================
#  Emergency Backend · config.py
#  Purpose: Environment settings loaded from .env
# ============================================================

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb://localhost:27017"
    DB_NAME: str = "emergency_db"
    PORT: int = 8001
    UPLOAD_DIR: str = "uploads"
    GEMINI_API_KEY: str = ""

    # ── AI Danger Detection ──────────────────────────────────────────────────
    # Number of seconds a danger level must be sustained before action is taken.
    # Prevents false positives from transient AI detection spikes.
    DANGER_SUSTAIN_SECONDS: int = 5

    # Seconds of silence after which a floor/room danger state resets.
    DANGER_STALE_SECONDS: int = 30

    # ── JWT Authentication ───────────────────────────────────────────────────
    # Generate with: python -c "import secrets; print(secrets.token_hex(64))"
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES_STAFF: int = 20
    ACCESS_TOKEN_EXPIRE_MINUTES_GUEST: int = 10
    REFRESH_TOKEN_EXPIRE_HOURS: int = 24

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
