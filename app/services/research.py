from typing import Literal

from app.schemas import ResearchResult, SignalCandidate
from app.services.scoring import ICPConfig
from app.services.scraper import ScrapedPage

SignalCategory = Literal["sales_motion", "manual_research", "growth", "automation"]


def research_website(
    pages: list[ScrapedPage], baseline: ResearchResult, config: ICPConfig
) -> ResearchResult:
    definitions: tuple[tuple[str, SignalCategory, list[str], str], ...] = (
        (
            "Demo or sales-led motion",
            "sales_motion",
            config.sales_motion_terms,
            "a demo-led or sales-led buying motion",
        ),
        (
            "Manual prospect research",
            "manual_research",
            config.manual_research_terms,
            "prospect or account research work",
        ),
        (
            "Hiring or funding growth",
            "growth",
            config.growth_terms,
            "active hiring, funding, or company expansion",
        ),
        (
            "GTM automation opportunity",
            "automation",
            config.automation_terms,
            "a GTM workflow that could benefit from automation",
        ),
    )
    signals: list[SignalCandidate] = []
    for name, category, terms, rationale in definitions:
        evidence = _find_evidence(pages, terms, category)
        if evidence:
            snippet, source_url, term = evidence
            signals.append(
                SignalCandidate(
                    name=name,
                    evidence=f"{snippet} — “{term}” supports {rationale}.",
                    source_url=source_url,
                    confidence=0.85,
                    category=category,
                )
            )
    return baseline.model_copy(update={"signals": signals})


def _find_evidence(
    pages: list[ScrapedPage], terms: list[str], category: SignalCategory
) -> tuple[str, str, str] | None:
    weak_growth_terms = {"careers", "jobs", "investor relations", "join our team"}
    for page in pages:
        lowered = page.text.lower()
        for term in terms:
            if term.lower() not in lowered:
                continue
            if category == "growth" and term.lower().strip() in weak_growth_terms:
                continue
            return _evidence_snippet(page.text, term), page.url, term
    return None


def _evidence_snippet(text: str, term: str) -> str:
    index = text.lower().find(term.lower())
    matched_term = text[index : index + len(term)]
    words_before = text[:index].split()[-10:]
    words_after = text[index + len(term) :].split()[:12]
    snippet = " ".join([*words_before, matched_term, *words_after]).strip()
    return f"…{snippet}…" if words_before or words_after else snippet
