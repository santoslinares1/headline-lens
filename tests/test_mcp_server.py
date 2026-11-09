from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from headlinelens import mcp_server as server
from headlinelens.fetch import FeedResult, parse_rss
from headlinelens.watchlist import Watchlist, load_watchlist, save_watchlist


@pytest.fixture
def watch(monkeypatch, tmp_path):
    path = tmp_path / "watchlist.yml"
    path.write_text("market: [SPY]\ntickers: [AAPL]\n")
    monkeypatch.setenv("HEADLINELENS_WATCHLIST", str(path))
    return path


def test_default_path_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("HEADLINELENS_WATCHLIST", raising=False)
    monkeypatch.chdir(tmp_path)
    assert server.watchlist_path() == Path(server.__file__).resolve().parents[2] / "watchlist.yml"
    assert load_watchlist(server.watchlist_path()).symbols == (
        "SPY", "AAPL", "MSFT", "NVDA", "JPM", "XOM"
    )


def test_relative_env_path_rejected(monkeypatch):
    monkeypatch.setenv("HEADLINELENS_WATCHLIST", "watchlist.yml")
    with pytest.raises(ValueError, match="absolute"):
        server.watchlist_path()


def test_add_persist_normalize_idempotent_and_groups(watch):
    assert server.add_ticker(" msft ")["tickers"] == ["AAPL", "MSFT"]
    assert load_watchlist(watch).tickers == ("AAPL", "MSFT")
    before = watch.read_bytes()
    server.add_ticker("MSFT")
    assert watch.read_bytes() == before
    assert server.add_ticker("qqq", "market")["market"] == ["SPY", "QQQ"]
    assert load_watchlist(watch).market == ("SPY", "QQQ")


def test_remove_both_groups_and_missing_noop(watch):
    server.add_ticker("SPY")
    assert server.remove_ticker(" spy ") == {"market": [], "tickers": ["AAPL"]}
    assert load_watchlist(watch).symbols == ("AAPL",)
    before = watch.read_bytes()
    assert server.remove_ticker("MISSING")["tickers"] == ["AAPL"]
    assert watch.read_bytes() == before
    with pytest.raises(ValueError, match="empty"):
        server.remove_ticker("AAPL")
    assert watch.read_bytes() == before


def test_save_refuses_empty_without_modifying_file(watch):
    before = watch.read_bytes()
    with pytest.raises(ValueError, match="at least one"):
        save_watchlist(Watchlist((), ()), watch)
    assert watch.read_bytes() == before


@pytest.mark.parametrize("symbol", ["", "AAPL MSFT", "AAPL/xx"])
def test_invalid_symbol_does_not_write(watch, symbol):
    before = watch.read_bytes()
    with pytest.raises(ValueError):
        server.add_ticker(symbol)
    with pytest.raises(ValueError):
        server.remove_ticker(symbol)
    assert watch.read_bytes() == before


def test_invalid_group(watch):
    with pytest.raises(ValueError, match="group"):
        server.add_ticker("MSFT", "other")


def test_get_brief_reuses_memo_and_preserves_market(watch, monkeypatch, rss):
    feed = parse_rss(rss, "MSFT")
    fake = Mock(return_value=[FeedResult("SPY", error="HTTP 503"), feed])
    monkeypatch.setattr(server, "fetch_watchlist", fake)
    before = watch.read_bytes()
    memo = server.get_brief(hours=36, tickers=["msft", "MSFT"])
    assert memo.startswith("# HeadlineLens — Morning Watchlist Brief")
    assert "DemoCo reports earnings" in memo
    assert "Market context: SPY" in memo
    assert "Watchlist: MSFT" in memo
    assert "Source error:" in memo and "HTTP 503" in memo
    assert fake.call_args.args[0] == ("SPY", "MSFT")
    assert fake.call_args.args[2] == 36
    assert watch.read_bytes() == before


def test_get_brief_default_and_empty_override(watch, monkeypatch):
    fake = Mock(return_value=[])
    monkeypatch.setattr(server, "fetch_watchlist", fake)
    server.get_brief()
    assert fake.call_args.args[0] == ("SPY", "AAPL")
    assert fake.call_args.args[2] == 24
    server.get_brief(tickers=[])
    assert fake.call_args.args[0] == ("SPY",)


def test_search_tagged_and_filter_ticker(watch, monkeypatch, rss):
    parsed = parse_rss(rss, "AAPL")
    earnings = parsed.items[0]
    untagged = replace(earnings, title="Routine update", tags=())
    investigation = replace(earnings, title="Fictional investigation", tags=("investigation",))
    fake = Mock(return_value=[
        FeedResult("AAPL", [earnings, untagged, investigation], warnings=["Skipped item"]),
        FeedResult("SPY", error="HTTP 429"),
    ])
    monkeypatch.setattr(server, "fetch_watchlist", fake)
    payload = server.search_catalysts()
    assert fake.call_args.args[0] == ("SPY", "AAPL")
    assert len(payload["items"]) == 2
    assert payload["errors"] == {"SPY": "HTTP 429"}
    assert payload["warnings"] == {"AAPL": ["Skipped item"]}
    row = payload["items"][0]
    assert row == {
        "ticker": "AAPL", "title": earnings.title, "source": earnings.source,
        "published_at": earnings.published_at.isoformat(), "link": earnings.link,
        "tags": list(earnings.tags),
    }
    filtered = server.search_catalysts(ticker="aapl", hours=12, catalyst=" EARNINGS ")
    assert fake.call_args.args[0] == ("AAPL",)
    assert fake.call_args.args[2] == 12
    assert filtered["items"] == [row]
    assert server.search_catalysts(catalyst="unknown")["items"] == []


@pytest.mark.parametrize("hours", [0, -1, float("nan"), float("inf"), 87601])
def test_invalid_hours_before_fetch(watch, monkeypatch, hours):
    fake = Mock()
    monkeypatch.setattr(server, "fetch_watchlist", fake)
    for tool in (server.get_brief, server.search_catalysts):
        with pytest.raises(ValueError, match="hours"):
            tool(hours=hours)
    fake.assert_not_called()


def test_empty_filter_rejected(watch):
    with pytest.raises(ValueError, match="catalyst"):
        server.search_catalysts(catalyst="  ")


def test_exact_mcp_tool_registry():
    import asyncio
    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "get_brief", "add_ticker", "remove_ticker", "search_catalysts"
    }
    schemas = {tool.name: tool.inputSchema for tool in tools}
    assert schemas["add_ticker"]["required"] == ["symbol"]
    assert schemas["remove_ticker"]["required"] == ["symbol"]
    assert schemas["get_brief"]["properties"]["hours"]["default"] == 24
