"""Command-line application; network failures produce an explicitly partial memo."""

import argparse
from datetime import datetime, timezone
import math
from pathlib import Path
import sys

import yaml

from .fetch import fetch_watchlist
from .report import write_reports
from .watchlist import Watchlist, load_watchlist, normalize_symbols


def positive_hours(value: str) -> float:
    try:
        hours = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "hours must be a positive finite number"
        ) from exc
    if not math.isfinite(hours) or not 0 < hours <= 87600:
        raise argparse.ArgumentTypeError(
            "hours must be positive and at most 87600 (10 years)"
        )
    return hours


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an equity-watchlist news brief from public Yahoo Finance RSS."
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        help="Override followed tickers; market context stays from the watchlist",
    )
    parser.add_argument(
        "--watchlist",
        type=Path,
        help="YAML file (default: ./watchlist.yml, then bundled defaults)",
    )
    parser.add_argument(
        "--hours",
        type=positive_hours,
        default=24.0,
        help="Lookback hours (default: 24)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output"),
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also write headlines.json; does not change stdout",
    )
    args = parser.parse_args(argv)
    try:
        watchlist = load_watchlist(args.watchlist)
        if args.tickers:
            watchlist = Watchlist(watchlist.market, normalize_symbols(args.tickers))
        now = datetime.now(timezone.utc)
        results = fetch_watchlist(watchlist.symbols, now, args.hours)
        memo = write_reports(
            args.output, watchlist, results, now, args.hours, args.json
        )
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(f"HeadlineLens: {exc}", file=sys.stderr)
        return 2
    print(f"Brief written: {memo.resolve()}")
    print(f"Headlines retained: {sum(len(r.items) for r in results)}")
    for result in results:
        if result.error:
            print(f"{result.ticker}: {result.error}", file=sys.stderr)
        for warning in result.warnings:
            print(f"{result.ticker}: {warning}", file=sys.stderr)
    return 1 if any(r.error or r.warnings for r in results) else 0
