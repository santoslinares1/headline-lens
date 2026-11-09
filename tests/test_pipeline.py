from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import pytest
import requests

from headlinelens.fetch import (
    FeedError,
    FeedResult,
    fetch_ticker,
    fetch_watchlist,
    parse_rss,
    USER_AGENT,
)
from headlinelens.normalize import select_headlines
from headlinelens.tagger import catalyst_tags


def test_parse_rss_and_date_offset(rss):
    result = parse_rss(rss, "DEMO")
    assert len(result.items) == 6
    assert result.items[0].summary == "Fictional quarterly results for testing only."
    assert result.items[0].tags == ("earnings", "guidance")
    assert result.items[2].published_at.hour == 9
    assert result.items[3].source == "Yahoo Finance RSS"


def test_dedup_window_newest_first(rss, now):
    result = select_headlines(parse_rss(rss, "DEMO").items, now, 24)
    assert len(result) == 3
    assert result[0].title.startswith("DemoCo reports")
    assert [h.published_at for h in result] == sorted(
        [h.published_at for h in result], reverse=True
    )


def test_window_inclusive_and_no_future(rss, now):
    item = parse_rss(rss, "DEMO").items[0]
    dates = [
        now - timedelta(hours=24),
        now,
        now - timedelta(hours=24, seconds=1),
        now + timedelta(seconds=1),
    ]
    items = [
        replace(item, published_at=date, link=f"https://example.com/{i}")
        for i, date in enumerate(dates)
    ]
    assert [h.published_at for h in select_headlines(items, now, 24)] == [now, dates[0]]


def test_same_title_different_links_preserved(rss, now):
    item = parse_rss(rss, "DEMO").items[0]
    assert (
        len(
            select_headlines(
                [item, replace(item, link="https://example.com/other")], now, 24
            )
        )
        == 2
    )


@pytest.mark.parametrize("xml", [b"not xml", b"<html/>", b"<rss/>"])
def test_invalid_feed(xml):
    with pytest.raises(FeedError):
        parse_rss(xml, "DEMO")


def test_bad_date_and_link_are_skipped_with_warning():
    xml = b"<rss><channel><item><title>Unknown date</title></item><item><title>Unsafe</title><link>javascript:alert(1)</link><pubDate>Fri, 06 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>"
    result = parse_rss(xml, "DEMO")
    assert not result.items
    assert len(result.warnings) == 2


@pytest.mark.parametrize(
    "title,summary,expected",
    [
        ("Quarterly earnings; guidance cut", "", {"earnings", "guidance"}),
        ("Company acquires rival", "", {"merger/acquisition"}),
        ("Analyst downgrades shares", "", {"downgrade"}),
        ("Analyst upgraded shares", "", {"upgrade"}),
        ("Company sued", "Investigation launched", {"lawsuit", "investigation"}),
        ("FDA review", "Secondary offering", {"FDA", "offering"}),
        (
            "Share repurchase and dividend",
            "Job cuts",
            {"buyback", "dividend", "layoffs"},
        ),
        ("Company expands product offering", "A community event", set()),
        ("Record revenue", "", {"earnings"}),
        ("A regular update", "", set()),
    ],
)
def test_catalyst_rules(title, summary, expected):
    assert set(catalyst_tags(title, summary)) == expected


def test_http_error_exposed(now):
    session = Mock()
    session.get.side_effect = requests.HTTPError("429 Too Many Requests")
    result = fetch_ticker("DEMO", now, 24, session)
    assert result.error == "HTTPError: 429 Too Many Requests"
    assert result.items == []


def test_fetch_sets_contact_and_timeout(rss, now):
    session = Mock()
    session.get.return_value.content = rss
    result = fetch_ticker("DEMO", now, 24, session)
    assert len(result.items) == 3
    kwargs = session.get.call_args.kwargs
    assert kwargs["headers"]["User-Agent"] == USER_AGENT
    assert "santos9linares@gmail.com" in USER_AGENT
    assert kwargs["timeout"] == (5, 20)
    assert kwargs["params"]["s"] == "DEMO"


def test_fetch_continues_after_ticker_failure(monkeypatch, rss, now):
    session = Mock()
    response = Mock(content=rss)
    session.get.side_effect = [requests.Timeout("read timed out"), response]
    manager = Mock()
    manager.__enter__ = Mock(return_value=session)
    manager.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("headlinelens.fetch.requests.Session", lambda: manager)
    results = fetch_watchlist(("BAD", "DEMO"), now, 24)
    assert "Timeout: read timed out" == results[0].error
    assert len(results[1].items) == 3


def test_invalid_xml_is_source_error(now):
    session = Mock()
    session.get.return_value.content = b"<html/>"
    assert fetch_ticker("DEMO", now, 24, session).error.startswith("FeedError:")


@pytest.mark.parametrize(
    "link", ["http://[broken", "https://", "https://example.com/a b"]
)
def test_malformed_links_do_not_crash_feed(link):
    xml = f"<rss><channel><item><title>Test</title><link>{link}</link><pubDate>Fri, 06 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>".encode()
    result = parse_rss(xml, "DEMO")
    assert result.items == []
    assert "valid HTTP(S) link" in result.warnings[0]
