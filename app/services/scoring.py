import json
import re
from collections.abc import Collection
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from app.schemas import FieldEvidence, ResearchResult, SignalCandidate


class ScoreWeights(BaseModel):
    industry_match: int = Field(ge=0)
    company_type_match: int = Field(ge=0)
    company_size_match: int = Field(ge=0)
    sales_motion_match: int = Field(ge=0)
    growth_signal_match: int = Field(ge=0)


class ICPConfig(BaseModel):
    name: str
    industries: list[str]
    business_models: list[str]
    employee_min: int = Field(ge=1)
    employee_max: int = Field(ge=1)
    sales_motion_terms: list[str]
    manual_research_terms: list[str]
    growth_terms: list[str]
    automation_terms: list[str]
    weights: ScoreWeights

    @model_validator(mode="after")
    def validate_config(self) -> "ICPConfig":
        if self.employee_min > self.employee_max:
            raise ValueError("employee_min cannot exceed employee_max")
        if sum(self.weights.model_dump().values()) != 100:
            raise ValueError("ICP scoring weights must total 100")
        return self


class ScoreResult(BaseModel):
    industry_match: int
    company_type_match: int
    company_size_match: int
    sales_motion_match: int
    growth_signal_match: int
    total: int
    explanation: str
    signals: list[SignalCandidate]


def load_icp_config(path: Path) -> ICPConfig:
    return ICPConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))


def score_company(research: ResearchResult, config: ICPConfig) -> ScoreResult:
    company = research.company
    weights = config.weights
    evidence = research.field_evidence

    industry_confidence = _field_confidence(company.industry, evidence.industry)
    industry = _matched_field_points(
        company.industry,
        config.industries,
        weights.industry_match,
        industry_confidence,
    )
    business_confidence = _field_confidence(company.business_model, evidence.business_model)
    business_model = _business_model_points(
        company.business_model,
        config,
        weights.company_type_match,
        business_confidence,
    )
    size_confidence = _field_confidence(
        company.estimated_employee_range, evidence.estimated_employee_range
    )
    raw_size = _score_size(company.estimated_employee_range, config, weights.company_size_match)
    size = _apply_confidence(raw_size, size_confidence)

    category_confidence = {
        category: max(
            (signal.confidence for signal in research.signals if signal.category == category),
            default=0.0,
        )
        for category in ("sales_motion", "manual_research", "growth", "automation")
    }
    sales_motion_max = round(weights.sales_motion_match * 0.6)
    manual_research_max = weights.sales_motion_match - sales_motion_max
    sales = _apply_confidence(sales_motion_max, category_confidence["sales_motion"])
    sales += _apply_confidence(manual_research_max, category_confidence["manual_research"])

    growth_max = round(weights.growth_signal_match * 0.55)
    automation_max = weights.growth_signal_match - growth_max
    growth = _apply_confidence(growth_max, category_confidence["growth"])
    growth += _apply_confidence(automation_max, category_confidence["automation"])

    sales = min(sales, weights.sales_motion_match)
    growth = min(growth, weights.growth_signal_match)
    total = industry + business_model + size + sales + growth
    industry_text = _fit_text(
        industry, weights.industry_match, company.industry, industry_confidence
    )
    company_type_max = weights.company_type_match
    business_text = _fit_text(
        business_model,
        company_type_max,
        company.business_model,
        business_confidence,
    )
    if company.estimated_employee_range:
        size_text = (
            f"target {config.employee_min}-{config.employee_max}; "
            f"found {company.estimated_employee_range} "
            f"(confidence {size_confidence:.0%})"
        )
    else:
        size_text = "unknown; no reliable employee-count evidence found"
    categories = {
        category for category, confidence in category_confidence.items() if confidence >= 0.6
    }
    sales_text = _category_text(categories, ("sales_motion", "manual_research"))
    growth_text = _category_text(categories, ("growth", "automation"))
    explanation = "\n".join(
        (
            f"Industry fit: {industry}/{weights.industry_match} — {industry_text}",
            f"Business model: {business_model}/{weights.company_type_match} — {business_text}",
            f"Company size: {size}/{weights.company_size_match} — {size_text}",
            f"Sales motion: {sales}/{weights.sales_motion_match} — {sales_text}",
            f"Growth signals: {growth}/{weights.growth_signal_match} — {growth_text}",
            f"Total: {total}/100",
        )
    )
    scored_signals = [_assign_signal_points(signal, weights) for signal in research.signals]
    return ScoreResult(
        industry_match=industry,
        company_type_match=business_model,
        company_size_match=size,
        sales_motion_match=sales,
        growth_signal_match=growth,
        total=total,
        explanation=explanation,
        signals=scored_signals,
    )


def _contains_any(text: str, values: list[str]) -> bool:
    return any(value.lower() in text for value in values)


def _matched_field_points(
    value: str | None, expected: list[str], maximum: int, confidence: float
) -> int:
    if not value or value.lower() == "unknown":
        return 0
    if not _contains_any(value.lower(), expected):
        return 0
    return _apply_confidence(maximum, confidence)


def _business_model_points(
    value: str | None, config: ICPConfig, maximum: int, confidence: float
) -> int:
    if not value or value.lower() == "unknown":
        return 0
    if _contains_any(value.lower(), config.business_models):
        fit_points = maximum
    elif value in {"Software / SaaS", "B2C SaaS"}:
        fit_points = round(maximum * 0.6)
    else:
        fit_points = 0
    return _apply_confidence(fit_points, confidence)


def _field_confidence(value: str | None, evidence: FieldEvidence | None) -> float:
    if not value or value.lower() == "unknown":
        return 0.0
    # Explicit structured inputs used by callers remain trusted; extracted values carry evidence.
    return evidence.confidence if evidence else 1.0


def _apply_confidence(points: int, confidence: float) -> int:
    if confidence >= 0.8:
        return points
    if confidence >= 0.6:
        return round(points * 0.6)
    return 0


def _score_size(value: str | None, config: ICPConfig, maximum: int) -> int:
    if not value:
        return 0
    numbers = [int(number) for number in re.findall(r"\d+", value)]
    if not numbers:
        return 0
    low, high = (numbers[0], numbers[-1])
    midpoint = (low + high) / 2
    if config.employee_min <= midpoint <= config.employee_max:
        return maximum
    if high >= config.employee_min and low <= config.employee_max:
        return round(maximum * 0.75)
    distance = min(abs(high - config.employee_min), abs(low - config.employee_max))
    if distance <= 20:
        return round(maximum * 0.5)
    return 0


def _fit_text(points: int, maximum: int, value: str | None, confidence: float) -> str:
    if not value or value.lower() == "unknown":
        return "no reliable evidence found"
    if points == maximum:
        match = "matches"
    elif points:
        match = "partially matches"
    else:
        match = "does not match"
    return f"{value} {match} the configured ICP (confidence {confidence:.0%})"


def _category_text(categories: Collection[str], relevant: tuple[str, ...]) -> str:
    present = [category.replace("_", " ") for category in relevant if category in categories]
    return ", ".join(present) if present else "no reliable evidence found"


def _assign_signal_points(signal: SignalCandidate, weights: ScoreWeights) -> SignalCandidate:
    maximum = {
        "sales_motion": round(weights.sales_motion_match * 0.6),
        "manual_research": weights.sales_motion_match - round(weights.sales_motion_match * 0.6),
        "growth": round(weights.growth_signal_match * 0.55),
        "automation": weights.growth_signal_match - round(weights.growth_signal_match * 0.55),
    }.get(signal.category, 0)
    points = _apply_confidence(maximum, signal.confidence)
    # Duplicate evidence in one category is visible but does not stack in the score.
    return signal.model_copy(update={"points": points})
