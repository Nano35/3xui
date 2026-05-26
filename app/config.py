import os
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Telegram Bot
    BOT_TOKEN: str = "7272715477:AAF3IQ1xs-bSybAM7_5KhRv4K8OBSvIV56E"  # Default from x-ui_shop_bot for fallback/dev
    ADMIN_IDS: List[int] = Field(default_factory=lambda: [1703779981])
    SUPPORT_USERNAME: str = "@frumos_r"
    DEFAULT_LANGUAGE: str = "ru"
    AGREEMENT_URL: str = "https://telegra.ph/PUBLICHNAYA-OFERTA-05-21-16"
    PRIVACY_URL: str = "https://telegra.ph/POLITIKA-KONFIDENCIALNOSTI-05-21-38"

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        elif isinstance(v, int):
            return [v]
        return v

    @field_validator("WEB_URL", mode="before")
    @classmethod
    def parse_web_url(cls, v):
        if isinstance(v, str):
            if "localhost" in v:
                return v.replace("localhost", "127.0.0.1")
        return v

    # Database
    DATABASE_MODE: str = "sqlite"  # "sqlite" or "postgresql"
    DATABASE_URL: Optional[str] = None  # Full SQL connection string, overrides default builders
    SQLITE_PATH: str = "./data/bot.db"
    
    # PostgreSQL parameters (used if DATABASE_MODE == "postgresql" and DATABASE_URL is not set)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "ultra_vpn"
    POSTGRES_USER: str = "Frumos"
    POSTGRES_PASSWORD: str = "1DrOLCKBEnk!"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # 3x-ui Panel Config
    XUI_API_URL: str = "https://heklet.duckdns.org:25383/ri2iwdueW3RtyB5GPx"
    XUI_AUTH_TYPE: str = "api_key"  # "api_key" or "basic_auth"
    XUI_API_KEY: Optional[str] = "k7Zls0l5PiL9dWkBU1KyKGNEvX5Xq46Omy4lg6tfimtiO60g"
    XUI_USERNAME: Optional[str] = "Fl3NtFy40z"
    XUI_PASSWORD: Optional[str] = "nPb0iYXJHr"
    XUI_LIMIT_IP: int = 15

    # YooKassa Gateway
    YOOKASSA_ENABLED: bool = True
    YOOKASSA_SHOP_ID: str = "1349395"
    YOOKASSA_SECRET_KEY: str = "test_Ba6BS3FTl0PK_iJE2L6omkbu5hJnCH5s0YC0IK_BWgM"

    # CryptoBot Gateway
    CRYPTOBOT_ENABLED: bool = False
    CRYPTOBOT_API_TOKEN: str = ""
    CRYPTOBOT_TESTNET: bool = True

    # Telegram Stars Gateway
    TELEGRAM_STARS_ENABLED: bool = False

    # TON Gateway
    TON_ENABLED: bool = False
    TON_WALLET: str = ""

    # USDT TRC20 Gateway
    USDT_TRC20_ENABLED: bool = False
    USDT_TRC20_WALLET: str = ""

    # RollyPay Gateway
    ROLLYPAY_ENABLED: bool = True
    ROLLYPAY_API_KEY: str = "rpk_test_api_key_placeholder"
    ROLLYPAY_SIGNING_SECRET: str = "rpk_test_signing_secret_placeholder"
    ROLLYPAY_TERMINAL_ID: str = "rpk_test_terminal_id_placeholder"

    # JWT Settings (for Admin UI)
    JWT_SECRET: str = "8kgpsTHeJ2GoUhYcyc"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 1 day

    # Web App Settings
    WEB_HOST: str = "0.0.0.0"
    WEB_PORT: int = 8080
    WEB_URL: str = "http://localhost:8080"  # Public address of this server

    # Billing Rules
    TRIAL_DURATION_DAYS: int = 3
    TRIAL_TRAFFIC_LIMIT_GB: int = 10
    REFERRAL_PERCENT: int = 30
    REFERRAL_MIN_DEPOSIT_KOPEKS: int = 10000
    SYNC_INTERVAL_SECONDS: int = 3600
    
    # Admin Credentials
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.DATABASE_MODE == "postgresql":
            return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        else:
            # For aiosqlite, SQLite needs to be prefixed with sqlite+aiosqlite://
            # Create directory for SQLite if it doesn't exist
            db_dir = os.path.dirname(self.SQLITE_PATH)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            return f"sqlite+aiosqlite:///{self.SQLITE_PATH}"

settings = Settings()
