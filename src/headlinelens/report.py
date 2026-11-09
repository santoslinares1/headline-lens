"""Auditable Markdown memo, full-window CSV and optional JSON export."""

import csv
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path

from .fetch import FeedResult
from .normalize import utc_text
from .watchlist import Watchlist


def markdown_text(value: str) -> str:
    # External titles are data, never executable Markdown/HTML.
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for char in "\\`*_{}[]":
        value = value.replace(char, "\\" + char)
    return value.replace("\n", " ")


def section(symbol: str, result: FeedResult) -> list[str]:
    lines = [f"### {symbol}", ""]
    if result.error:
        lines += [
            f"**Source error:** {markdown_text(result.error)}",
            "Coverage unavailable; no conclusion about news activity can be drawn.",
            "",
        ]
    elif not result.items:
        lines += ["No material headlines in the lookback.", ""]
    else:
        ranked = sorted(
            result.items, key=lambda h: (bool(h.tags), h.published_at), reverse=True
        )[:5]
        lines += [
            f"Showing {len(ranked)} of {len(result.items)} in-window headlines (tagged first, then newest).",
            "",
        ]
        for item in ranked:
            link = (
                item.link.replace("(", "%28")
                .replace(")", "%29")
                .replace("<", "%3C")
                .replace(">", "%3E")
                .replace(" ", "%20")
            )
            tags = ", ".join(item.tags) if item.tags else "none"
            lines += [
                f"- [{markdown_text(item.title)}]({link})",
                f"  - Source: {markdown_text(item.source)} | Published: {utc_text(item.published_at)} | Possible catalysts: {tags}",
            ]
        lines.append("")
    for warning in result.warnings:
        lines += [f"- Data warning: {markdown_text(warning)}"]
    return lines + ([""] if result.warnings else [])


def render_memo(
    watchlist: Watchlist, results: list[FeedResult], now: datetime, hours: float
) -> str:
    lookup = {result.ticker: result for result in results}
    lines = [
        "# HeadlineLens — Morning Watchlist Brief",
        "",
        f"Generated: {utc_text(now)}",
        f"Lookback: {hours:g} hours",
        f"Market context: {', '.join(watchlist.market) or 'none'}",
        f"Watchlist: {', '.join(watchlist.tickers) or 'none'}",
        "",
        "## At a glance",
        "",
        f"{sum(len(r.items) for r in results)} unique ticker/headline observations in the window; {sum(bool(r.error) for r in results)} source errors.",
        "A headline appearing under two symbols counts twice. CSV includes all retained items; sections show at most five.",
        "",
        "Priority is a keyword-based triage aid, not an assessment of financial materiality or sentiment.",
        "",
    ]
    if watchlist.market:
        lines += ["## Market context", ""]
        for symbol in watchlist.market:
            lines += section(
                symbol,
                lookup.get(
                    symbol, FeedResult(symbol, error="No fetch result recorded")
                ),
            )
    lines += ["## Followed companies", ""]
    for symbol in watchlist.tickers:
        lines += section(
            symbol,
            lookup.get(symbol, FeedResult(symbol, error="No fetch result recorded")),
        )
    lines += [
        "## Sources",
        "",
        "Yahoo Finance RSS — https://feeds.finance.yahoo.com/rss/2.0/headline (one feed per symbol).",
        "Publisher labels are taken from RSS source fields when supplied; otherwise the label is Yahoo Finance RSS.",
        "RSS coverage can be delayed or incomplete. 'No material headlines' means no usable feed items in the window, not verified absence of news.",
        "Catalyst tags are heuristic, may describe speculation or negated events, and require reading the linked story. Not investment advice.",
        "",
    ]
    return "\n".join(lines)


def write_reports(
    directory: Path,
    watchlist: Watchlist,
    results: list[FeedResult],
    now: datetime,
    hours: float,
    include_json: bool = False,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    memo = directory / "watchlist_brief.md"
    memo.write_text(render_memo(watchlist, results, now, hours), encoding="utf-8")
    with (directory / "headlines.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["ticker", "title", "source", "published_at", "link", "tags"])
        for result in results:
            for item in result.items:
                cells = [
                    item.ticker,
                    item.title,
                    item.source,
                    item.published_at.isoformat(),
                    item.link,
                    ";".join(item.tags),
                ]
                writer.writerow(
                    [
                        "'" + value if value.startswith(("=", "+", "-", "@")) else value
                        for value in cells
                    ]
                )
    status = {
        r.ticker: {"error": r.error, "warnings": r.warnings, "headlines": len(r.items)}
        for r in results
    }
    (directory / "source_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )
    if include_json:
        payload = {
            "generated_at": now.isoformat(),
            "hours": hours,
            "watchlist": asdict(watchlist),
            "results": [asdict(r) for r in results],
        }
        (directory / "headlines.json").write_text(
            json.dumps(payload, indent=2, default=lambda v: v.isoformat()) + "\n",
            encoding="utf-8",
        )
    return memo
