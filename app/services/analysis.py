import logging

from sqlalchemy.orm import Session

from app import models
from app.core.config import Settings
from app.schemas import CompanyAnalyzeRequest, CompanyDetail
from app.services.extraction import extract_website_facts
from app.services.llm import LLMResearcher
from app.services.research import research_website
from app.services.scoring import ICPConfig, load_icp_config, score_company
from app.services.scraper import WebsiteScraper

logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        scraper: WebsiteScraper | None = None,
        researcher: LLMResearcher | None = None,
        icp_config: ICPConfig | None = None,
    ):
        self.db = db
        self.settings = settings
        self.scraper = scraper or WebsiteScraper(settings)
        self.researcher = researcher or LLMResearcher(settings)
        self.icp_config = icp_config or load_icp_config(settings.icp_config_path)

    async def analyze(self, request: CompanyAnalyzeRequest) -> CompanyDetail:
        website = str(request.website)
        logger.info("Starting analysis name=%s website=%s", request.name, website)
        pages = await self.scraper.fetch(website)
        facts = extract_website_facts(request.name, pages)
        baseline = research_website(pages, facts, self.icp_config)
        research = await self.researcher.research(request.name, pages, baseline)
        score = score_company(research, self.icp_config)

        company = models.Company(
            name=request.name,
            website=website,
            **research.company.model_dump(),
        )
        company.signals = [
            models.Signal(
                name=signal.name,
                evidence=signal.evidence,
                source_url=signal.source_url,
                confidence=signal.confidence,
                points=signal.points,
            )
            for signal in score.signals
        ]
        company.score = models.Score(
            industry_match=score.industry_match,
            company_type_match=score.company_type_match,
            company_size_match=score.company_size_match,
            sales_motion_match=score.sales_motion_match,
            growth_signal_match=score.growth_signal_match,
            total=score.total,
            explanation=score.explanation,
        )
        try:
            self.db.add(company)
            self.db.commit()
            self.db.refresh(company)
        except Exception:
            self.db.rollback()
            logger.exception("Failed to persist analysis for %s", request.name)
            raise
        logger.info("Completed analysis company_id=%s score=%s", company.id, company.score.total)
        return CompanyDetail.model_validate(company)
