# Screening rules

What a stock must do to appear in this screener, and what it must do to survive
to the final lineup. Every number here is a constant in `src/`, not prose that
drifted away from the code.

The screen runs in three stages. Each stage is cheap-then-expensive: a batched
fundamental query over thousands of tickers, then an expensive per-ticker chart
audit over the few hundred that survive, then ranking.

```
universe filter        ~12,000 US stocks  →  ~500
   ↓
CAN SLIM screen        6 factors, pass ≥4  →  ~100
   ↓
chart audit            5 checks, 0–5 score →  ~15–40
   ↓
rank + sector tilt                          →  final lineup
```

---

## Stage 0 — Universe

Applied inside the TradingView screener query, before any scoring.

| Filter | Value | Why |
|---|---|---|
| Market capitalisation | ≥ $300,000,000 | Below this, spreads widen and a single order moves the price. The chart audit's volume checks also stop being meaningful. |
| Instrument type | `stock` | Excludes ETFs, funds, and trusts. A sector ETF passing CAN SLIM tells you nothing about a tradeable company. |
| Order | Volume, descending | The scan returns a bounded slice. Ranking by liquidity first means the slice is the tradeable part of the market, not an arbitrary alphabetical cut. |
| Slice size | 500 per market | Free-tier call budget. A larger slice does not improve the lineup, because the chart audit is capped anyway. |
| Markets | `america` (~12,000), `malaysia` (~1,100) | Two separate taxonomies; Bursa is screened with the same rules but a different universe call. |

---

## Stage 1 — The CAN SLIM screen

Six factors. Each factor contributes a **pass flag** and a **0–2 score**.

A stock must pass **at least 4 of the 6** to remain. That majority rule is
deliberate: see "Why a majority, not a veto" below.

### C — Current quarterly earnings

| | |
|---|---|
| **Rule** | Quarterly diluted EPS, year-over-year growth **> 25%** |
| **Field** | `earnings_per_share_diluted_yoy_growth_fq` |
| **Score** | `clip(growth, -100, 500) / 50`, capped 0–2 |
| **Missing data** | Treated as fail (`-999`), never as pass |

The single strongest signal O'Neil used: the most recent reported quarter
accelerating. 25% is the canonical floor. The clip at 500% prevents one
distorted quarter from dwarfing every other factor in the total.

### A — Annual earnings

| | |
|---|---|
| **Rule** | Annual diluted EPS, year-over-year growth **> 25%** |
| **Field** | `earnings_per_share_diluted_yoy_growth_fy` |
| **Score** | `clip(growth, -100, 200) / 50`, capped 0–2 |
| **Bonus** | **+0.5** when 5-year EPS CAGR > 25% |
| **Missing data** | Treated as fail |

One good quarter can be a cost cut or a one-off contract. Three years of
compounding growth is much harder to fake, so annual growth is scored
separately rather than folded into C.

### N — New

| | |
|---|---|
| **Rule** | Price **within 15%** of the 52-week high |
| **Field** | `(close - price_52_week_high) / price_52_week_high × 100` |
| **Threshold** | `pct_from_52w_high ≥ -15` |
| **Score** | `((100 + pct_from_52w_high) / 20)`, capped 0–2 |

**This is a proxy, and worth being blunt about it.** O'Neil's N means a new
product, new management, new industry condition. A data feed cannot tell you
that. What it *can* tell you is that there is no trapped supply overhead — a
stock near its high has nobody sitting on a loss waiting to sell into strength.
That is the tradeable half of the idea.

### L — Leader

| | |
|---|---|
| **Rule** | Close **above the 200-day SMA** |
| **Score** | `(pct_above_sma200 / 20) + 1`, capped 0–2 |
| **Bonus** | **+0.3** if close > SMA50 · **+0.2** if RSI between 50 and 80 |

Filters out laggards in long-term downtrends. The RSI band is deliberately
two-sided: below 50 is weak, above 80 is extended and prone to a shakeout.

### I — Institutional sponsorship

| | |
|---|---|
| **Rule** | Analyst recommendation mark **> 0.1** (scale −1.0 sell … +1.0 buy) |
| **Field** | `recommendation_mark` |
| **Score** | `(mark + 1) / 2 × 2`, capped 0–2 |
| **Bonus** | **+0.3** when more than 50% of analysts rate buy |
| **Missing data** | Treated as fail |

**The weakest factor in the model, and it earns no veto.** O'Neil's I means
13F filings — real institutional accumulation. A batch screener has no cheap
access to that, so analyst sentiment stands in as a proxy. It is correlated
with institutional interest but it is not the same measurement, and treating it
as a veto would reject good companies that analysts simply do not cover.

### M — Market direction

| | |
|---|---|
| **Rule** | 10-day relative volume **> 1.0** |
| **Field** | `relative_volume_10d_calc` |
| **Score** | `clip(rel_volume, 0, 3)` |
| **Bonus** | **+0.3** when the day is up **and** relative volume > 1.2 |

Per-stock only. Above-average volume is treated as evidence of accumulation.
Genuine market direction — index trend, distribution days — is a separate
portfolio-level input in the full system, not something this screen can infer
from one ticker.

### Aggregate

```
canslim_total  = C + A + N + L + I + M       (score, used for ordering)
canslim_passes = count(pass flags)           (0–6, used as the gate)
```

---

## Stage 2 — Chart audit

Runs **only** on Stage 1 survivors, because it needs a year of daily OHLCV per
ticker and that is the expensive part of any free data tier. Five checks, one
point each, **0–5**.

| # | Check | Threshold | What it is really asking |
|---|---|---|---|
| 1 | Moving averages stacked | SMA20 > SMA50 > SMA200 | Is the trend ordered across all horizons, or is it a bounce inside a downtrend? |
| 2 | RS line at a 3-month high | current RS ≥ 99% of the 63-day max | Is the stock beating the index *now*? |
| 3 | Volume dry-up (VDU) | 3-day average volume < **60%** of the 50-day baseline | Is supply actually shrinking while the base forms? |
| 4 | Volatility contraction (VCP) | last 5-day range < **50%** of the prior 20-day range | Is the base tightening toward a pivot? |
| 5 | 3-month excess return | stock 3M − benchmark 3M > 0 | Is there positive relative performance to trade? |

**Unknown is not zero.** If a ticker lacks enough bars, `audit()` returns
`None` and the name is recorded as unaudited. Scoring a data gap as a bad chart
is how a pipeline quietly starts rejecting good stocks.

**Bursa caveat, stated rather than hidden:** the chart audit returns a static
3/5 for Bursa because free daily OHLCV for `.KL` names is not reliably
available. Bursa candidates are therefore ranked on fundamentals plus sector
tilt, not on their chart. If you are reading a Bursa lineup, do not read the
chart score as a measurement.

---

## Stage 3 — Ranking

Both gate scores are different units, so they are blended, not summed:

```
final_rank = screener_score × 0.60 + chart_score × 0.40
```

Fundamentals carry the larger weight because a good chart on a deteriorating
business is the more common way to lose money. The chart is the timing input,
not the thesis.

### Sector tilt (M factor at portfolio level)

Reads the latest sector relative-strength ranking and adjusts `final_rank`:

| Sector RS rank | Adjustment |
|---|---|
| 1–3 | **+0.5** |
| 4–6 | **+0.2** |
| 7–10 | no change |
| 11+ | **−0.3** |

Sector labels from the data feed are mapped onto the ranking taxonomy through
an alias table, then an industry-keyword fallback.

If no sector table exists, the tilt is **skipped entirely** — not defaulted to
zero. "No ranking available" and "ranked last" are different claims, and
collapsing them would silently push every name into the penalty bucket.

---

## Why a majority, not a veto

A single-factor veto makes the screen brittle in a specific way: a company with
25%+ EPS growth that happens to sit 16% off its high is not a bad business, it
is a stock that has not set up yet. Vetoing it means the screener only ever
shows you names that are already extended.

Requiring 4 of 6 keeps the spirit of the model — most of it must be true — while
letting the ranker sort quality afterwards. The pass count is also stored, so
you can tighten to 5 or 6 yourself without touching the scoring code.

---

## Freshness — refusing stale screens

A screen built from a scan older than **3 days** is refused rather than used.
The table records the scan date, so this is checkable rather than assumed:

| Condition | Behaviour |
|---|---|
| Newest scan is today | proceed |
| Newest scan is 1–3 days old | proceed, loudly logged |
| Newest scan is > 3 days old | refuse — return nothing |
| No rows at all | refuse |

Reason: the chart audit is measured against today's price. Screening yesterday's
fundamentals against today's chart produces a lineup that was never testable.

---

## What this screener does not claim

- It does not predict returns. It orders candidates.
- The I factor is analyst sentiment, not institutional ownership.
- The N factor is price proximity, not news.
- The M factor is per-stock volume, not market direction.
- Bursa chart scores are a placeholder, not a measurement.
- A passing score is a reason to look at a chart, not a reason to buy.
