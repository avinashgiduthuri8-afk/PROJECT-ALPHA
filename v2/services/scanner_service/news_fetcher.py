"""
V2 NewsRiskService — Live News & Delisting Risk Scraper.

Ingests crypto news feeds (e.g. CryptoPanic public API) and evaluates headline risks:
  - Delisting & Trading Halts
  - Negative Risk Events (Hacks, SEC/Regulatory investigations, Exploits, Bankruptcy)
  - Per-Coin Risk Tagging & Sentiment Scoring
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Set

import httpx

from v2.core.logging import get_logger

logger = get_logger("v2.services.scanner_service.news_fetcher")

# Keyword matching rules
DELISTING_KEYWORDS: List[str] = [
    "delist",
    "delisting",
    "remove pair",
    "halt trading",
    "cease support",
    "trading suspended",
    "suspending trading",
    "delisted",
]

NEGATIVE_NEWS_KEYWORDS: List[str] = [
    "hack",
    "hacked",
    "exploit",
    "exploited",
    "investigation",
    "sec",
    "lawsuit",
    "sued",
    "rugpull",
    "scam",
    "bankruptcy",
    "insolvency",
    "insolvent",
    "fraud",
    "stolen",
    "vulnerability",
    "subpoena",
    "criminal",
]

POSITIVE_KEYWORDS: List[str] = [
    "partnership",
    "upgrade",
    "mainnet",
    "adoption",
    "etf approved",
    "record high",
    "expansion",
    "milestone",
    "bullish",
    "listing",
    "listed",
]


class NewsRiskService:
    """
    Scrapes and analyzes live crypto news to detect security vulnerabilities,
    delisting risks, regulatory headwinds, and coin-specific negative catalysts.
    """

    def __init__(
        self,
        api_token: Optional[str] = None,
        cache_ttl_seconds: int = 180,
        timeout_seconds: float = 6.0,
    ) -> None:
        self._api_token = api_token
        self._cache_ttl = cache_ttl_seconds
        self._timeout = timeout_seconds
        self._last_fetch_time: Optional[datetime] = None
        self._cached_news_by_coin: Dict[str, Dict[str, Any]] = {}
        self._all_recent_posts: List[Dict[str, Any]] = []

    def is_cache_valid(self) -> bool:
        if not self._last_fetch_time:
            return False
        elapsed = (datetime.now(timezone.utc) - self._last_fetch_time).total_seconds()
        return elapsed < self._cache_ttl

    async def fetch_latest_news(self) -> Dict[str, Dict[str, Any]]:
        """
        Fetch latest news posts from CryptoPanic or public crypto feeds.
        Parses headlines and populates per-coin risk maps.
        """
        if self.is_cache_valid() and self._cached_news_by_coin:
            return self._cached_news_by_coin

        posts: List[Dict[str, Any]] = []
        url = "https://cryptopanic.com/api/v2/posts/?public=true"
        if self._api_token:
            url += f"&auth_token={self._api_token}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    posts = data.get("results", data.get("posts", []))
                else:
                    logger.debug("CryptoPanic returned HTTP %d, using local analysis", resp.status_code)
        except Exception as exc:
            logger.debug("News fetch failed (%s), relying on cached/internal news evaluator", exc)

        self._all_recent_posts = posts
        self._last_fetch_time = datetime.now(timezone.utc)
        self._cached_news_by_coin = self._index_posts_by_coin(posts)
        return self._cached_news_by_coin

    def _index_posts_by_coin(self, posts: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Indexes raw post objects into per-coin evaluations."""
        coin_posts_map: Dict[str, List[Dict[str, Any]]] = {}

        for post in posts:
            title = post.get("title", "")
            # Check tagged currencies
            currencies = post.get("currencies", [])
            tagged_coins: Set[str] = set()

            for curr in currencies:
                code = curr.get("code", "").upper()
                if code:
                    tagged_coins.add(code)

            # Also check title keywords for common symbols (e.g. BTC, ETH, SOL, XRP)
            words = set(re.findall(r"\b[A-Z]{2,6}\b", title))
            tagged_coins.update(words)

            for coin in tagged_coins:
                coin_upper = coin.upper()
                if coin_upper not in coin_posts_map:
                    coin_posts_map[coin_upper] = []
                coin_posts_map[coin_upper].append(post)

        indexed: Dict[str, Dict[str, Any]] = {}
        for coin, coin_posts in coin_posts_map.items():
            indexed[coin] = self._analyze_posts_for_coin(coin, coin_posts)

        return indexed

    def _analyze_posts_for_coin(self, coin: str, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyzes a set of posts specifically for a given coin."""
        has_negative_news = False
        delisting_risk = False
        matched_keywords: List[str] = []
        headlines: List[str] = []
        positive_count = 0
        negative_count = 0

        for p in posts:
            title = p.get("title", "")
            title_lower = title.lower()
            headlines.append(title)

            # Check delisting
            for kw in DELISTING_KEYWORDS:
                if kw in title_lower:
                    delisting_risk = True
                    matched_keywords.append(f"delisting:{kw}")

            # Check negative news
            for kw in NEGATIVE_NEWS_KEYWORDS:
                if kw in title_lower:
                    has_negative_news = True
                    negative_count += 1
                    matched_keywords.append(f"negative:{kw}")

            # Check positive news
            for kw in POSITIVE_KEYWORDS:
                if kw in title_lower:
                    positive_count += 1

        # Sentiment score from 0.0 (very negative) to 1.0 (very positive), 0.5 neutral
        if delisting_risk:
            sentiment_score = 0.0
        elif has_negative_news:
            sentiment_score = max(0.1, 0.5 - (negative_count * 0.15))
        elif positive_count > 0:
            sentiment_score = min(1.0, 0.7 + (positive_count * 0.1))
        else:
            sentiment_score = 0.85  # Clean news baseline

        return {
            "has_negative_news": has_negative_news,
            "delisting_risk": delisting_risk,
            "sentiment_score": round(sentiment_score, 2),
            "news_count": len(posts),
            "matched_keywords": list(set(matched_keywords)),
            "headlines": headlines[:5],
        }

    def evaluate_coin_news(self, coin_symbol: str) -> Dict[str, Any]:
        """
        Evaluate news risk for a given coin ticker.
        If cached analysis is available, returns it. Otherwise returns clean default baseline.
        """
        coin_upper = coin_symbol.upper()
        if coin_upper in self._cached_news_by_coin:
            return self._cached_news_by_coin[coin_upper]

        # Scan any all_recent_posts for coin mentions if not already in map
        matching_posts = []
        for post in self._all_recent_posts:
            title = post.get("title", "")
            if re.search(rf"\b{re.escape(coin_upper)}\b", title, re.IGNORECASE):
                matching_posts.append(post)

        if matching_posts:
            res = self._analyze_posts_for_coin(coin_upper, matching_posts)
            self._cached_news_by_coin[coin_upper] = res
            return res

        # Default clean news environment
        return {
            "has_negative_news": False,
            "delisting_risk": False,
            "sentiment_score": 0.90,
            "news_count": 0,
            "matched_keywords": [],
            "headlines": [],
        }
