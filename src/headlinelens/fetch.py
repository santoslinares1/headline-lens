"""Yahoo Finance RSS adapter. All failures remain visible to the reader."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import requests

from .normalize import Headline, clean_text, select_headlines
from .tagger import catalyst_tags

FEED_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"
USER_AGENT = "HeadlineLens/0.1 (Santos Linares; portfolio research project; santos9linares@gmail.com)"


class FeedError(Exception):
    """An unavailable or invalid source, not an empty news window."""


@dataclass
class FeedResult:
    ticker: str
    items: list[Headline] = field(default_factory=list)
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


def valid_http_link(link: str) -> bool:
    try:
        parts = urlsplit(link)
        return (
            parts.scheme in {"https", "http"}
            and bool(parts.hostname)
            and not any(c.isspace() for c in link)
        )
    except ValueError:
        return False


def parse_rss(content: bytes, ticker: str) -> FeedResult:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise FeedError(f"Invalid RSS XML: {exc}") from exc
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise FeedError("Invalid RSS: expected an rss/channel document")
    result = FeedResult(ticker)
    for index, node in enumerate(channel.findall("item"), 1):
        title = clean_text(node.findtext("title", ""))
        link = node.findtext("link", "").strip()
        date = node.findtext("pubDate", "").strip()
        try:
            published = parsedate_to_datetime(date)
            if published.tzinfo is None:
                raise ValueError("missing timezone")
            published = published.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            result.warnings.append(
                f"Skipped RSS item {index}: missing or invalid publication date."
            )
            continue
        if not title or not valid_http_link(link):
            result.warnings.append(
                f"Skipped RSS item {index}: missing title or valid HTTP(S) link."
            )
            continue
        summary = clean_text(node.findtext("description", ""))
        source = clean_text(node.findtext("source", "")) or "Yahoo Finance RSS"
        result.items.append(
            Headline(
                ticker,
                title,
                source,
                published,
                link,
                summary,
                catalyst_tags(title, summary),
            )
        )
    return result


def fetch_ticker(
    ticker: str, now: datetime, hours: float, session: requests.Session
) -> FeedResult:
    try:
        response = session.get(
            FEED_URL,
            params={"s": ticker, "region": "US", "lang": "en-US"},
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/xml",
            },
            timeout=(5, 20),
        )
        response.raise_for_status()
        result = parse_rss(response.content, ticker)
        result.items = select_headlines(result.items, now, hours)
        return result
    except (requests.RequestException, FeedError) as exc:
        return FeedResult(ticker, error=f"{type(exc).__name__}: {exc}")


def fetch_watchlist(
    symbols: tuple[str, ...], now: datetime, hours: float
) -> list[FeedResult]:
    with requests.Session() as session:
        return [fetch_ticker(symbol, now, hours, session) for symbol in symbols]
