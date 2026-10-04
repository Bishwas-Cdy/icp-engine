from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_analysis_service
from app.core.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.services.analysis import AnalysisService
from app.services.scraper import ScrapedPage, ScrapeError


class FakeScraper:
    async def fetch(self, website: str) -> list[ScrapedPage]:
        if "unreachable" in website:
            raise ScrapeError("Website request failed")
        return [
            ScrapedPage(
                url=website,
                title="Acme Revenue AI",
                description="B2B SaaS automation for sales and revenue teams.",
                text=(
                    "Acme is a B2B SaaS software platform for sales teams. "
                    "Our team of 36 employees "
                    "helps account executives automate manual account research and GTM workflows. "
                    "Book a demo. We are hiring—join our team."
                ),
            )
        ]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        llm_api_key=None,
        icp_config_path=Path("config/default_icp.json"),
        max_batch_rows=10,
    )


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
async def client(db: Session, settings: Settings) -> AsyncGenerator[AsyncClient, None]:
    async def override_db() -> AsyncGenerator[Session, None]:
        yield db

    async def override_settings() -> Settings:
        return settings

    async def override_service() -> AnalysisService:
        return AnalysisService(db, settings, scraper=FakeScraper())  # type: ignore[arg-type]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_analysis_service] = override_service
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()
