import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required for the PostgreSQL layer")
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url

def make_engine(url: str | None = None):
    return create_engine(url or database_url(), pool_pre_ping=True)

SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)
