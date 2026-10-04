import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.core.config import Settings
from app.services.url_safety import UnsafeURLError, validate_public_url

logger = logging.getLogger(__name__)


class ScrapeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScrapedPage:
    url: str
    title: str | None
    description: str | None
    text: str
    links: tuple[str, ...] = ()


class WebsiteScraper:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def fetch(self, website: str) -> list[ScrapedPage]:
        root = self._normalize_url(website)
        await validate_public_url(root)
        timeout = httpx.Timeout(self.settings.scrape_timeout_seconds)
        headers = {"User-Agent": "SignalForge/0.1 (+lead-research; respectful crawler)"}
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            homepage = await self._fetch_page(client, root)
            pages = [homepage]
            for link in self._priority_links(homepage.links, homepage.url):
                if len(pages) >= self.settings.scrape_max_pages:
                    break
                try:
                    pages.append(await self._fetch_page(client, link))
                except (ScrapeError, UnsafeURLError) as exc:
                    logger.info("Skipping secondary page %s: %s", link, exc)
            return pages

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> ScrapedPage:
        current_url = url
        for redirect_count in range(6):
            await validate_public_url(current_url)
            for attempt in range(self.settings.scrape_retries + 1):
                try:
                    async with client.stream("GET", current_url) as response:
                        if response.status_code >= 500 and attempt < self.settings.scrape_retries:
                            should_retry = True
                            redirect_target = None
                            page = None
                        elif response.is_redirect:
                            should_retry = False
                            location = response.headers.get("location")
                            if redirect_count == 5 or not location:
                                raise ScrapeError("Too many redirects")
                            redirect_target = urljoin(current_url, location)
                            page = None
                        else:
                            should_retry = False
                            redirect_target = None
                            page = await self._read_page(response)
                    if should_retry:
                        await asyncio.sleep(0.2 * (2**attempt))
                        continue
                    if redirect_target:
                        current_url = redirect_target
                        break
                    if page:
                        return page
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt >= self.settings.scrape_retries:
                        raise ScrapeError(f"Website request failed: {exc}") from exc
                    await asyncio.sleep(0.2 * (2**attempt))
            else:
                raise ScrapeError("Website request failed after retries")
        raise ScrapeError("Too many redirects")

    async def _read_page(self, response: httpx.Response) -> ScrapedPage:
        if response.status_code >= 400:
            raise ScrapeError(f"Website returned HTTP {response.status_code}")
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            raise ScrapeError("URL did not return HTML")
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = 0
            if declared_length > self.settings.scrape_max_bytes:
                raise ScrapeError("Website response exceeds size limit")

        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > self.settings.scrape_max_bytes:
                raise ScrapeError("Website response exceeds size limit")
        return self._parse_page(str(response.url), bytes(body))

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlsplit(url)
        return parsed._replace(path=parsed.path or "/", fragment="").geturl()

    @staticmethod
    def _parse_page(url: str, body: bytes) -> ScrapedPage:
        soup = BeautifulSoup(body, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else None
        meta = soup.find("meta", attrs={"name": "description"})
        description = str(meta.get("content", "")).strip() if meta else None
        links = tuple(
            str(anchor.get("href"))
            for anchor in soup.find_all("a", href=True)
            if anchor.get("href")
        )
        for element in soup(["script", "style", "noscript", "svg", "nav", "header", "footer"]):
            element.decompose()
        text = " ".join(soup.stripped_strings)
        return ScrapedPage(
            url=url,
            title=title,
            description=description,
            text=text[:100_000],
            links=links,
        )

    @staticmethod
    def _priority_links(links: tuple[str, ...], root_url: str) -> list[str]:
        root_host = urlsplit(root_url).hostname
        priorities = ("about", "company", "pricing", "careers", "jobs")
        selected: list[str] = []
        for href in links:
            absolute = urljoin(root_url, href)
            parsed = urlsplit(absolute)
            if parsed.hostname != root_host or parsed.scheme not in {"http", "https"}:
                continue
            if any(term in parsed.path.lower() for term in priorities):
                clean_url = parsed._replace(fragment="").geturl()
                if clean_url not in selected and clean_url != root_url:
                    selected.append(clean_url)
        return selected
