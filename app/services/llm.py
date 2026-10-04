import asyncio
import json
import logging
import re

import httpx

from app.core.config import Settings
from app.schemas import ResearchResult
from app.services.scraper import ScrapedPage

logger = logging.getLogger(__name__)


class LLMResearcher:
    """Optional interpretation layer for any OpenAI-compatible chat endpoint."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.settings.llm_api_key)

    async def research(
        self,
        name: str,
        pages: list[ScrapedPage],
        baseline: ResearchResult,
    ) -> ResearchResult:
        if not self.configured:
            return baseline

        source_text = "\n\n".join(f"SOURCE URL: {page.url}\n{page.text[:20_000]}" for page in pages)
        prompt = (
            f"Analyze {name} using only the supplied website text. Fill unknown fields with null. "
            "Signals must quote concise evidence from the text and use one supplied source URL. "
            "For each non-null company field, include field_evidence with an exact supporting "
            "excerpt, its supplied source URL, and confidence. "
            "Use only these categories: sales_motion, manual_research, growth, automation. "
            "Do not score the company. Existing deterministic extraction: "
            f"{baseline.model_dump_json()}\n\n{source_text}"
        )
        schema = ResearchResult.model_json_schema()
        payload = {
            "model": self.settings.llm_model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You extract evidence-backed B2B company intelligence as strict JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "company_research", "strict": True, "schema": schema},
            },
        }
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.llm_base_url.rstrip("/"),
                headers=headers,
                timeout=self.settings.llm_timeout_seconds,
                transport=self.transport,
            ) as client:
                for attempt in range(self.settings.llm_retries + 1):
                    try:
                        response = await client.post("/chat/completions", json=payload)
                        transient = response.status_code == 429 or response.status_code >= 500
                        if transient and attempt < self.settings.llm_retries:
                            await asyncio.sleep(0.5 * (2**attempt))
                            continue
                        response.raise_for_status()
                        break
                    except (httpx.TimeoutException, httpx.NetworkError):
                        if attempt >= self.settings.llm_retries:
                            raise
                        await asyncio.sleep(0.5 * (2**attempt))
            content = response.json()["choices"][0]["message"]["content"]
            parsed = ResearchResult.model_validate(json.loads(content))
            return self._merge_and_filter(baseline, parsed, pages)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("LLM research failed; using deterministic extraction: %s", exc)
            return baseline

    @staticmethod
    def _merge_and_filter(
        baseline: ResearchResult, llm_result: ResearchResult, pages: list[ScrapedPage]
    ) -> ResearchResult:
        allowed_urls = {page.url for page in pages}
        page_text = {page.url: page.text.lower() for page in pages}
        filtered = []
        for signal in llm_result.signals:
            if not signal.source_url:
                continue
            if signal.source_url not in allowed_urls:
                continue
            if signal.evidence.lower() not in page_text[signal.source_url]:
                continue
            filtered.append(signal)

        llm_company = llm_result.company
        base_company = baseline.company
        field_updates: dict[str, str | None] = {}
        evidence_updates = baseline.field_evidence.model_dump()
        for field in type(base_company).model_fields:
            base_value = getattr(base_company, field)
            llm_value = getattr(llm_company, field)
            base_evidence = getattr(baseline.field_evidence, field)
            llm_evidence = getattr(llm_result.field_evidence, field)
            base_confidence = base_evidence.confidence if base_evidence else 0.0
            valid_llm_evidence = (
                llm_evidence
                if llm_evidence
                and llm_evidence.source_url in allowed_urls
                and llm_evidence.evidence.lower() in page_text[llm_evidence.source_url]
                and llm_value is not None
                and _evidence_supports_field(field, llm_value, llm_evidence.evidence)
                else None
            )
            should_use_llm = (
                llm_value is not None
                and valid_llm_evidence is not None
                and valid_llm_evidence.confidence >= 0.6
                and (
                    not base_value
                    or base_value == "Unknown"
                    or valid_llm_evidence.confidence >= base_confidence + 0.15
                )
            )
            field_updates[field] = llm_value if should_use_llm else base_value
            if should_use_llm and valid_llm_evidence:
                evidence_updates[field] = valid_llm_evidence.model_dump()

        company = base_company.model_copy(update=field_updates)
        field_evidence = type(baseline.field_evidence).model_validate(evidence_updates)
        seen = {(signal.name.lower(), signal.source_url) for signal in baseline.signals}
        combined = list(baseline.signals)
        for signal in filtered:
            key = (signal.name.lower(), signal.source_url)
            if key not in seen:
                combined.append(signal)
                seen.add(key)
        return ResearchResult(
            company=company,
            field_evidence=field_evidence,
            signals=combined,
        )


def _evidence_supports_field(field: str, value: str, evidence: str) -> bool:
    if field == "estimated_employee_range":
        range_numbers = [int(number) for number in re.findall(r"\d+", value)]
        evidence_numbers = [int(number) for number in re.findall(r"\d+", evidence)]
        if not range_numbers or not evidence_numbers:
            return False
        low, high = range_numbers[0], range_numbers[-1]
        return any(low <= number <= high for number in evidence_numbers)
    if field == "business_model" and value == "Marketplace":
        strong_terms = (
            "two-sided marketplace",
            "online marketplace",
            "connects buyers and sellers",
            "buy and sell",
        )
        return any(term in evidence.lower() for term in strong_terms)
    return True
