# O'Neil CAN SLIM Screener

A five-stage equity screen that turns a market-wide universe into a short,
ranked lineup of breakout candidates. Built for US and Bursa Malaysia listings,
and run daily against live data in the system I use for my own scans.

The question this repository answers is narrow and specific: **what exactly
must a stock do to appear in this screen, and what must it do to survive to the
end?** Every threshold below is a named constant in [`oneil/rules.py`](oneil/rules.py),
not prose that drifted away from the code.

```
universe  →  weekly trend gate  →  C/A/N/L/I/M  →  chart audit  →  rank  →  deploy gate
 ~7,600          ~1.5%              ≥3 of 6         0–5 checks     0–6.1     market-level
```

---

## What "passing" means, stage by stage

| Stage | The question it answers | Rule | Survivors on 2026-11-03 |
|---|---|---|---|
| 1. Universe | Is this tradeable at all? | `type = stock`, market cap ≥ $300M, top 500 by volume | 7,612 US tickers in the universe table |
| 2. Weekly gate | Is it in an uptrend right now? | close > 10-week SMA **and** > 30-week SMA, weekly RSI(7) > 60, cap ≥ $1B | **113 US, 28 Malaysia** |
| 3. CAN SLIM | Is the business growing and near a high? | pass ≥ 3 of C/A/N/L/I/M | 175 names pass ≥4/6 in the daily batch |
| 4. Chart audit | Is the chart set up today? | 5 checks, 1 point each | capped at 15 per run (rate-limit budget) |
| 5. Rank | Which first? | `screen × 0.6 + chart × 0.4 + sector tilt` ≥ 4.0 | 15 ranked, top 4.7 |

Two different senses of "pass" are deliberately kept apart. **Being seen** is the
weekly gate: trend and momentum, no fundamentals. **Passing** is the scored
screen: at least three of six CAN SLIM factors, then a chart score. A stock can
be seen and still be rejected, which is the normal case.

---

## The funnel on a real scan

Numbers below are from the 2026-11-03 run of the production system.

```
US universe (mcap > 0)                                    7,612
  → batched scan: stocks only, mcap ≥ $300M, top 500 by volume
  → CAN SLIM pass ≥ 4/6                                     175
      pass 4: 93 · pass 5: 67 · pass 6: 15
  → weekly O'Neil gate                                       113   (Malaysia: 28)
      weekly passes 3/5: 97 · 4/5: 16
  → fundamentals pass ≥ 3/6, then chart audit (cap 15)
  → ranked, stored                                           15
      top: EXEL 4.7, CNQ 4.7 · floor: 4.0 of a 6.1 ceiling
```

The weekly list is the strict one: 113 US names out of roughly 7,600 is about
1.5%. That is the whole point of putting the trend gate first. A CAN SLIM
fundamental score alone hands you a hundred names and no opinion; the weekly
gate removes the ones that are simply not going up.

---

## Stage 2 — the weekly gate (what gets you seen)

Applied in one batched vendor query, before any scoring:

| Condition | Value | Why |
|---|---|---|
| Close > 10-week SMA | strict | Short-term trend must be up |
| Close > 30-week SMA | strict | ...and the intermediate trend with it |
| Weekly RSI(7) | > 60 | Momentum, measured on weekly bars so one noisy day cannot flip it |
| Market cap | ≥ $1,000,000,000 | Higher than the daily floor: this list feeds trade candidates |
| Instrument | `stock` | ETFs and funds pass trend filters for reasons that say nothing about a company |

A weekly RSI above 90 still passes this gate. That is intentional: the gate asks
"is it going up", and exhaustion is handled later by the L factor's 55–85 band
and by the chart audit, which is where an extended stock should fail.

---

## Stage 3 — CAN SLIM fundamentals

Six factors, each a pass flag plus a 0–2 score. Pass ≥ 3 of 6 in this pipeline,
≥ 4 of 6 in the stricter daily batch.

| Factor | Rule | Score | Bonus |
|---|---|---|---|
| **C** current quarterly EPS | YoY growth **> 25%** | `clip(g, -100, 500) / 50`, capped 0–2 | — |
| **A** annual EPS | YoY growth **> 25%** | `clip(g, -100, 200) / 50`, capped 0–2 | +0.5 if 5Y CAGR > 25% |
| **N** new high | within **15%** of the 52-week high | `(100 + pct_from_high) / 20`, capped 0–2 | — |
| **L** leader | close **> SMA200** | `pct_above_sma200 / 20 + 1`, capped 0–2 | +0.3 if > SMA50, +0.2 if RSI 50–80 |
| **I** institutional | analyst mark **> 0.1** on −1…+1 | `(mark + 1) / 2 × 2` | +0.3 if >50% buy ratings |
| **M** market/volume | 10-day relative volume **> 1.0** | `clip(rel_vol, 0, 3)` | +0.3 if up day and rel_vol > 1.2 |

Missing data fails the factor; it never passes one. See
[`docs/SCREENING-RULES.md`](docs/SCREENING-RULES.md) for the full rationale,
including why I is the weakest factor in the model and why it earns no veto.

---

## Stage 4 — the chart audit (what gets you ranked)

Five checks on daily bars, one point each. Runs only on survivors, because it
needs a year of bars per ticker and that is the expensive part of any free tier.

| # | Check | Threshold | What it is really asking |
|---|---|---|---|
| 1 | Moving averages stacked | SMA20 > SMA50 > SMA200 | Is the trend ordered across all horizons? |
| 2 | RS line at a 3-month high | current ratio ≥ 99% of the 63-day max | Is it beating the index *now*? |
| 3 | Volume dry-up | 3-day average < **60%** of the prior 50-day | Is supply shrinking while the base forms? |
| 4 | Volatility contraction | last 5-day range < **50%** of the prior 20-day | Is the base tightening toward a pivot? |
| 5 | 3-month excess return | stock − benchmark > 0 | Is there relative performance to trade? |

**Unknown is not zero.** Too few bars returns `None`, and the name is recorded
as unaudited rather than scored as a bad chart. A data gap scored as a zero is
how a pipeline quietly starts rejecting good stocks.

---

## Stage 5 — rank, then the market gate

```
final_rank = screener_score × 0.60 + chart_score × 0.40 + sector tilt
sector tilt:   rank 1–3 +0.5 · 4–6 +0.2 · 7–10 0 · 11+ −0.3
ceiling = 6 × 0.6 + 5 × 0.4 + 0.5 = 6.1
```

Ranking a stock is not permission to buy it. The deploy gate is separate and
market-level: VIX ≤ 20, and the US 10-year yield not up 25bp or more over ten
sessions. A high but stable yield only halves position size; it is a rate
shock, not a level, that flushes growth names. In 2026 a level-based version of
this rule (halt while the 10Y is above 4.80%) blocked every trade for 76
consecutive sessions while the market was fine.

The 6.1 ceiling is asserted in the tests. A gate set above its own arithmetic
maximum is not strict, it is an outage: nobody can satisfy it, and the screen
returns nothing for months before anyone notices.

---

## What it refuses to do

- **Stale scans are refused, not used.** A scan older than 3 days returns
  nothing. Screening yesterday's fundamentals against today's chart produces a
  lineup that was never testable.
- **A blank leg is not a pass.** Missing VIX or missing yield data means no
  verdict, not a green light.
- **No data is not a bad chart.** See above.
- **No sector table, no tilt.** Skipping is different from ranking everything
  last; collapsing the two would push every name into the penalty bucket.

---

## What it does not claim

- **It does not predict returns.** It orders candidates so a human reviews the
  best few first.
- **The I factor is analyst sentiment, not institutional ownership.** Real 13F
  accumulation is not available from a batch screen.
- **The N factor is price proximity, not news.** Nothing here knows about a new
  product or a management change.
- **The M factor is per-stock volume.** True market direction is a
  portfolio-level input.
- **Bursa chart scores are a placeholder.** Free daily OHLCV for `.KL` names is
  not reliably available, so Bursa names are ranked on fundamentals plus sector
  tilt. Do not read those chart scores as measurements.
- **There is no backtest in this repository.** The rules are O'Neil's published
  criteria and my calibrations; the only performance evidence I have is the
  live track record, which is not published here and would be a single, short,
  unblinded sample in any case.

---

## Running it

```bash
pip install -r requirements.txt
python3 run_demo.py            # five synthetic candidates, no network
python3 -m pytest -q           # 50 tests, all offline
```

The demo is generated by [`oneil/synthetic.py`](oneil/synthetic.py) with a fixed
seed. **There is no real market data in this repository.** The series exist to
exercise the rules, not to be read as prices.

To screen your own snapshot, pass plain JSON:

```bash
python3 -m oneil.cli --snapshot snapshot.json --min-rank 4.0
python3 -m oneil.cli --gate 4.18 4.21 4.34 --vix 17.4   # deploy gate only
```

```json
{
  "benchmark": {"close": [0.0], "high": [0.0], "low": [0.0], "volume": [0]},
  "candidates": [
    {
      "ticker": "EXAMPLE", "sector": "Software", "sector_rank": 4,
      "weekly": {"close": 44.2, "sma10w": 41.0, "sma30w": 37.5, "rsi7w": 64.1,
                 "high_52w": 45.0, "rel_vol_w": 1.3,
                 "eps_q_yoy": 41.0, "eps_a_yoy": 33.0, "market_cap": 12000000000},
      "fundamentals": {"eps_q_yoy": 41.0, "eps_a_yoy": 33.0, "eps_5y_cagr": 28.0,
                       "sma50": 42.0, "sma200": 35.0, "rsi": 61.0,
                       "rec_mark": 0.4, "pct_buy": 0.6,
                       "rel_vol": 1.3, "change": 1.1},
      "bars": {"close": [0.0], "high": [0.0], "low": [0.0], "volume": [0]}
    }
  ]
}
```

The arrays are abbreviated here; each needs 200+ daily bars for the chart audit
and 63+ for the relative-strength checks. The snapshot format is deliberately
plain, so a scan produced anywhere, by any language, can be re-scored without
re-fetching anything.

---

## Layout

```
oneil/rules.py       every threshold, one place, with the reason attached
oneil/weekly.py      the weekly gate and the 0–5 CAN SLIM score
oneil/chart.py       five chart checks as pure functions
oneil/score.py       C/A/N/L/I/M scoring, ranking, sector tilt, deploy gate
oneil/pipeline.py    the funnel, with counts at every stage
oneil/synthetic.py   deterministic bars for the demo and the tests
oneil/cli.py         command line entry point
docs/SCREENING-RULES.md   full rule tables, boundaries and rationale
tests/               50 tests; every threshold asserted on both sides
```

The modules are pure: they take dicts, they touch no database and no network.
Data acquisition is deliberately outside, so the rules can be tested without a
live feed and a vendor change cannot silently alter a threshold.

---

## Licence

MIT — see [`LICENSE`](LICENSE).
