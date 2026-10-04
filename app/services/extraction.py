import re
from dataclasses import dataclass

from app.schemas import (
    CompanyFieldEvidence,
    ExtractedCompany,
    FieldEvidence,
    ResearchResult,
)
from app.services.scraper import ScrapedPage

EMPLOYEE_PATTERNS = (
    re.compile(
        r"(?:team of|over|more than)\s+(\d{2,5})\s+(?:employees|people|team members)",
        re.I,
    ),
    re.compile(r"(\d{2,5})\+?\s+(?:employees|people|team members)", re.I),
)

BUSINESS_MODEL_TERMS: dict[str, tuple[tuple[str, int], ...]] = {
    "B2B SaaS": (
        ("b2b saas", 15),
        ("software as a service", 8),
        ("crm software", 7),
        ("sales software", 6),
        ("marketing software", 6),
        ("customer platform", 5),
        ("software for businesses", 7),
        ("software for companies", 7),
        ("business software", 5),
    ),
    "B2C SaaS": (
        ("consumer software", 7),
        ("consumer app", 6),
        ("for consumers", 6),
        ("personal subscription", 6),
    ),
    "Software / SaaS": (
        ("saas", 5),
        ("software platform", 5),
        ("cloud software", 5),
        ("subscription software", 5),
        ("software", 2),
    ),
    "Services": (
        ("managed services", 6),
        ("professional services", 5),
        ("it services", 6),
    ),
    "Marketplace": (
        ("two-sided marketplace", 8),
        ("online marketplace", 7),
        ("connects buyers and sellers", 8),
        ("buy and sell", 6),
        ("marketplace", 1),
    ),
    "Ecommerce": (
        ("ecommerce platform", 7),
        ("e-commerce platform", 7),
        ("online store", 5),
        ("shopping cart", 5),
    ),
    "Agency / Consultancy": (
        ("digital agency", 7),
        ("marketing agency", 7),
        ("consulting firm", 7),
        ("consultancy", 6),
    ),
}

INDUSTRY_TERMS: dict[str, tuple[tuple[str, int], ...]] = {
    "Financial technology": (("fintech", 8), ("financial technology", 8)),
    "Healthcare technology": (("healthtech", 8), ("healthcare software", 8)),
    "Information technology": (("information technology", 7), ("it services", 7)),
}

TARGET_MARKET_TERMS: dict[str, tuple[tuple[str, int], ...]] = {
    "Sales and revenue teams": (
        ("sales teams", 6),
        ("revenue teams", 6),
        ("go-to-market teams", 6),
    ),
    "SMB and mid-market": (("small businesses", 6), ("mid-market", 6), ("smb", 5)),
    "Enterprise": (("enterprise customers", 6), ("enterprise teams", 6)),
}


@dataclass(frozen=True)
class Candidate:
    label: str
    evidence: str
    source_url: str
    score: float
    confidence: float


def extract_website_facts(name: str, pages: list[ScrapedPage]) -> ResearchResult:
    homepage = pages[0]
    business = _best_candidate(pages, BUSINESS_MODEL_TERMS, minimum_score=4)
    industry = _best_candidate(pages, INDUSTRY_TERMS, minimum_score=4)
    if business and business.label in {"B2B SaaS", "B2C SaaS", "Software / SaaS"}:
        software_industry = Candidate(
            label="Software / SaaS",
            evidence=business.evidence,
            source_url=business.source_url,
            score=business.score,
            confidence=business.confidence,
        )
        if industry is None or software_industry.score > industry.score:
            industry = software_industry

    target_market = _best_candidate(pages, TARGET_MARKET_TERMS, minimum_score=4)
    employee = _employee_candidate(pages)
    description, description_evidence = _description_candidate(name, homepage)

    company = ExtractedCompany(
        industry=industry.label if industry else None,
        business_model=business.label if business else "Unknown",
        estimated_employee_range=employee.label if employee else None,
        target_market=target_market.label if target_market else None,
        description=description,
    )
    evidence = CompanyFieldEvidence(
        industry=_field_evidence(industry),
        business_model=_field_evidence(business),
        estimated_employee_range=_field_evidence(employee),
        target_market=_field_evidence(target_market),
        description=description_evidence,
    )
    return ResearchResult(company=company, field_evidence=evidence)


def _best_candidate(
    pages: list[ScrapedPage],
    definitions: dict[str, tuple[tuple[str, int], ...]],
    minimum_score: float,
) -> Candidate | None:
    candidates: list[Candidate] = []
    for label, weighted_terms in definitions.items():
        score = 0.0
        strongest: tuple[str, ScrapedPage, float] | None = None
        for page_index, page in enumerate(pages):
            page_weight = 1.0 if page_index == 0 else 0.85
            lowered = page.text.lower()
            for term, weight in weighted_terms:
                if term in lowered:
                    weighted_score = weight * page_weight
                    score += weighted_score
                    if strongest is None or weighted_score > strongest[2]:
                        strongest = (term, page, weighted_score)
        if score >= minimum_score and strongest:
            term, page, _ = strongest
            candidates.append(
                Candidate(
                    label=label,
                    evidence=_sentence_snippet(page.text, term),
                    source_url=page.url,
                    score=score,
                    confidence=min(0.98, 0.5 + score / 20),
                )
            )
    return max(candidates, key=lambda candidate: candidate.score, default=None)


def _employee_candidate(pages: list[ScrapedPage]) -> Candidate | None:
    for page in pages:
        for pattern in EMPLOYEE_PATTERNS:
            match = pattern.search(page.text)
            if match:
                size = int(match.group(1))
                low = max(1, (size // 10) * 10)
                return Candidate(
                    label=f"{low}-{low + 9}",
                    evidence=_sentence_snippet(page.text, match.group(0)),
                    source_url=page.url,
                    score=10,
                    confidence=0.95,
                )
    return None


def _description_candidate(
    name: str, homepage: ScrapedPage
) -> tuple[str | None, FieldEvidence | None]:
    if homepage.description:
        return homepage.description, FieldEvidence(
            evidence=homepage.description,
            source_url=homepage.url,
            confidence=0.95,
        )
    cleaned = homepage.text.strip()
    if not cleaned:
        return None, None
    snippet = _word_window(cleaned, 40)
    return f"{name}: {snippet}", FieldEvidence(
        evidence=snippet,
        source_url=homepage.url,
        confidence=0.55,
    )


def _field_evidence(candidate: Candidate | None) -> FieldEvidence | None:
    if not candidate:
        return None
    return FieldEvidence(
        evidence=candidate.evidence,
        source_url=candidate.source_url,
        confidence=candidate.confidence,
    )


def _sentence_snippet(text: str, phrase: str, max_words: int = 32) -> str:
    sentences = re.split(r"(?<=[.!?])\s+|[\r\n]+", text)
    sentence = next(
        (candidate.strip() for candidate in sentences if phrase.lower() in candidate.lower()),
        "",
    )
    if sentence:
        words = sentence.split()
        if len(words) <= max_words:
            return sentence
        return _phrase_window(sentence, phrase)
    return _phrase_window(text, phrase)


def _phrase_window(text: str, phrase: str) -> str:
    index = text.lower().find(phrase.lower())
    matched_phrase = text[index : index + len(phrase)]
    words_before = text[:index].split()[-10:]
    words_after = text[index + len(phrase) :].split()[:12]
    snippet = " ".join([*words_before, matched_phrase, *words_after]).strip()
    return f"…{snippet}…" if words_before or words_after else snippet


def _word_window(text: str, max_words: int) -> str:
    words = text.split()
    snippet = " ".join(words[:max_words])
    return f"{snippet}…" if len(words) > max_words else snippet
