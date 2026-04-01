"""R&V IPC — Base collector and price observation."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
import re
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
from config.settings import get_settings

log = structlog.get_logger()


@dataclass
class PriceObservation:
    """A single price observation."""
    producto: str
    precio: float
    unidad: str = "unidad"
    categoria_coicop: str = ""   # "01.1.2"
    division_coicop: str = ""    # "01"
    fuente: str = ""
    url: str = ""
    fecha: date = field(default_factory=date.today)
    metadata: dict = field(default_factory=dict)

    def is_valid(self) -> bool:
        return self.precio > 0 and len(self.producto) > 0


def parse_price_ar(text: str) -> float | None:
    """Parse Argentine price string like '$4.500' or '$ 4.500,50' or '4500'."""
    text = text.replace("$", "").replace("\xa0", "").strip()
    # Remove everything that's not digit, dot, or comma
    text = re.sub(r"[^\d.,]", "", text)
    if not text:
        return None
    # "4.500,50" → dots are thousands, comma is decimal
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        # "4.500" → dots are thousands separators (no decimal)
        # But "4.5" could be a decimal — heuristic: if last dot group has 3 digits, it's thousands
        parts = text.split(".")
        if len(parts) > 1 and len(parts[-1]) == 3:
            text = text.replace(".", "")
        # else leave as-is (e.g. "1234.56")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


class BaseCollector(ABC):
    """Abstract base for all data collectors (API-based, uses httpx)."""

    collector_id: str = "base"
    division_coicop: str = ""
    description: str = ""

    def __init__(self):
        self.settings = get_settings()
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                headers={
                    "User-Agent": self.settings.USER_AGENT,
                    "Accept": "text/html,application/json,*/*",
                    "Accept-Language": "es-AR,es;q=0.9",
                },
                timeout=self.settings.REQUEST_TIMEOUT,
                follow_redirects=True,
            )
        return self._client

    @abstractmethod
    def collect(self) -> list[PriceObservation]:
        """Collect prices. Must be implemented by each collector."""
        ...

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def fetch(self, url: str, **kwargs) -> httpx.Response:
        """HTTP GET with retries."""
        resp = self.client.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def fetch_json(self, url: str, **kwargs) -> dict | list:
        """HTTP GET returning JSON with retries."""
        resp = self.client.get(url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def run(self) -> list[PriceObservation]:
        """Execute collector with error handling and logging."""
        start = datetime.utcnow()
        try:
            observations = self.collect()
            valid = [o for o in observations if o.is_valid()]
            elapsed = (datetime.utcnow() - start).total_seconds()
            log.info(
                "collector.success",
                collector=self.collector_id,
                total=len(observations),
                valid=len(valid),
                elapsed=f"{elapsed:.1f}s",
            )
            return valid
        except Exception as e:
            elapsed = (datetime.utcnow() - start).total_seconds()
            log.error(
                "collector.error",
                collector=self.collector_id,
                error=str(e),
                elapsed=f"{elapsed:.1f}s",
            )
            return []
        finally:
            if self._client and not self._client.is_closed:
                self._client.close()

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.collector_id}>"


class PlaywrightCollector(BaseCollector):
    """
    Base for collectors that need a headless browser (SPAs, anti-bot sites).

    Subclasses implement collect_with_page(page) instead of collect().
    The browser lifecycle is managed here.
    """

    def collect(self) -> list[PriceObservation]:
        """Launch browser, delegate to collect_with_page, then close."""
        from playwright.sync_api import sync_playwright

        observations = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process",
                ],
            )
            context = browser.new_context(
                user_agent=self.settings.USER_AGENT,
                locale="es-AR",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            try:
                observations = self.collect_with_page(page)
            except Exception as e:
                log.error(
                    "playwright_collector.error",
                    collector=self.collector_id,
                    error=str(e),
                )
            finally:
                context.close()
                browser.close()

        return observations

    @abstractmethod
    def collect_with_page(self, page) -> list[PriceObservation]:
        """Collect prices using a Playwright page. Implement in subclass."""
        ...
