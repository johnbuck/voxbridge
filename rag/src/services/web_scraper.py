"""
Web Scraper Service (RAG Phase 3.1)

Extracts clean text content from web pages using trafilatura.
Handles various web content formats and provides metadata extraction.
"""

import logging
import hashlib
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


class WebScrapeError(Exception):
    """Raised when web scraping fails."""
    pass


@dataclass
class ScrapedWebPage:
    """
    Result of web page scraping.

    Contains extracted text, metadata, and source information.
    """

    # Core content
    text: str
    url: str

    # Metadata
    title: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None

    # Source info
    content_hash: str = ""
    char_count: int = 0
    word_count: int = 0
    scraped_at: str = ""

    def __post_init__(self):
        """Calculate counts and hash after initialization."""
        self.char_count = len(self.text)
        self.word_count = len(self.text.split())
        self.content_hash = hashlib.sha256(self.text.encode()).hexdigest()
        self.scraped_at = datetime.utcnow().isoformat()


class WebScraperService:
    """
    Service for scraping web pages using trafilatura.

    Trafilatura provides high-quality text extraction with:
    - Main content extraction (removes boilerplate)
    - Metadata extraction (title, author, date)
    - Clean text output (no HTML artifacts)

    Usage:
        scraper = WebScraperService()
        result = await scraper.scrape_url("https://example.com/article")
        print(result.text)
    """

    def __init__(
        self,
        timeout: float = 30.0,
        user_agent: str = "VoxBridge/3.1 (RAG Knowledge Ingestion)",
    ):
        """
        Initialize web scraper.

        Args:
            timeout: HTTP request timeout in seconds
            user_agent: User-Agent header for requests
        """
        self.timeout = timeout
        self.user_agent = user_agent
        self._initialized = False
        self._trafilatura_available = False
        self._check_dependencies()

    def _check_dependencies(self):
        """Check if trafilatura is available."""
        try:
            import trafilatura
            self._trafilatura_available = True
            self._initialized = True
            logger.info("🌐 WebScraperService initialized with trafilatura")
        except ImportError as e:
            logger.warning(f"⚠️ trafilatura not available: {e}")
            logger.warning("⚠️ Falling back to basic HTML extraction")
            self._trafilatura_available = False
            self._initialized = True

    async def scrape_url(
        self,
        url: str,
        include_links: bool = False,
        include_images: bool = False,
        favor_recall: bool = True,
    ) -> ScrapedWebPage:
        """
        Scrape a web page and extract its content.

        Args:
            url: URL to scrape
            include_links: Include links in extracted text
            include_images: Include image descriptions
            favor_recall: Prioritize content recall over precision

        Returns:
            ScrapedWebPage with extracted content

        Raises:
            WebScrapeError: If scraping fails
        """
        logger.info(f"🌐 Scraping URL: {url}")

        try:
            # Fetch HTML content
            html_content = await self._fetch_url(url)

            if self._trafilatura_available:
                return await self._scrape_with_trafilatura(
                    url=url,
                    html_content=html_content,
                    include_links=include_links,
                    include_images=include_images,
                    favor_recall=favor_recall,
                )
            else:
                return await self._scrape_basic(url, html_content)

        except httpx.HTTPError as e:
            logger.error(f"❌ HTTP error scraping {url}: {e}")
            raise WebScrapeError(f"HTTP error: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Failed to scrape {url}: {e}")
            raise WebScrapeError(f"Scraping failed: {str(e)}")

    async def _fetch_url(self, url: str) -> str:
        """Fetch URL content using httpx."""
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                url,
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
            return response.text

    async def _scrape_with_trafilatura(
        self,
        url: str,
        html_content: str,
        include_links: bool,
        include_images: bool,
        favor_recall: bool,
    ) -> ScrapedWebPage:
        """
        Extract content using trafilatura.

        Trafilatura is optimized for:
        - News articles
        - Blog posts
        - Documentation
        - General web content
        """
        import trafilatura
        from trafilatura.settings import use_config

        # Configure trafilatura
        config = use_config()
        config.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")

        # Extract main content
        text = trafilatura.extract(
            html_content,
            url=url,
            include_links=include_links,
            include_images=include_images,
            favor_recall=favor_recall,
            config=config,
        )

        if not text:
            # Fallback to bare extraction
            text = trafilatura.extract(
                html_content,
                url=url,
                favor_recall=True,
                include_comments=False,
                include_tables=True,
            )

        if not text:
            raise WebScrapeError(f"No content extracted from {url}")

        # Extract metadata
        metadata = trafilatura.extract_metadata(html_content, url=url)

        title = None
        author = None
        date = None
        description = None

        if metadata:
            title = metadata.title
            author = metadata.author
            date = metadata.date
            description = metadata.description

        logger.info(
            f"✅ Scraped {url}: {len(text)} chars, "
            f"title: '{title or 'N/A'}'"
        )

        return ScrapedWebPage(
            text=text,
            url=url,
            title=title,
            author=author,
            date=date,
            description=description,
        )

    async def _scrape_basic(self, url: str, html_content: str) -> ScrapedWebPage:
        """
        Basic HTML text extraction fallback.

        Uses simple regex-based extraction when trafilatura is unavailable.
        """
        import re

        # Remove script and style elements
        clean = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', ' ', clean)

        # Decode HTML entities
        import html
        clean = html.unescape(clean)

        # Normalize whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()

        # Extract title from HTML
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else None

        if not clean:
            raise WebScrapeError(f"No content extracted from {url}")

        logger.info(f"✅ Basic scrape of {url}: {len(clean)} chars")

        return ScrapedWebPage(
            text=clean,
            url=url,
            title=title,
        )

    async def scrape_multiple(
        self,
        urls: list[str],
        max_concurrent: int = 3,
    ) -> list[ScrapedWebPage | WebScrapeError]:
        """
        Scrape multiple URLs concurrently.

        Args:
            urls: List of URLs to scrape
            max_concurrent: Maximum concurrent requests

        Returns:
            List of ScrapedWebPage or WebScrapeError for each URL
        """
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)

        async def scrape_with_limit(url: str):
            async with semaphore:
                try:
                    return await self.scrape_url(url)
                except WebScrapeError as e:
                    return e

        results = await asyncio.gather(
            *[scrape_with_limit(url) for url in urls],
            return_exceptions=False,
        )

        return results


# Singleton instance
_scraper_service: Optional[WebScraperService] = None


def get_scraper_service() -> WebScraperService:
    """Get or create the singleton web scraper service."""
    global _scraper_service
    if _scraper_service is None:
        _scraper_service = WebScraperService()
    return _scraper_service
