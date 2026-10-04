from pathlib import Path

import pytest

from app.schemas import (
    CompanyFieldEvidence,
    ExtractedCompany,
    FieldEvidence,
    ResearchResult,
    SignalCandidate,
)
from app.services.scoring import ICPConfig, load_icp_config, score_company


@pytest.fixture
def icp() -> ICPConfig:
    return load_icp_config(Path("config/default_icp.json"))


def test_full_match_scores_100(icp: ICPConfig) -> None:
    research = ResearchResult(
        company=ExtractedCompany(
            industry="B2B software",
            business_model="B2B SaaS",
            estimated_employee_range="30-39",
            target_market="Sales teams",
            description="Technology for go-to-market teams",
        ),
        signals=[
            _signal("Demo", "sales_motion"),
            _signal("Research", "manual_research"),
            _signal("Hiring", "growth"),
            _signal("RevOps", "automation"),
        ],
    )
    result = score_company(research, icp)
    assert result.total == 100
    assert result.company_size_match == 20
    assert "Total: 100/100" in result.explanation


def test_unknown_evidence_does_not_get_free_points(icp: ICPConfig) -> None:
    result = score_company(ResearchResult(company=ExtractedCompany()), icp)
    assert result.total == 0
    assert "no reliable evidence found" in result.explanation


def test_unknown_industry_cannot_borrow_points_from_description(icp: ICPConfig) -> None:
    research = ResearchResult(
        company=ExtractedCompany(
            industry=None,
            business_model="Marketplace",
            estimated_employee_range=None,
            target_market="Enterprise",
            description="CRM software and SaaS tools for enterprise businesses",
        )
    )

    result = score_company(research, icp)

    assert result.industry_match == 0
    assert result.company_size_match == 0
    assert "Industry fit: 0/25 — no reliable evidence found" in result.explanation
    assert "Company size: 0/20 — unknown" in result.explanation
    assert "Industry fit: 25/25 — no reliable evidence found" not in result.explanation


def test_weak_field_confidence_receives_only_partial_points(icp: ICPConfig) -> None:
    research = ResearchResult(
        company=ExtractedCompany(industry="Software / SaaS"),
        field_evidence=CompanyFieldEvidence(
            industry=FieldEvidence(
                evidence="We build software.",
                source_url="https://example.com",
                confidence=0.65,
            )
        ),
    )

    result = score_company(research, icp)

    assert result.industry_match == 15
    assert "Industry fit: 15/25" in result.explanation
    assert "confidence 65%" in result.explanation


def test_duplicate_category_signals_do_not_stack(icp: ICPConfig) -> None:
    research = ResearchResult(
        company=ExtractedCompany(),
        signals=[_signal("Demo one", "sales_motion"), _signal("Demo two", "sales_motion")],
    )
    result = score_company(research, icp)
    assert result.sales_motion_match == 12


def _signal(name: str, category: str) -> SignalCandidate:
    return SignalCandidate(
        name=name,
        evidence=f"Evidence for {name}",
        source_url="https://example.com",
        confidence=0.9,
        category=category,
    )
