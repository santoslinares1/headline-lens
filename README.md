# HeadlineLens

**From a ticker watchlist to a traceable morning news brief — no API key.**

HeadlineLens is a Python research-workflow project by **Santos Linares**. It collects public Yahoo Finance RSS headlines for specific securities, removes duplicates, filters a rolling time window, and writes a concise Markdown memo with links and possible catalyst tags. A full-window CSV and a source-health file sit alongside the memo.

It complements **StatementLens**, a filings analyzer: financial statements explain the business; HeadlineLens helps triage what may have changed since the last review. The aim is a repeatable junior equity/credit analyst workflow, not a trading signal or an automated investment recommendation.

## Quick start

Python 3.10+ (CI uses 3.12).

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
headlinelens
```

The default run reads `watchlist.yml` in the working directory and writes `output/watchlist_brief.md`, `output/headlines.csv` and `output/source_status.json`. If no local watchlist exists, it uses a bundled copy of the defaults. An explicitly requested missing or invalid file is an error, never silently ignored.

```bash
headlinelens AAPL MSFT NVDA --hours 24
headlinelens --watchlist watchlist.yml --hours 36 -o /tmp/headline-demo
python -m headlinelens JPM XOM --json -o output
```

`--json` additionally writes `headlines.json` (not a JSON stdout stream). CLI symbols replace only the followed `tickers` list for that run; market context is retained from the file. Symbols are uppercased and validated, and repeated names are fetched once.

### Watchlist

```yaml
# Edit this list to follow different names.
market:
  - SPY
tickers:
  - AAPL
  - MSFT
  - NVDA
  - JPM
  - XOM
```

`market` securities appear first in a separate context section. An empty market list is allowed; at least one symbol is required overall.

## What happens under the hood

1. **Fetch** one public feed per symbol: `https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL&region=US&lang=en-US`. Requests identify the project and contact email in a descriptive User-Agent. There are no API keys, credentials, paid services or hidden model calls. Network timeouts are bounded (5-second connect / 20-second read); no aggressive retries.
2. **Parse and normalize** RSS XML with Python's standard library. Strip HTML from display text, require valid timezone-aware publication dates and HTTP(S) links, and report skipped records. Keep only `now - hours <= published_at <= now`, normalized to UTC. Undated and future items are not guessed into the window.
3. **Deduplicate** within each symbol by normalized title + link. Title case/whitespace and common URL tracking parameters/fragments are ignored. Different links with the same title remain distinct; a story associated with two symbols is retained under each.
4. **Tag possible catalysts** with small, inspectable word-boundary rules on title + RSS summary. Earnings, guidance, M&A, analyst upgrades/downgrades, lawsuits, investigations, FDA, public/share offerings, buybacks, dividends and layoffs are supported. Generic “offering” alone does not trigger a financing tag. There is no sentiment prediction, entity resolution or claim verification.
5. **Render** market context first, then one section per followed ticker. Show at most five items per section, prioritizing tagged items, then recency. Every item includes source, UTC publication time, link and tags. CSV contains **all** retained items, newest first within each symbol. Spreadsheet-formula prefixes in CSV text are escaped with an apostrophe. JSON preserves original text.

The memo is a deterministic analyst-style **news triage sheet**, not a generative narrative. “Most relevant” is a disclosed keyword/recency proxy; tagging does not prove company impact. No headlines, price changes, or investment conclusions are invented.

### Source failures are not quiet news days

An unavailable feed gets a **Source error** in that symbol's section while other symbols continue. Empty successful feeds receive “No material headlines in the lookback.” That phrase only means no usable in-window RSS records, not that no significant company event occurred. Parse warnings are also visible in the memo and source-health JSON.

Exit codes: `0` complete source coverage, `1` degraded coverage (source error or skipped records; reports still written), `2` invalid input/output failure. An empty but successfully fetched news window is a valid run.

## Samples

- [Fixture brief](examples/fixture/watchlist_brief.md): explicitly synthetic **DEMO / MARKET / QUIET** data, generated offline from checked-in XML. The company and events are fictional; never presented as live news.
- Recreate it: `python examples/generate_fixture.py` after installing the package.
- [Live build-time brief](examples/live/watchlist_brief.md): 49 ticker/headline observations across SPY, AAPL, MSFT, NVDA, JPM and XOM, with no source errors. See [snapshot notes](examples/live/README.md); this is a historical snapshot, not a continuously updating report.

Fixture excerpt (fictional):

```text
### DEMO
Showing 3 of 3 in-window headlines (tagged first, then newest).
- DemoCo reports earnings and raises guidance
  - Source: Fixture Wire | Published: 2026-11-06 10:00 UTC
    Possible catalysts: earnings, guidance
```

## MCP server (stdio)

The official Python MCP SDK is included in the default install. Install into the
project's virtual environment with `python -m pip install -e ".[dev]"`, then run:

```bash
headlinelens-mcp
# Equivalent:
python -m headlinelens.mcp_server
```

The server uses **stdio**, not HTTP: a client launches it and exchanges protocol
messages on stdin/stdout. Running it alone waits for a client; `--help` exits
without starting it.

Tools:

- `get_brief(hours=24, tickers=None)` fetches a fresh Markdown brief using the
  existing RSS and report pipeline. A ticker list overrides followed names only
  for that call; saved market context stays. Source failures/warnings remain
  visible in the brief. No report files are written.
- `add_ticker(symbol, group="tickers")` normalizes and persists a symbol in
  `tickers` or `market`, without duplicating it within that group. Returns both groups.
- `remove_ticker(symbol)` removes it from both groups and persists the result.
  Missing symbols are a no-op; removing the last symbol is refused.
- `search_catalysts(ticker=None, hours=24, catalyst=None)` fetches tagged items
  for one symbol or the entire current watchlist, including market context.
  A single-symbol query does not change the saved list. The optional catalyst
  matches an exact tag case-insensitively (e.g. `earnings`, `investigation`,
  `merger/acquisition`, `FDA`); unknown tags return no matches. The result has
  `items` (ticker, title, source, published_at, link, tags), `errors`, and `warnings`.
  Publication timestamps are ISO 8601 UTC. All news is from RSS; tags are heuristic.

Hours must be positive and finite, at most 87600 (the same bound as the CLI).
The MCP default watchlist is **the project-root `watchlist.yml`, resolved from the
package location**, not the launch directory. Mutations persist there. To select
another existing YAML file, set `HEADLINELENS_WATCHLIST` to its absolute path.
Use the editable install shown above; a non-editable wheel install should set
this variable explicitly to a writable watchlist. Missing/invalid files are errors.
Writes use atomic file replacement and an in-process lock. Run only one server
process per watchlist: concurrent independent processes/manual edits are not locked.
Saving rewrites YAML formatting/comments but preserves group ordering and names.

Example MCP client configuration (`mcp.json` for Cursor, or the equivalent
`mcpServers` section in a Claude Desktop configuration): replace the placeholder
with the absolute path on the machine running your MCP client. The virtualenv
must already contain the editable install; no activation or working-directory
setting is needed.

```json
{
  "mcpServers": {
    "headlinelens": {
      "command": "/absolute/path/to/headline-lens/.venv/bin/headlinelens-mcp",
      "args": []
    }
  }
}
```

Optionally add `"env": {"HEADLINELENS_WATCHLIST": "/absolute/path/to/watchlist.yml"}`
to the server entry. This is a local research server: it does not schedule or
send briefs, verify news claims, or place trades. Feed requests are sequential;
large watchlists and slow feeds can take longer than a client's tool timeout.

## Engineering & tests

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m headlinelens --help
```

Tests are offline and mock HTTP/CLI boundaries: RSS parsing, malformed inputs, source failures, continuation, date-window edges, duplicate rules, catalyst tags, watchlist validation, memo ordering and caps, CSV/JSON exports, and CLI success/degraded/invalid paths. GitHub Actions runs pytest on Python 3.12 on pushes and pull requests once uploaded.

```text
src/headlinelens/
  mcp_server.py   stdio MCP tools and live watchlist operations
  cli.py          arguments and orchestration
  watchlist.py    validated YAML + packaged defaults
  fetch.py        RSS HTTP adapter and explicit source status
  normalize.py    headline model, normalization and rolling window
  tagger.py       conservative, inspectable keyword rules
  report.py       Markdown, CSV and JSON outputs
  __main__.py     python -m headlinelens
tests/            offline fixtures and unit/integration tests
examples/         reproducible fixture and live-run artifacts
```

## Limitations

- Yahoo RSS may be delayed, incomplete, rate-limited or unavailable. Coverage can differ by symbol and stories may be broadly related rather than directly about the company. There is no paid-source completeness guarantee.
- Only RSS metadata is used; articles are not scraped. Headlines and summaries may omit context, repeat syndicated stories, or contain stale claims. Date filtering uses the feed's publication time.
- Tags are heuristic. Negated events, rumors, and product upgrades can trigger false positives; unrecognized wording can be missed. Read the source before drawing conclusions.
- No delivery scheduler, email sending, price data, portfolio returns or order execution is included. Run the CLI each morning yourself or wire it to your own scheduler later; generation time is UTC, not a promise of delivery at a particular hour.
- This is a portfolio research tool, **not investment advice**. External headline rights belong to their publishers.

## License

MIT. Copyright (c) 2026 Santos Linares.
