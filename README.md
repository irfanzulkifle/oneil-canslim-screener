# O'Neil CAN SLIM Screener

A five-stage equity screen that turns a market-wide universe into a short,
ranked lineup of breakout candidates. Built for US and Bursa Malaysia listings.

The question this repository answers is narrow and specific: **what exactly
must a stock do to appear in this screen, and what must it do to survive to the
end?** Every threshold below is a named constant in [`oneil/rules.py`](oneil/rules.py),
not prose that drifted away from the code.

```
universe  →  weekly trend gate  →  C/A/N/L/I/M  →  chart audit  →  rank  →  deploy gate
```

One thing to be clear about before the tables. This repository is a **clean
re-implementation** of a screen I run daily in a private system (TITAN). The
rules are the ones that system applies, the numbers are from its 2026-11-03
scan, and where the deployed code has drifted from this specification, the
drift is listed in [Production vs this repository](#production-vs-this-repository)
rather than smoothed over. A screen you cannot audit is a rumour.

---

## What "passing" means, stage by stage

| Stage | The question it answers | Rule | 2026-11-03 |
|---|---|---|---|
| 1. Universe | Is this tradeable at all? | `type = stock`, market cap ≥ **$500M**, top 500 by volume | 5,149 US tickers with a known cap; 2,805 clear $500M |
| 2. Weekly gate | Is it in an uptrend right now? | close > 10-week SMA **and** > 30-week SMA, weekly RSI(7) > 60, cap ≥ $1B | 113 US, 28 Malaysia (after the 3/5 weekly score) |
| 3. CAN SLIM | Is the business growing and near a high? | pass ≥ 3 of C/A/N/L/I/M | 175 names pass ≥4/6 in the daily batch |
| 4. Chart audit | Is the chart set up today? | 5 checks, 1 point each | capped at 15 per run (rate-limit budget) |
| 5. Rank | Which first? | `screen × 0.6 + chart × 0.4 + sector tilt` ≥ 4.0 | 15 stored, top 4.7 |

The "capped 0–2" in that table is the *base* formula. Bonuses lift the real
per-factor ceilings to A 2.5, L 2.5, I 2.3 and M 3.3, so the total can reach
14.6 — and none of it feeds the rank. `pipeline.screen()` calls
`score.final_rank(factors.passes, ...)`, an integer 0–6. The total is a
diagnostic; the pass count is the decision.

Two different senses of "pass" are deliberately kept apart. **Being seen** is the
weekly gate: trend and momentum, no fundamentals. **Passing** is the scored
screen: at least three of six CAN SLIM factors, then a chart score. A stock can
be seen and still rejected, which is the normal case.

---

## The funnel on a real scan

Numbers from the 2026-11-03 run of the production system.

```
US universe table                                          7,612 rows
  of which with a known market cap                          5,149
  of which above the $500M floor                            2,805
  → batched scan: stocks only, cap ≥ $500M, top 500 by vol
  → CAN SLIM pass ≥ 4/6                                       175
      pass 4: 93 · pass 5: 67 · pass 6: 15
  → weekly trend gate, then weekly score ≥ 3/5                113   (Malaysia: 28)
      of those, scoring 3/5: 97 · 4/5: 16
  → fundamentals ≥ 3/6, then chart audit (capped at 15)
  → ranked and stored                                          15
      top: EXEL 4.7, CNQ 4.7 · bottom: 2.7
      13 of the 15 are below the 4.0 deploy floor
```

Two honest notes on those numbers. **113 is not the raw trend-gate count.** The
weekly query returns names that clear the SMA and RSI tests, but the table only
stores the ones that then score 3+ on the five weekly factors, and the raw
intermediate count was never written down. And **15 stored is not 15 tradeable**:
storage and deployment use different bars, which is the subject of the
production-delta table below.

---

## Stage 2 — the weekly gate (what gets you seen)

| Condition | Value | Why |
|---|---|---|
| Close > 10-week SMA | strict | Short-term trend must be up |
| Close > 30-week SMA | strict | ...and the intermediate trend with it |
| Weekly RSI(7) | > 60 | Momentum on weekly bars, so one noisy day cannot flip it |
| Market cap | ≥ $1,000,000,000 | Higher than the daily floor: this list feeds trade candidates |
| Instrument | `stock` | ETFs and funds pass trend filters for reasons that say nothing about a company |

Then the weekly score, over five factors (C, A, N, L, M) with three needed:

```
W_total = C_score + A_score + clip(pct_above_10w, 0, 30)/10 + M_score + RSI7/50
```

| Weekly factor | Pass rule |
|---|---|
| C | quarterly EPS YoY > 25% |
| A | annual EPS YoY > 25% |
| N | within **10%** of the 52-week high |
| L | above both weekly SMAs and weekly RSI(7) between 55 and 85 |
| M | weekly relative volume > 1.0 |

Note the N difference: 10% weekly, 15% daily. They are different questions, and
a shared constant would silently change one of them. `W_total` is a sorting score,
not a 0–5 count; by construction it reaches about 22.

A weekly RSI above 90 still passes the gate. That is intentional: the gate asks
"is it going up", and exhaustion is handled by the L band and by the chart
audit, which is where an extended stock should fail.

---

## Stage 3 — CAN SLIM fundamentals

Six factors, each a pass flag plus a score. Pass ≥ 3 of 6 here, ≥ 4 of 6 in the
stricter daily batch.

| Factor | Rule | Score | Bonus |
|---|---|---|---|
| **C** current quarterly EPS | YoY growth **> 25%** | `clip(g, -100, 500) / 50`, base capped 0–2 | — |
| **A** annual EPS | YoY growth **> 25%** | `clip(g, -100, 200) / 50`, base capped 0–2 | +0.5 if 5Y CAGR > 25% |
| **N** new high | within **15%** of the 52-week high | `(100 + pct_from_high) / 20`, base capped 0–2 | — |
| **L** leader | close **> SMA200** | `pct_above_sma200 / 20 + 1`, base capped 0–2 | +0.3 if > SMA50, +0.2 if RSI 50–80 |
| **I** institutional | analyst mark **> 0.1** on −1…+1 | `(mark + 1) / 2 × 2`, base capped 0–2 | +0.3 if >50% buy ratings |
| **M** market/volume | 10-day relative volume **> 1.0** | `clip(rel_vol, 0, 3)` | +0.3 if up day and rel_vol > 1.2 |

The bonuses are added after the base clip, so the achieved maximums are C 2.0,
A 2.5, N 2.0, L 2.5, I 2.3, M 3.3. The table says "base capped" for that reason;
calling them hard caps would be false about a number in a table.

Missing data fails the factor; it never passes one. See
[`docs/SCREENING-RULES.md`](docs/SCREENING-RULES.md) for why I is the weakest
factor in the model and why it earns no veto.

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

There is a second volume dry-up rule on weekly bars, used by the base detector:
last completed week's volume below 60% of the 10-week average, with the
in-progress week's stub bar dropped before the ratio is taken. Two timeframes,
two rules, one name. Conflating them is how a "dry-up" flag ends up firing on a
Tuesday half-week.

**Unknown is not zero.** Too few bars returns `None`; this pipeline counts the
name as unaudited and leaves it out of the ranked list. Scoring a data gap as a
bad chart is how a pipeline quietly starts rejecting good stocks. (The deployed
system does not yet do this. See below.)

---

## Stage 5 — rank, then the market gate

```
final_rank = screener_score × 0.60 + chart_score × 0.40 + sector tilt
sector tilt:   rank 1–3 +0.5 · 4–6 +0.2 · 7–10 0 · 11+ −0.3
ceiling = 6 × 0.6 + 5 × 0.4 + 0.5 = 6.1
```

Ranking a stock is not permission to buy it. The deploy gate is separate and
market-level: VIX strictly below 20, and the US 10-year yield not up 25bp or
more over ten sessions. A high but stable yield only halves position size; it is
a rate shock, not a level, that flushes growth names. In 2026 a level-based
version of this rule blocked every trade for 76 consecutive sessions while the
market was making higher highs.

The 6.1 ceiling is asserted in the tests, and so is the reachability check. A
threshold above the arithmetic maximum is not a strict filter, it is an outage:
the screen returns nothing for months and every downstream report looks calm. The
production system ran a `final_rank ≥ 7.0` gate against a formula whose ceiling
is 6.1 and produced 68 consecutive HOLD decisions before anyone traced why.

---

## Production vs this repository

The deployed TITAN system and this specification disagree in eight places. They
are listed here because the alternative, publishing a document that describes a
system nobody runs, is worse than publishing a system with known defects.

| # | Area | Here | In production | Evidence |
|---|---|---|---|---|
| 1 | Universe floor | $500M | wrapper passes 500M; library default 300M | `tv-scan:12`, `canslim_tv.py:57` |
| 2 | Screener score | 6 factors (C/A/N/L/I/M) | pipeline re-derives 5 proxies from aggregate scores; M absent, so its reachable rank max is **5.5**, not 6.1 | `canslim_pipeline.py:406-412` |
| 3 | Rank floor | applied in the pipeline | 4.0 exists only as a *deploy* gate, after storage; 13 of 15 stored rows on 2026-11-03 were below it | `gate_rules.py:83`, `vix_gate_status.py:181` |
| 4 | Unauditable names | excluded as unaudited | fallback writes `chart_score: 0` and persists it | `canslim_pipeline.py:460-476` |
| 5 | Bursa chart score | computed like any other market | flat 3/5 for every `.KL` name, a free +1.2 of rank | `canslim_pipeline.py:112` |
| 6 | 10Y level halt | removed in favour of the shock rule | `gate_rules` is shock-based, but `gate_panel` still halts above 4.80 and the stricter rule governs | `gate_panel.py:45,128,329` |
| 7 | Weekly regime dock | not applied | ±1.0 BULLISH / −1.5 BEARISH added to every weekly pick, on a different scale from the 6.1 rank | `weekly_pipeline.py:344-345` |
| 8 | Earnings gate | not implemented | no new entry within 3 sessions of an earnings date, failing **open** when the date is unknown | `earnings_filter.py:70,137` |

Two more deployment facts the spec alone would not tell you: the freshness test
that actually blocks a trade is 30 **hours** on `canslim_results.fetched_at`
(the 3-day test is about the scan), and the weekly `W_total` is not a 0–5 score
despite a comment in `gate_rules.py` saying so.

None of this changes the rule arithmetic, which was checked line by line against
the source. It changes what you are entitled to claim about the output, which is
the part that matters.

---

## What the production system this came from refuses to do

These rules live in the operational system, not in this library — this
repository is the rule core and holds no data layer, so nothing here can check a
scan's age. Stated so a reader does not look for the code:

- **Stale scans are refused, not used.** A scan older than 3 days returns
  nothing; a deployment older than 30 hours is refused separately.
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
- **Bursa chart scores are a placeholder.** Do not read them as measurements.
- **There is no backtest in this repository.** The rules are O'Neil's published
  criteria and my calibrations; the only performance evidence is a live track
  record, which is a single short unblinded sample in any case.

---

## Running it

```bash
pip install -r requirements.txt
python3 run_demo.py            # five synthetic candidates, no network
python3 -m pytest -q           # 53 tests, all offline
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
tests/               53 tests; every threshold asserted on both sides
```

The modules are pure: they take dicts, they touch no database and no network.
Data acquisition is deliberately outside, so the rules can be tested without a
live feed and a vendor change cannot silently alter a threshold.

---

## Licence

MIT — see [`LICENSE`](LICENSE).
