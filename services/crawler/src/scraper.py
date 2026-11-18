import random
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from configs import (
    BASE_BACKOFF,
    INITIAL_ADAPTIVE_DELAY,
    MAX_ADAPTIVE_DELAY,
    MAX_BACKOFF,
    MAX_RETRIES,
    MIN_ADAPTIVE_DELAY,
    TARGET_REVIEWS_COUNT,
    COUNTRY_CODE,
    LANG_CODE,
    REVIEWS_BATCH_SIZE,
    REVIEW_LOCALES,
)
from google_play_scraper import Sort, app, reviews
from google_play_scraper.exceptions import NotFoundError
from models import AppMetrics, Review

from utils.logging_setup import get_logger

logger = get_logger(__name__)


class PlayStoreScraper:
    """Fetches app metrics and reviews from the Play Store with retry/backoff."""

    def __init__(
        self,
        fetch_app_details: Callable[..., Any] = app,
        fetch_reviews_page: Callable[..., Any] = reviews,
    ) -> None:
        """Accept the Play Store calls as injectable dependencies; the defaults hit the real store."""
        self.fetch_app_details = fetch_app_details
        self.fetch_reviews_page = fetch_reviews_page

        self.max_retries = MAX_RETRIES
        self.base_backoff = BASE_BACKOFF
        self.max_backoff = MAX_BACKOFF

        self.adaptive_delay = INITIAL_ADAPTIVE_DELAY
        self.min_delay = MIN_ADAPTIVE_DELAY
        self.max_delay = MAX_ADAPTIVE_DELAY


    def get_app_metrics(self, package_name: str) -> AppMetrics | None:
        for attempt in range(self.max_retries):
            try:
                payload = self.fetch_app_details(package_name, lang=LANG_CODE, country=COUNTRY_CODE)
                if payload is None:
                    return None
                return AppMetrics.from_scraped_payload(payload, datetime.now(UTC).isoformat())
            except NotFoundError:
                logger.warning("App not found on Google Play: %s", package_name)
                return None
            except Exception:
                if attempt == self.max_retries - 1:
                    logger.exception("Could not fetch app metrics for %s", package_name)
                    return None
                delay = min(self.base_backoff * 2**attempt, self.max_backoff)
                time.sleep(delay)
        return None

    def get_latest_reviews(self, package_name: str, count: int = TARGET_REVIEWS_COUNT) -> list[dict[str, Any]]:
        if count <= 0:
            return []

        collected: dict[str, dict[str, Any]] = {}
        scraped_at = datetime.now(UTC).isoformat()
        for lang, country in REVIEW_LOCALES:
            token = None
            while len(collected) < count:
                try:
                    page, token = self.fetch_reviews_page(
                        package_name,
                        lang=lang,
                        country=country,
                        sort=Sort.NEWEST,
                        count=min(REVIEWS_BATCH_SIZE, count - len(collected)),
                        continuation_token=token,
                    )
                except NotFoundError:
                    logger.warning("Reviews not found on Google Play: %s", package_name)
                    return list(collected.values())
                except Exception:
                    logger.exception("Could not fetch reviews for %s (%s/%s)", package_name, lang, country)
                    break

                for payload in page:
                    review = Review.from_scraped_payload(payload, scraped_at)
                    if review:
                        collected[review.review_id] = review.to_record()
                    if len(collected) >= count:
                        break
                if not token or not page:
                    break
            if len(collected) >= count:
                break
        return list(collected.values())
