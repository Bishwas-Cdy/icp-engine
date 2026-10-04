from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import Base, engine

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="SignalForge",
    version="0.1.0",
    description="Evidence-backed B2B lead intelligence and configurable ICP scoring.",
    lifespan=lifespan,
)
app.include_router(router)
