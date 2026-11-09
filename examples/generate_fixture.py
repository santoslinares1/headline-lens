"""Reproduce a clearly labeled synthetic example; no network requests."""

from datetime import datetime, timezone
from pathlib import Path

from headlinelens.fetch import FeedResult, parse_rss
from headlinelens.normalize import select_headlines
from headlinelens.report import write_reports
from headlinelens.watchlist import Watchlist

root = Path(__file__).resolve().parents[1]
now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
result = parse_rss((root / "tests/fixtures/sample.xml").read_bytes(), "DEMO")
result.items = select_headlines(result.items, now, 24)
watchlist = Watchlist(("MARKET",), ("DEMO", "QUIET"))
memo = write_reports(
    root / "examples/fixture",
    watchlist,
    [FeedResult("MARKET"), result, FeedResult("QUIET")],
    now,
    24,
    True,
)
memo.write_text(
    "> SYNTHETIC FIXTURE EXAMPLE. All tickers, companies, events, links and timestamps below are test data, not live financial news. Sources describe the production adapter; this example makes no HTTP requests.\n\n"
    + memo.read_text(encoding="utf-8"),
    encoding="utf-8",
)
print(memo)
