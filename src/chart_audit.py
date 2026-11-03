"""
Chart audit — the second gate, applied only to screener survivors.

Fundamentals tell you the business is growing. The chart tells you whether the
market agrees *right now*. Five checks, one point each, 0–5.

Why this is a separate gate rather than more columns in the screen:

The fundamental screen runs on thousands of tickers from one batched API call.
The chart audit needs a year of daily OHLCV per name, which is the expensive
part of any free data tier. So the expensive gate runs only on names that
already cleared the cheap one, and on a wall-clock budget.

A ticker that cannot be audited is not silently scored 0 — `audit()` returns
None, and the caller records the name as unaudited. Scoring a data gap as a bad
chart is how a pipeline quietly starts rejecting good stocks.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

# Thresholds, each tied to a named check below.
VDU_RATIO_MAX = 0.60        # 3-day volume vs 50-day baseline
VCP_CONTRACTION_MAX = 0.50  # recent 5-day range vs prior 20-day range
RS_NEW_HIGH_TOLERANCE = 0.99  # within 1% of the 3-month RS high
MIN_BARS = 200              # need a full 200-day average


def audit(ohlcv: pd.DataFrame, benchmark: pd.DataFrame) -> Optional[dict]:
    """Score one ticker's chart against a benchmark index.

    Args:
        ohlcv: daily bars for the stock, columns Close/High/Low/Volume,
               oldest first, at least MIN_BARS rows.
        benchmark: daily bars for the index (e.g. SPY), same shape.

    Returns:
        {"score": int 0-5, "checks": {...}, "metrics": {...}}
        or None when there is not enough data to judge. None means "unknown",
        never "bad".
    """
    if ohlcv is None or benchmark is None:
        return None
    if len(ohlcv) < MIN_BARS or len(benchmark) < 63:
        return None

    closes = _floats(ohlcv["Close"])
    if closes is None:
        return None
    bench = _floats(benchmark["Close"])
    if bench is None:
        return None

    score = 0
    checks: dict[str, bool] = {}
    metrics: dict[str, float | bool] = {}

    # 1. Moving averages stacked in order: 20 > 50 > 200.
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50
    sma200 = sum(closes[-200:]) / 200
    checks["sma_aligned"] = sma20 > sma50 > sma200
    score += checks["sma_aligned"]
    metrics.update(sma20=sma20, sma50=sma50, sma200=sma200)

    # 2. Relative-strength line at a 3-month high — the stock is beating the
    # index now, not merely rising with it.
    n = min(len(closes), len(bench))
    if n >= 63:
        rs = [closes[-n:][i] / bench[-n:][i] for i in range(n)]
        recent = rs[-63:]
        checks["rs_line_new_high"] = recent[-1] >= max(recent) * RS_NEW_HIGH_TOLERANCE
        score += checks["rs_line_new_high"]
        metrics.update(rs_line_current=recent[-1], rs_line_3m_max=max(recent))

    # 3. Volume dry-up — the base is being built on shrinking supply, which is
    # what makes a later breakout on volume meaningful.
    vols = _floats(ohlcv["Volume"]) if "Volume" in ohlcv.columns else None
    if vols and len(vols) >= 53:
        recent_3 = sum(vols[-3:]) / 3
        baseline_50 = sum(vols[-53:-3]) / 50
        if baseline_50 > 0:
            ratio = recent_3 / baseline_50
            checks["vdu"] = ratio < VDU_RATIO_MAX
            score += checks["vdu"]
            metrics.update(vdu_ratio=ratio)

    # 4. Volatility contraction (VCP) — the last 5 days are tighter than the
    # preceding 20. A properly tightening base precedes the pivot.
    if "High" in ohlcv.columns and "Low" in ohlcv.columns and len(ohlcv) >= 25:
        highs = _floats(ohlcv["High"])
        lows = _floats(ohlcv["Low"])
        if highs and lows and closes[-1] > 0:
            recent_range = (max(highs[-5:]) - min(lows[-5:])) / closes[-1]
            prior_close = closes[-6]
            if prior_close > 0:
                prior_range = (max(highs[-25:-5]) - min(lows[-25:-5])) / prior_close
                if prior_range > 0:
                    checks["vcp"] = (recent_range / prior_range) < VCP_CONTRACTION_MAX
                    score += checks["vcp"]
                    metrics.update(
                        recent_range_pct=recent_range * 100,
                        prior_range_pct=prior_range * 100,
                    )

    # 5. Three-month excess return over the benchmark is positive.
    if len(closes) >= 63 and len(bench) >= 63:
        rs_3m = (closes[-1] / closes[-63] - 1) - (bench[-1] / bench[-63] - 1)
        checks["rs_3m_positive"] = rs_3m > 0
        score += checks["rs_3m_positive"]
        metrics["rs_3m_pct"] = rs_3m * 100

    return {"score": int(score), "checks": checks, "metrics": metrics}


def _floats(series) -> Optional[list[float]]:
    """Coerce a pandas column or array to a plain list of floats."""
    if series is None:
        return None
    try:
        if hasattr(series, "values"):
            series = series.values
        if hasattr(series, "flatten"):
            series = series.flatten()
        return [float(x) for x in series]
    except (TypeError, ValueError):
        return None
