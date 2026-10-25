import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/portaria.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
if (
    DATABASE_URL.startswith("postgresql+psycopg://")
    and "sslmode=" not in DATABASE_URL
    and "localhost" not in DATABASE_URL
    and "127.0.0.1" not in DATABASE_URL
):
    sep = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = f"{DATABASE_URL}{sep}sslmode=require"

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-key")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "FRAncisca_0154")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
TZ = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo"))


def agora() -> datetime:
    """Data/hora local (sem fuso) no fuso configurado."""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)
