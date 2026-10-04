import httpx
import pytest

from app.core.config import Settings
from app.services import scraper as scraper_module
from app.services.scraper import ScrapeError, WebsiteScraper


@pytest.mark.asyncio
async def test_fetches_prioritized_same_site_link(monkeypatch: pytest.MonkeyPatch) -> None:
    async def allow_test_url(_: str) -> None:
        return None

    monkeypatch.setattr(scraper_module, "validate_public_url", allow_test_url)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/about":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body>About our team of 35 employees</body></html>",
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text='<html><body>Home <a href="/about">About</a></body></html>',
        )

    service = WebsiteScraper(Settings(scrape_max_pages=2), httpx.MockTransport(handler))
    pages = await service.fetch("https://example.com")

    assert [page.url for page in pages] == ["https://example.com/", "https://example.com/about"]
    assert "35 employees" in pages[1].text


@pytest.mark.asyncio
async def test_stops_response_at_byte_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def allow_test_url(_: str) -> None:
        return None

    monkeypatch.setattr(scraper_module, "validate_public_url", allow_test_url)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"x" * 10_001,
        )

    settings = Settings(scrape_max_bytes=10_000, scrape_retries=0)
    service = WebsiteScraper(settings, httpx.MockTransport(handler))

    with pytest.raises(ScrapeError, match="size limit"):
        await service.fetch("https://example.com")


@pytest.mark.asyncio
async def test_navigation_text_is_not_treated_as_page_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def allow_test_url(_: str) -> None:
        return None

    monkeypatch.setattr(scraper_module, "validate_public_url", allow_test_url)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=(
                "<html><body><nav>Marketplace Careers Investor Relations</nav>"
                "<main>CRM software for revenue teams.</main></body></html>"
            ),
        )

    service = WebsiteScraper(Settings(scrape_max_pages=1), httpx.MockTransport(handler))
    page = (await service.fetch("https://example.com"))[0]

    assert page.text == "CRM software for revenue teams."
