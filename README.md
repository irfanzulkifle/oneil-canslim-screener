# O'Neil CAN SLIM Screener

A three-stage equity screener that turns a broad market universe into a short,
ranked lineup: fundamentals first, chart structure second, sector strength last.

Built for US and Bursa Malaysia listings. The rules are explicit constants, not
prose — see [`docs/SCREENING-RULES.md`](docs/SCREENING-RULES.md) for every
threshold and why it is set where it is.

---

## The idea in one paragraph

Most screeners return too much. A growth filter alone hands you a hundred names
and no opinion. This one applies three filters in series, each one more
expensive than the last, and each one answering a different question: *is the
business growing* (CAN SLIM factors), *is the chart set up right now* (chart
audit), and *is the sector in favour* (relative-strength tilt). What comes out
is a ranked list you can actually work through, with the reason each name is
there recorded alongside it.

---

## How a stock gets in

```
Stage 0   Universe       market cap ≥ $300M · stocks only · top 500 by volume
   ↓      ~12,000 US names
Stage 1   CAN SLIM       six factors, must pass at least 4
   ↓      ~100 survive
Stage 2   Chart audit    five checks, scored 0–5
   ↓      top N by budget
Stage 3   Rank           fundamentals 60% + chart 40%, then sector tilt
```

### Stage 1 — the six factors

| Factor | Rule | Threshold |
|---|---|---|
| **C** Current quarterly earnings | Diluted EPS, YoY growth | **> 25%** |
| **A** Annual earnings | Diluted EPS, YoY growth | **> 25%** (bonus if 5-year CAGR > 25%) |
| **N** New | Distance from 52-week high | **within 15%** |
| **L** Leader | Close vs 200-day SMA | **above** (bonus if > SMA50, RSI 50–80) |
| **I** Institutional | Analyst recommendation mark | **> 0.1** on a −1…+1 scale |
| **M** Market direction | 10-day relative volume | **> 1.0** (bonus if up day and > 1.2) |

Each factor also carries a 0–2 score. A candidate must pass **at least 4 of 6**
to survive — a majority rule rather than a veto, so a strong company that has
not yet set up is not thrown away before the chart audit can judge it.

### Stage 2 — the five chart checks

| Check | Threshold |
|---|---|
| Moving averages stacked | SMA20 > SMA50 > SMA200 |
| Relative-strength line at a 3-month high | within 1% of the 63-day RS max |
| Volume dry-up | 3-day volume < **60%** of the 50-day baseline |
| Volatility contraction | 5-day range < **50%** of the prior 20-day range |
| 3-month excess return vs benchmark | **> 0** |

One point each, 0–5. A ticker without enough history returns `None` and is
recorded as **unaudited** — a data gap is never scored as a bad chart.

### Stage 3 — ranking

```
final_rank = screener_score × 0.60 + chart_score × 0.40
```

Then a sector tilt from the latest sector relative-strength table: ranks 1–3 get
**+0.5**, ranks 4–6 get **+0.2**, ranks 11+ get **−0.3**. When no sector table
exists the tilt is skipped entirely, not defaulted to zero — "no ranking" and
"ranked last" are different claims.

---

## What it will not do

This is a screener, not a signal service, and the limits are worth stating
plainly rather than burying:

- **It does not predict returns.** It orders candidates so a human can review
  the best few first.
- **The I factor is analyst sentiment, not institutional ownership.** Real 13F
  accumulation is not available from a batch screen. This proxy earns no veto
  for exactly that reason.
- **The N factor is price proximity, not news.** Nothing here knows about a new
  product or a management change.
- **The M factor is per-stock volume.** True market direction is a separate,
  portfolio-level input.
- **Bursa chart scores are a placeholder.** Free daily OHLCV for `.KL` names is
  not reliably available, so those candidates are ranked on fundamentals plus
  sector tilt and their chart score should not be read as a measurement.
- **A passing score is a reason to look at a chart,** not a reason to buy.

---

## Project layout

```
src/scoring.py        six CAN SLIM factors, pass flags and 0–2 scores
src/chart_audit.py    five chart checks, 0–5, returns None on insufficient data
src/ranking.py        weighted blend + sector relative-strength tilt
tests/                32 tests, every threshold asserted on both sides
docs/SCREENING-RULES.md   full rule tables with rationale
```

The modules are pure: they take DataFrames and dicts, and touch no database and
no network. Data acquisition is deliberately kept outside so the rules can be
tested without a live feed.

---

## Running it

```bash
pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

You need a DataFrame with the columns listed in `src/scoring.py`, which mirror
the TradingView screener field names:

```
close, change, SMA50, SMA200, RSI,
price_52_week_high, price_52_week_low,
earnings_per_share_diluted_yoy_growth_fq,
earnings_per_share_diluted_yoy_growth_fy,
earnings_per_share_diluted_5y_growth_fy,
recommendation_mark, recommendation_buy, recommendation_total,
relative_volume_10d_calc
```

Typical use:

```python
from src.scoring import score_canslim, survivors
from src.chart_audit import audit
from src.ranking import rank, apply_m_factor

scored = score_canslim(raw)          # raw: one row per ticker
shortlist = survivors(scored)        # pass ≥ 4 of 6, best first

candidates = []
for _, row in shortlist.iterrows():
    chart = audit(ohlcv[row["ticker"]], ohlcv["SPY"])
    if chart is None:
        continue                     # unaudited, not a zero
    candidates.append({
        "ticker": row["ticker"],
        "sector": row["sector"],
        "industry": row["industry"],
        "screener_score": row["canslim_total"],
        "chart_score": chart["score"],
    })

lineup = apply_m_factor(rank(candidates), sector_map)
```

---

## Tests

32 tests, all offline. Each boundary is asserted from both directions — for
example `C` passes at 26% and fails at exactly 25%, because the rule is
strictly greater than. `test_empty_sector_map_skips_adjustment` exists to stop
a future refactor from quietly turning a missing sector table into a penalty
for every name.

```
Ran 32 tests in 0.43s
OK
```

---

## Licence

MIT — see [`LICENSE`](LICENSE).
