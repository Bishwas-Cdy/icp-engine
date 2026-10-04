from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import get_db
from app.services.analysis import AnalysisService


async def get_analysis_service(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnalysisService:
    return AnalysisService(db, settings)
