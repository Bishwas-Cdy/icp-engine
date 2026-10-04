import csv
import io
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models
from app.api.dependencies import get_analysis_service
from app.core.config import Settings, get_settings
from app.db import get_db
from app.schemas import (
    BatchItemResult,
    BatchResponse,
    CompanyAnalyzeRequest,
    CompanyDetail,
    CompanySummary,
    HealthResponse,
    SignalRead,
)
from app.services.analysis import AnalysisService
from app.services.scraper import ScrapeError
from app.services.url_safety import UnsafeURLError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("Database health check failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return HealthResponse(
        status="ok", database="connected", llm_configured=bool(settings.llm_api_key)
    )


@router.post(
    "/companies/analyze",
    response_model=CompanyDetail,
    status_code=status.HTTP_201_CREATED,
    tags=["companies"],
)
async def analyze_company(
    request: CompanyAnalyzeRequest,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
) -> CompanyDetail:
    try:
        return await service.analyze(request)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ScrapeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/companies/batch", response_model=BatchResponse, tags=["companies"])
async def analyze_batch(
    file: Annotated[UploadFile, File(description="UTF-8 CSV with name and website columns")],
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BatchResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload must be a CSV file")
    raw = await file.read(1_000_001)
    if len(raw) > 1_000_000:
        raise HTTPException(status_code=413, detail="CSV exceeds 1 MB")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(content))
    fieldnames = {field.strip().lower() for field in (reader.fieldnames or [])}
    if not {"name", "website"}.issubset(fieldnames):
        raise HTTPException(status_code=400, detail="CSV must contain name and website columns")
    rows = list(reader)
    if len(rows) > settings.max_batch_rows:
        raise HTTPException(
            status_code=413, detail=f"CSV exceeds the {settings.max_batch_rows}-row limit"
        )

    results: list[BatchItemResult] = []
    for row_number, row in enumerate(rows, start=2):
        normalized = {key.strip().lower(): value for key, value in row.items() if key}
        try:
            request = CompanyAnalyzeRequest(
                name=normalized.get("name", ""), website=normalized.get("website", "")
            )
            company = await service.analyze(request)
            results.append(BatchItemResult(row=row_number, company=company))
        except (ValidationError, UnsafeURLError, ScrapeError) as exc:
            logger.info("Batch row %s failed: %s", row_number, exc)
            results.append(BatchItemResult(row=row_number, error=_friendly_error(exc)))

    succeeded = sum(item.company is not None for item in results)
    return BatchResponse(
        processed=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )


@router.get("/companies", response_model=list[CompanySummary], tags=["companies"])
async def list_companies(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[models.Company]:
    statement = (
        select(models.Company)
        .order_by(models.Company.analyzed_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).unique())


@router.get("/companies/{company_id}", response_model=CompanyDetail, tags=["companies"])
async def get_company(company_id: int, db: Annotated[Session, Depends(get_db)]) -> models.Company:
    company = db.get(models.Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.get("/companies/{company_id}/signals", response_model=list[SignalRead], tags=["companies"])
async def get_company_signals(
    company_id: int, db: Annotated[Session, Depends(get_db)]
) -> list[models.Signal]:
    if db.get(models.Company, company_id) is None:
        raise HTTPException(status_code=404, detail="Company not found")
    statement = select(models.Signal).where(models.Signal.company_id == company_id)
    return list(db.scalars(statement))


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        return str(first.get("msg", "Invalid input"))
    return str(exc)
