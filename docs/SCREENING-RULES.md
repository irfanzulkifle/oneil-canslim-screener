# Screening rules

Every rule a stock must satisfy to appear in this screen, and every rule it must
satisfy to survive to the end. The numbers are constants in
[`oneil/rules.py`](../oneil/rules.py); this document explains them, and the code
enforces them. When the two disagree, the code is right and this file is a bug.

```
universe filter      stocks only · cap ≥ $500M · top 500 by volume
   ↓
weekly O'Neil gate   close > 10W SMA · close > 30W SMA · weekly RSI(7) > 60
   ↓
CAN SLIM screen      C/A/N/L/I/M, pass ≥ 3 (≥ 4 in the daily batch)
   ↓
chart audit          5 checks, 0–5, only on survivors
   ↓
rank                 screen 60% + chart 40% + sector tilt, ceiling 6.1
   ↓
deploy gate          market-level: VIX, 10Y shock. Separate from any stock.
```

Each stage is more expensive than the last, so the cheap batched filters run
first and the per-ticker work runs on the few hundred that survive.

---

## Stage 0 — Universe

Applied in the vendor query, before any scoring.

| Filter | Value | Why |
|---|---|---|
| Market capitalisation | ≥ $500,000,000 | Below this, spreads widen and one order moves the price. The volume checks also stop being meaningful. Production's deployed wrapper passes 500M even though the library default is 300M; the 2026-11-03 scan's smallest name was $556M, so 500M is the operative floor. |
| Instrument type | `stock` | Excludes ETFs, funds and trusts. A sector ETF passing CAN SLIM says nothing about a tradeable company. |
| Order | Volume, descending | The scan returns a bounded slice. Ranking by liquidity first makes the slice the tradeable part of the market, not an alphabetical cut. |
| Slice size | 500 per market (300 weekly) | Free-tier call budget. The chart audit is capped anyway, so a larger slice does not improve the lineup. |
| Markets | US (~12,000 listed), Bursa (~1,100) | Two taxonomies, same rules, different universe call. |

In the production database the universe table holds **7,612 rows**, of which
**5,149** have a known market cap and **2,805** clear the $500M floor. Quoting
7,612 as "the tradeable universe" is a row count pretending to be a screen
result.

---

## Stage 1 — The weekly gate (what gets a stock *seen*)

This is the stage that most screeners do not have, and the reason the output is
short. It runs in a single batched query and asks nothing about the business:
**is this stock going up?**

| Condition | Value | Notes |
|---|---|---|
| Close > 10-week SMA | strict `>` | Short-term trend |
| Close > 30-week SMA | strict `>` | Intermediate trend |
| Weekly RSI(7) | **> 60** | Momentum on weekly bars, so one noisy session cannot flip it |
| Market cap | ≥ $1,000,000,000 | Higher than the daily floor: this list feeds trade candidates |
| Instrument | `stock` | As above |

On 2026-11-03 the weekly table ended with **113 US names and 28 Malaysian**
names. Those counts are the *scored* survivors, not the raw trend-gate output:
the table only stores names that clear the trend query and then score at least
3 of 5 on the weekly factors below. The intermediate count was never persisted,
so do not quote 113 as "names above their 10 and 30-week averages".

### The five weekly factors

```
W_total = C_score + A_score + clip(pct_above_10w, 0, 30)/10 + M_score + RSI7/50
W_passes = count(C, A, N, L, M)
```

| Factor | Pass rule |
|---|---|
| C | quarterly EPS YoY **> 25%** |
| A | annual EPS YoY **> 25%** |
| N | within **10%** of the 52-week high |
| L | above both weekly SMAs, weekly RSI(7) between **55 and 85** |
| M | weekly relative volume **> 1.0** |

The N threshold is 10% here and 15% on the daily screen. That is deliberate: the
weekly list is the trade list, so it demands a tighter base. `W_total` is a
sorting score in the low twenties, not a 0–5 count; a comment in the production
`gate_rules.py` calls it 0–5 and is wrong.

Weekly volume dry-up is also its own rule: the last completed week's volume
below 60% of the 10-week average, with the in-progress week's stub bar dropped
before the ratio is computed. Without that drop, a Tuesday "week" shows a
0.10–0.30 ratio and every name looks like it is drying up.

Deliberate consequence: weekly RSI 91 passes. The gate is a trend question, not
a valuation question. Extension is handled where it belongs, by the L factor's
55–85 score band and by the VCP check in the chart audit.

---

## Stage 2 — CAN SLIM (what makes a stock *pass*)

Six factors. Each contributes a pass flag and a 0–2 score.

| Factor | Pass rule | Score | Bonus |
|---|---|---|---|
| C | quarterly EPS YoY **> 25%** | `clip(g, −100, 500) / 50`, capped 0–2 | — |
| A | annual EPS YoY **> 25%** | `clip(g, −100, 200) / 50`, capped 0–2 | +0.5 if 5Y CAGR > 25% |
| N | within **15%** of the 52-week high | `(100 + pct_from_high) / 20`, capped 0–2 | — |
| L | close **> SMA200** | `pct_above_sma200 / 20 + 1`, capped 0–2 | +0.3 if > SMA50 · +0.2 if RSI 50–80 |
| I | analyst mark **> 0.1** (scale −1…+1) | `(mark + 1) / 2 × 2`, capped 0–2 | +0.3 if > 50% buy ratings |
| M | 10-day relative volume **> 1.0** | `clip(rel_vol, 0, 3)` | +0.3 if up day and rel_vol > 1.2 |

```
canslim_total  = C + A + N + L + I + M      (score, used for ordering)
canslim_passes = count(pass flags)          (0–6, used as the gate)
```

**Missing data fails a factor.** A null EPS growth is not unknown-but-promising;
it is a company whose numbers could not be verified, and it does not get the
benefit of the doubt.

### Why a majority, not a veto

A single-factor veto makes a screen brittle in a specific way: a company with
25% earnings growth that sits 16% off its high is not a bad business, it is a
stock that has not set up yet. Vetoing it means the screen only ever shows names
that are already extended, which is the worst time to buy them.

Requiring 3 of 6 (and 4 of 6 in the stricter daily batch) keeps the spirit of the
model, most of it must be true, while letting the ranker sort quality afterwards.
The pass count is stored, so the bar can be tightened without touching the
scoring code.

### The two weak factors, named

**I is analyst sentiment, not institutional ownership.** O'Neil's I means 13F
accumulation. A batch screen has no cheap access to that, so the analyst
recommendation mark stands in. It correlates with institutional interest; it is
not the same measurement. It is the weakest factor in the model and it is
exactly why the pass bar is a majority rather than a veto.

**N is price proximity, not news.** O'Neil's N means a new product, a new
management team, a new industry condition. A data feed cannot see any of that.
What it can measure is that there is no trapped supply overhead: a stock near its
high has nobody sitting on a loss waiting to sell into strength. That is the
tradeable half of the idea, and it is the half that is used.

---

## Stage 3 — Chart audit (0–5)

Runs only on survivors. Five checks, one point each. Too few bars returns
`None`, and the name is recorded as **unaudited**, never scored as zero.

| # | Check | Threshold | What it is asking |
|---|---|---|---|
| 1 | Moving averages stacked | SMA20 > SMA50 > SMA200 | Is the trend ordered across horizons, or is this a bounce inside a downtrend? |
| 2 | RS line at a 3-month high | current ratio ≥ **99%** of the 63-day max | Is the stock beating the index now? |
| 3 | Volume dry-up | 3-day average < **60%** of the prior 50-day | Is supply shrinking while the base forms? |
| 4 | Volatility contraction | last 5-day range < **50%** of the prior 20-day | Is the base tightening toward a pivot? |
| 5 | 3-month excess return | stock 3M − benchmark 3M **> 0** | Is there relative performance to trade? |

Checks 1–4 are computed on daily bars and expressed as percentages of price so
they compare across names at different price levels. Check 2 uses the ratio of
stock to benchmark, not the stock's own price, so a stock can score here while
still below its own high.

---

## Stage 4 — Ranking

The two gate scores are different units (0–6 and 0–5), so they are blended, not
summed:

```
final_rank = screener_score × 0.60 + chart_score × 0.40 + sector tilt
```

Fundamentals carry the larger weight because a good chart on a deteriorating
business is the more common way to lose money. The chart is the timing input,
not the thesis.

### Sector tilt (M at portfolio level)

| Sector RS rank | Adjustment |
|---|---|
| 1–3 | **+0.5** |
| 4–6 | **+0.2** |
| 7–10 | no change |
| 11+ | **−0.3** |

No sector table means no tilt at all, not a zero tilt applied to everything.
"No ranking" and "ranked last" are different claims; collapsing them would push
every name into the penalty bucket on a day the sector table failed to load.

### The ceiling

```
6 × 0.60 + 5 × 0.40 + 0.5 = 6.1
```

This is the arithmetic maximum of the rank, and it is asserted in the tests.
A threshold above the maximum is not a strict filter, it is an outage: the
screen returns nothing for months and every downstream report looks calm. In
2026 the production system had a `final_rank ≥ 7.0` gate against a formula whose
ceiling is 6.1; it produced 68 consecutive HOLD decisions and zero trades before
anyone traced why. `rank_is_reachable()` exists so that mistake cannot come back
silently.

---

## Stage 5 — Deploy gate (market-level)

A ranked candidate is not permission to trade. This gate answers a different
question: **is today a day to buy anything?**

| Leg | Rule | Effect |
|---|---|---|
| VIX | strictly **< 20** | At or above 20: halt. 20.00 is a halt, not a pass. |
| 10Y rate shock | no rise ≥ **25bp** over 10 sessions | Shock: halt |
| 10Y level | > 4.60% | High but stable: half position size, not a ban |
| Missing data in any leg | — | No verdict. A blank leg is not a pass |

The 10Y rule is a shock detector, not a level ban, and that distinction cost 76
trading days to learn. A level-based version ("halt while 10Y > 4.80%") stayed
on through a market that was making higher highs, because the level never came
back down. A rate *shock* is what flushes growth names; a repriced level that
stops moving is not a risk event, it is the new normal.

---

## Boundaries, exactly

Thresholds are tested from both sides, because an off-by-one is invisible in a
lineup and only shows up months later as "why did this never appear".

| Rule | Fails | Passes |
|---|---|---|
| C / A EPS growth | 25.0% | 25.1% |
| N distance from high (daily screen) | −15.1% | −15.0% |
| N distance from high (weekly gate) | −10.1% | −10.0% |
| Weekly RSI gate | 60.0 | 60.1 |
| Weekly L score band | 54.9 or 85.1 | 55.0 … 85.0 |
| M relative volume | 1.00 | 1.01 |
| VDU ratio | 0.60 | 0.59 |
| VCP contraction | 0.50 | 0.49 |
| Rank floor | 3.99 | 4.00 |

Missing values always land on the failing side.

---

## Freshness — refusing stale screens

A screen built from a scan older than **3 days** is refused, not used. The
table records the scan date, so this is checkable rather than assumed.

| Condition | Behaviour |
|---|---|
| Newest scan is today | proceed |
| Newest scan is 1–3 days old | proceed, loudly logged |
| Newest scan is > 3 days old | refuse, return nothing |
| No rows at all | refuse |

The chart audit is measured against today's price. Screening last week's
fundamentals against today's chart produces a lineup that was never testable.

---

## Deployed system: known deviations

This document describes the rule set as specified and implemented in `oneil/`.
The private TITAN system that runs it daily has drifted in eight places. They
are listed because a spec that quietly describes something else is worse than no
spec.

| # | Area | This repo | Deployed | Evidence |
|---|---|---|---|---|
| 1 | Universe floor | $500M | 500M via wrapper, 300M library default | `tv-scan:12`, `canslim_tv.py:57` |
| 2 | Screener factors | 6 (C/A/N/L/I/M) | 5 proxies re-derived from aggregate scores; M missing, reachable rank max **5.5** | `canslim_pipeline.py:406-412` |
| 3 | Rank floor | applied at rank time | 4.0 is a deploy gate only; 13/15 stored rows on 2026-11-03 < 4.0, min 2.7 | `gate_rules.py:83` |
| 4 | Unauditable names | excluded, counted | zero written and persisted | `canslim_pipeline.py:460-476` |
| 5 | Bursa chart | computed | flat 3/5, free +1.2 rank | `canslim_pipeline.py:112` |
| 6 | 10Y level halt | replaced by shock rule | shock rule in `gate_rules`, but `gate_panel` still halts above 4.80 and the stricter leg rules | `gate_panel.py:45,128,329` |
| 7 | Weekly regime dock | none | ±1.0 BULLISH / −1.5 BEARISH on every weekly pick | `weekly_pipeline.py:344-345` |
| 8 | Earnings gate | none | no new entry within 3 sessions of earnings, fail-open | `earnings_filter.py:70,137` |

Two more: the freshness test that blocks a *deployment* is 30 hours on
`canslim_results.fetched_at`; the 3-day test applies to the scan itself. And the
weekly scoring bonuses lift the achieved factor maximums above the clip values
(C 2.0, A 2.5, N 2.0, L 2.5, I 2.3, M 3.3), so "capped 0–2" is only true of the
base term.

---

## What this screener does not claim

- It does not predict returns. It orders candidates.
- The I factor is analyst sentiment, not institutional ownership.
- The N factor is price proximity, not news.
- The M factor is per-stock volume, not market direction.
- Bursa chart scores are a placeholder, not a measurement.
- It has no backtest. The criteria are O'Neil's and the calibrations are mine;
  the evidence is a live track record, not a study.
- A passing score is a reason to look at a chart, not a reason to buy.
