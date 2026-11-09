import csv
from dataclasses import replace
import json

import pytest

from headlinelens import cli
from headlinelens.fetch import FeedResult, parse_rss
from headlinelens.normalize import select_headlines
from headlinelens.report import render_memo, write_reports
from headlinelens.watchlist import Watchlist, load_watchlist


def test_memo_context_order_empty_error_and_cap(rss, now):
    item = parse_rss(rss, "DEMO").items[0]
    many = [
        replace(item, title=f"Headline {i}", link=f"https://example.com/{i}")
        for i in range(8)
    ]
    watch = Watchlist(("SPY",), ("DEMO", "QUIET", "BAD"))
    memo = render_memo(
        watch,
        [
            FeedResult("SPY"),
            FeedResult("DEMO", many),
            FeedResult("QUIET"),
            FeedResult("BAD", error="HTTP 429"),
        ],
        now,
        24,
    )
    assert memo.index("### SPY") < memo.index("### DEMO") < memo.index("### QUIET")
    assert "Showing 5 of 8" in memo
    assert memo.count("[Headline ") == 5
    assert "No material headlines in the lookback." in memo
    assert "Source error:" in memo and "HTTP 429" in memo
    assert "Generated: 2026-11-06 12:00 UTC" in memo


def test_exports_preserve_fields_and_protect_formulas(tmp_path, rss, now):
    item = replace(parse_rss(rss, "DEMO").items[0], title="=SUM(1,2)")
    write_reports(
        tmp_path, Watchlist((), ("DEMO",)), [FeedResult("DEMO", [item])], now, 24, True
    )
    with (tmp_path / "headlines.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["title"] == "'=SUM(1,2)"
    assert rows[0]["tags"] == "earnings;guidance"
    payload = json.loads((tmp_path / "headlines.json").read_text())
    assert payload["results"][0]["items"][0]["title"] == "=SUM(1,2)"
    assert (
        json.loads((tmp_path / "source_status.json").read_text())["DEMO"]["error"]
        is None
    )


def test_external_title_is_escaped(rss, now):
    item = replace(parse_rss(rss, "DEMO").items[0], title="[click](bad) <script>")
    memo = render_memo(Watchlist((), ("DEMO",)), [FeedResult("DEMO", [item])], now, 24)
    assert "<script>" not in memo
    assert "\\[click\\]" in memo


def test_cli_mocked_fetch_and_override(monkeypatch, tmp_path, rss):
    watch = tmp_path / "custom.yml"
    watch.write_text("market: [SPY]\ntickers: [XOM]\n")

    def fake(symbols, now, hours):
        assert symbols == ("SPY", "AAPL", "MSFT")
        assert hours == 36
        result = parse_rss(rss, "AAPL")
        # Use a deterministic empty window rather than depend on the wall clock.
        result.items = select_headlines(result.items, now, hours)
        return [FeedResult("SPY"), result, FeedResult("MSFT")]

    monkeypatch.setattr(cli, "fetch_watchlist", fake)
    output = tmp_path / "out"
    assert (
        cli.main(
            [
                "aapl",
                "MSFT",
                "--watchlist",
                str(watch),
                "--hours",
                "36",
                "-o",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    assert (output / "watchlist_brief.md").exists()
    assert (output / "headlines.json").exists()
    assert "Watchlist: AAPL, MSFT" in (output / "watchlist_brief.md").read_text()


def test_cli_source_error_returns_one_but_writes(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "fetch_watchlist",
        lambda symbols, now, hours: [FeedResult(s, error="HTTP 503") for s in symbols],
    )
    assert cli.main(["-o", str(tmp_path / "out")]) == 1
    assert "HTTP 503" in (tmp_path / "out/watchlist_brief.md").read_text()


@pytest.mark.parametrize("hours", ["0", "-1", "nan", "inf", "nonsense"])
def test_cli_rejects_invalid_hours(hours):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--hours", hours])
    assert exc.value.code == 2


def test_cli_invalid_yaml_returns_two(tmp_path):
    watch = tmp_path / "bad.yml"
    watch.write_text("tickers: [\n")
    assert cli.main(["--watchlist", str(watch)]) == 2


def test_watchlist_normalization_and_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert load_watchlist().tickers == ("AAPL", "MSFT", "NVDA", "JPM", "XOM")
    local = tmp_path / "watchlist.yml"
    local.write_text("market: [spy]\ntickers: [aapl, AAPL, BRK-B]\n")
    assert load_watchlist().symbols == ("SPY", "AAPL", "BRK-B")


@pytest.mark.parametrize(
    "text",
    ["tickers: AAPL", "tickers: [1]", "tickers: ['AAPL/xx']", "{}", "wrong: []", "[]"],
)
def test_invalid_watchlists(tmp_path, text):
    file = tmp_path / "watchlist.yml"
    file.write_text(text)
    with pytest.raises(ValueError):
        load_watchlist(file)


def test_tagged_item_prioritized_over_newer_untagged(rss, now):
    item = parse_rss(rss, "DEMO").items[0]
    older = replace(item, title="Tagged older", tags=("earnings",))
    newer = replace(item, title="Untagged newer", published_at=now, tags=())
    memo = render_memo(
        Watchlist((), ("DEMO",)), [FeedResult("DEMO", [newer, older])], now, 24
    )
    assert memo.index("Tagged older") < memo.index("Untagged newer")


def test_warning_visible_in_memo_and_cli(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "fetch_watchlist",
        lambda symbols, now, hours: [
            FeedResult(s, warnings=["Skipped item: invalid date"]) for s in symbols
        ],
    )
    assert cli.main([]) == 1
    assert (
        "Data warning: Skipped item: invalid date"
        in (tmp_path / "output/watchlist_brief.md").read_text()
    )
