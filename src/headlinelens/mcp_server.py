"""HeadlineLens tools over MCP stdio; stdout is reserved for the protocol."""

import argparse
from datetime import datetime, timezone
import math
import os
from pathlib import Path
from threading import RLock
from typing import Literal

from mcp.server.fastmcp import FastMCP

from .fetch import fetch_watchlist
from .report import render_memo
from .watchlist import Watchlist, load_watchlist, normalize_symbols, save_watchlist

mcp = FastMCP("HeadlineLens")
_watchlist_lock = RLock()


def watchlist_path() -> Path:
    """Resolve an editable-install default independently of the launch cwd."""
    configured = os.environ.get("HEADLINELENS_WATCHLIST")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError("HEADLINELENS_WATCHLIST must be an absolute path.")
        return path
    return Path(__file__).resolve().parents[2] / "watchlist.yml"


def _hours(value: float) -> float:
    if not math.isfinite(value) or not 0 < value <= 87600:
        raise ValueError("hours must be positive, finite and at most 87600 (10 years)")
    return value


def _payload(watchlist: Watchlist) -> dict[str, list[str]]:
    return {"market": list(watchlist.market), "tickers": list(watchlist.tickers)}


@mcp.tool()
def get_brief(hours: float = 24, tickers: list[str] | None = None) -> str:
    """Fetch a fresh Yahoo RSS morning brief as Markdown (default: last 24 hours).

    Optional tickers replace followed names for this call only; saved market
    context stays. Source failures/warnings appear in the memo. Does not mutate
    the saved watchlist or schedule delivery.
    """
    hours = _hours(hours)
    watchlist = load_watchlist(watchlist_path())
    if tickers is not None:
        watchlist = Watchlist(watchlist.market, normalize_symbols(tickers))
    if not watchlist.symbols:
        raise ValueError("Watchlist must contain at least one symbol.")
    now = datetime.now(timezone.utc)
    results = fetch_watchlist(watchlist.symbols, now, hours)
    return render_memo(watchlist, results, now, hours)


@mcp.tool()
def add_ticker(
    symbol: str, group: Literal["tickers", "market"] = "tickers"
) -> dict[str, list[str]]:
    """Persist one normalized symbol in tickers (default) or market.

    Duplicate additions to the same group are idempotent. Return both updated
    groups. Changes affect later calls and rewrite the YAML watchlist.
    """
    normalized = normalize_symbols([symbol])[0]
    if group not in {"tickers", "market"}:
        raise ValueError("group must be tickers or market")
    with _watchlist_lock:
        path = watchlist_path()
        watchlist = load_watchlist(path)
        data = _payload(watchlist)
        if normalized not in data[group]:
            data[group].append(normalized)
            watchlist = Watchlist(tuple(data["market"]), tuple(data["tickers"]))
            save_watchlist(watchlist, path)
        return _payload(watchlist)


@mcp.tool()
def remove_ticker(symbol: str) -> dict[str, list[str]]:
    """Persist removal from BOTH market and tickers; return both updated groups.

    A missing symbol is a no-op. Refuse removing the last symbol without changing
    the file: the saved watchlist must never become empty.
    """
    normalized = normalize_symbols([symbol])[0]
    with _watchlist_lock:
        path = watchlist_path()
        watchlist = load_watchlist(path)
        updated = Watchlist(
            tuple(s for s in watchlist.market if s != normalized),
            tuple(s for s in watchlist.tickers if s != normalized),
        )
        if not updated.symbols:
            raise ValueError("Cannot remove the last symbol: watchlist would be empty.")
        if updated != watchlist:
            save_watchlist(updated, path)
        return _payload(updated)


@mcp.tool()
def search_catalysts(
    ticker: str | None = None, hours: float = 24, catalyst: str | None = None
) -> dict:
    """Fetch tagged RSS items for one ticker or the whole saved watchlist.

    ticker may be any valid single symbol; it is not added to the saved list.
    catalyst optionally matches an exact tag, case-insensitively (e.g. earnings,
    investigation, merger/acquisition, FDA). Omit it to get all tagged items.
    Return items plus explicit source errors/warnings. Tags are heuristic flags,
    not verified events. Publication times are ISO 8601 UTC.
    """
    hours = _hours(hours)
    symbols = (
        normalize_symbols([ticker]) if ticker is not None
        else load_watchlist(watchlist_path()).symbols
    )
    wanted = catalyst.strip().casefold() if catalyst is not None else None
    if wanted == "":
        raise ValueError("catalyst must be a non-empty tag or omitted")
    now = datetime.now(timezone.utc)
    results = fetch_watchlist(symbols, now, hours)
    items = []
    for result in results:
        for item in result.items:
            # Shared RSS parsing already applies catalyst_tags to title + summary.
            if not item.tags or (
                wanted is not None and wanted not in {tag.casefold() for tag in item.tags}
            ):
                continue
            items.append({
                "ticker": item.ticker,
                "title": item.title,
                "source": item.source,
                "published_at": item.published_at.astimezone(timezone.utc).isoformat(),
                "link": item.link,
                "tags": list(item.tags),
            })
    return {
        "items": items,
        "errors": {r.ticker: r.error for r in results if r.error},
        "warnings": {r.ticker: r.warnings for r in results if r.warnings},
    }


def main() -> None:
    """Launch MCP on stdio, not an HTTP endpoint."""
    parser = argparse.ArgumentParser(description="HeadlineLens MCP server (stdio)")
    parser.parse_args()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
