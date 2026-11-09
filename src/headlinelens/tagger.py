"""Keyword flags, not event verification, sentiment, or investment signals."""

import re
from .normalize import clean_text

RULES = {
    "earnings": r"\b(?:earnings|quarterly results|record revenue)\b",
    "guidance": r"\b(?:guidance|raises outlook|cuts outlook|lowers outlook)\b",
    "merger/acquisition": r"\b(?:merger|acquisition|takeover|acquires|buyout)\b",
    "downgrade": r"\b(?:downgrade[ds]?|downgrading)\b",
    "upgrade": r"\b(?:upgrade[ds]?|upgrading)\b",
    "lawsuit": r"\b(?:lawsuit|sued|class.action)\b",
    "investigation": r"\b(?:investigation|investigates|regulatory probe)\b",
    "FDA": r"\bfda\b",
    "offering": r"\b(?:public offering|stock offering|share offering|secondary offering)\b",
    "buyback": r"\b(?:buyback|share repurchase|stock repurchase)\b",
    "dividend": r"\bdividends?\b",
    "layoffs": r"\b(?:layoffs?|job cuts|cuts jobs)\b",
}
PATTERNS = {tag: re.compile(pattern, re.IGNORECASE) for tag, pattern in RULES.items()}


def catalyst_tags(title: str, summary: str = "") -> tuple[str, ...]:
    text = clean_text(f"{title} {summary}")
    return tuple(tag for tag, pattern in PATTERNS.items() if pattern.search(text))
