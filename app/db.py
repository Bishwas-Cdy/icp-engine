from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict[str, object]:
    return {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}


settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    **_engine_kwargs(settings.database_url),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def get_db() -> AsyncGenerator[Session, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
