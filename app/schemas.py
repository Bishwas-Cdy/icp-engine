from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

BusinessModel = Literal[
    "B2B SaaS",
    "B2C SaaS",
    "Software / SaaS",
    "Services",
    "Marketplace",
    "Ecommerce",
    "Agency / Consultancy",
    "Other",
    "Unknown",
]


class CompanyAnalyzeRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    website: HttpUrl

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("website")
    @classmethod
    def validate_public_http_url(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme not in {"http", "https"}:
            raise ValueError("website must use http or https")
        if value.username or value.password:
            raise ValueError("website URLs cannot include credentials")
        if not value.host or value.host.lower() == "localhost":
            raise ValueError("website must have a public hostname")
        return value


class SignalRead(BaseModel):
    id: int | None = None
    name: str
    evidence: str
    source_url: str | None
    confidence: float = Field(ge=0, le=1)
    points: int = Field(ge=0)

    model_config = ConfigDict(from_attributes=True)


class ScoreRead(BaseModel):
    industry_match: int
    company_type_match: int
    company_size_match: int
    sales_motion_match: int
    growth_signal_match: int
    total: int
    explanation: str

    model_config = ConfigDict(from_attributes=True)


class CompanySummary(BaseModel):
    id: int
    name: str
    website: str
    industry: str | None
    business_model: str | None
    estimated_employee_range: str | None
    target_market: str | None
    description: str | None
    analyzed_at: datetime
    score: ScoreRead

    model_config = ConfigDict(from_attributes=True)


class CompanyDetail(CompanySummary):
    signals: list[SignalRead]


class BatchItemResult(BaseModel):
    row: int
    company: CompanyDetail | None = None
    error: str | None = None


class BatchResponse(BaseModel):
    processed: int
    succeeded: int
    failed: int
    results: list[BatchItemResult]


class HealthResponse(BaseModel):
    status: str
    database: str
    llm_configured: bool


class ExtractedCompany(BaseModel):
    industry: str | None = None
    business_model: BusinessModel | None = None
    estimated_employee_range: str | None = None
    target_market: str | None = None
    description: str | None = None


class FieldEvidence(BaseModel):
    evidence: str
    source_url: str
    confidence: float = Field(ge=0, le=1)


class CompanyFieldEvidence(BaseModel):
    industry: FieldEvidence | None = None
    business_model: FieldEvidence | None = None
    estimated_employee_range: FieldEvidence | None = None
    target_market: FieldEvidence | None = None
    description: FieldEvidence | None = None


class SignalCandidate(BaseModel):
    name: str
    evidence: str
    source_url: str | None = None
    confidence: float = Field(ge=0, le=1)
    category: Literal["sales_motion", "manual_research", "growth", "automation"]
    points: int = Field(default=0, ge=0)


class ResearchResult(BaseModel):
    company: ExtractedCompany
    field_evidence: CompanyFieldEvidence = Field(default_factory=CompanyFieldEvidence)
    signals: list[SignalCandidate] = Field(default_factory=list)
