"""Load and validate watchlists; preserve user ordering."""

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
import re
import os
import tempfile

import yaml


@dataclass(frozen=True)
class Watchlist:
    market: tuple[str, ...]
    tickers: tuple[str, ...]

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.market + self.tickers))


def normalize_symbols(values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("Watchlist symbols must be a list of strings.")
    result = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("Each ticker must be a string.")
        symbol = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=\-]{0,19}", symbol):
            raise ValueError(f"Invalid ticker: {value!r}")
        if symbol not in result:
            result.append(symbol)
    return tuple(result)


def load_watchlist(path: Path | None = None) -> Watchlist:
    if path is None:
        local = Path("watchlist.yml")
        text = (
            local.read_text(encoding="utf-8")
            if local.exists()
            else files("headlinelens")
            .joinpath("default_watchlist.yml")
            .read_text(encoding="utf-8")
        )
    else:
        text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or set(data) - {"market", "tickers"}:
        raise ValueError(
            "Watchlist must be a mapping containing only market and tickers."
        )
    watchlist = Watchlist(
        normalize_symbols(data.get("market", [])),
        normalize_symbols(data.get("tickers", [])),
    )
    if not watchlist.symbols:
        raise ValueError("Watchlist must contain at least one symbol.")
    return watchlist


def save_watchlist(watchlist: Watchlist, path: Path) -> None:
    """Validate and atomically replace YAML; never save an empty watchlist."""
    validated = Watchlist(
        normalize_symbols(watchlist.market), normalize_symbols(watchlist.tickers)
    )
    if not validated.symbols:
        raise ValueError("Watchlist must contain at least one symbol.")
    text = yaml.safe_dump(
        {"market": list(validated.market), "tickers": list(validated.tickers)},
        sort_keys=False,
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
