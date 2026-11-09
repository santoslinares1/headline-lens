"""Deterministic normalization, date filtering and duplicate handling."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class Headline:
    ticker: str
    title: str
    source: str
    published_at: datetime
    link: str
    summary: str = ""
    tags: tuple[str, ...] = ()


def clean_text(value: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", value)).split())


def normalized_link(link: str) -> str:
    parts = urlsplit(link.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
        and k.lower() not in {"guccounter", "guce_referrer", "guce_referrer_sig"}
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            urlencode(sorted(query)),
            "",
        )
    )


def select_headlines(
    items: list[Headline], now: datetime, hours: float
) -> list[Headline]:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if hours <= 0:
        raise ValueError("hours must be positive")
    cutoff = now - timedelta(hours=hours)
    seen = set()
    selected = []
    for item in sorted(items, key=lambda h: h.published_at, reverse=True):
        if not cutoff <= item.published_at <= now:
            continue
        key = (clean_text(item.title).casefold(), normalized_link(item.link))
        if key not in seen:
            selected.append(item)
            seen.add(key)
    return selected


def utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
