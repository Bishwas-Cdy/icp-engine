from pathlib import Path

from app.services.extraction import extract_website_facts
from app.services.research import research_website
from app.services.scoring import load_icp_config
from app.services.scraper import ScrapedPage


def test_strong_saas_language_outweighs_isolated_marketplace_word() -> None:
    result = extract_website_facts(
        "Acme",
        [
            _page(
                "Our customer platform includes CRM software, marketing software, and sales "
                "software. Explore our marketplace integrations."
            )
        ],
    )

    assert result.company.business_model == "B2B SaaS"
    assert result.company.industry == "Software / SaaS"
    assert result.field_evidence.business_model is not None
    assert result.field_evidence.business_model.confidence >= 0.8


def test_isolated_marketplace_word_does_not_classify_company_as_marketplace() -> None:
    result = extract_website_facts(
        "Acme",
        [_page("Read customer stories, visit our marketplace, and contact the team.")],
    )

    assert result.company.business_model == "Unknown"
    assert result.field_evidence.business_model is None


def test_explicit_b2b_saas_language_is_classified_as_b2b_saas() -> None:
    result = extract_website_facts(
        "Acme",
        [_page("A B2B SaaS platform built for revenue teams and enterprise customers.")],
    )

    assert result.company.business_model == "B2B SaaS"
    assert result.company.industry == "Software / SaaS"


def test_navigation_only_growth_words_do_not_create_growth_signal() -> None:
    config = load_icp_config(Path("config/default_icp.json")).model_copy(
        update={"growth_terms": ["careers", "jobs", "investor relations", "join our team"]}
    )
    baseline = extract_website_facts(
        "Acme", [_page("Products Pricing Careers Investor Relations Join our team")]
    )

    result = research_website(
        [_page("Products Pricing Careers Investor Relations")], baseline, config
    )

    assert all(signal.category != "growth" for signal in result.signals)


def test_signal_evidence_is_concise_contextual_and_sourced() -> None:
    page = _page(
        f"{'Menu item ' * 80}Book a demo to discuss your revenue workflow with our sales team."
    )
    config = load_icp_config(Path("config/default_icp.json"))
    result = research_website([page], extract_website_facts("Acme", [page]), config)
    signal = next(item for item in result.signals if item.category == "sales_motion")

    assert "Book a demo" in signal.evidence
    assert "demo-led or sales-led" in signal.evidence
    assert len(signal.evidence.split()) < 40
    assert signal.source_url == page.url


def _page(text: str) -> ScrapedPage:
    return ScrapedPage(
        url="https://example.com/",
        title="Acme",
        description=None,
        text=text,
    )
