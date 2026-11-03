"""Stage 4: the chart audit.

Five checks, one point each, computed from daily bars. The point of splitting
this from the fundamental screen is that a stock can be fundamentally perfect
and still be the wrong purchase today: extended, on no volume, or rolling over.

Each check is a pure function so it can be tested against a hand-built series
instead of against a live vendor feed.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Sequence

from . import rules


def _f(seq: Sequence[float]) -> list[float]:
    return [float(x) for x in seq]


def sma(values: Sequence[float], window: int) -> float | None:
    v = _f(values)
    if len(v) < window:
        return None
    return sum(v[-window:]) / window


def sma_alignment(closes: Sequence[float]) -> bool | None:
    """20 > 50 > 200. None when there is not enough history to judge."""
    fast, mid, slow = rules.SMA_WINDOWS
    c = _f(closes)
    if len(c) < slow:
        return None
    s20, s50, s200 = sma(c, fast), sma(c, mid), sma(c, slow)
    assert s20 is not None and s50 is not None and s200 is not None
    return s20 > s50 > s200


def vdu(volumes: Sequence[float]) -> tuple[bool | None, float | None]:
    """Volume dry-up: last 3 sessions under 60% of the prior 50-day average.

    Dry-up is the quiet before a breakout. It matters most when price is
    holding near a high on shrinking supply, so this is scored, not gated.
    """
    v = _f(volumes)
    need = rules.VDU_RECENT_DAYS + rules.VDU_BASELINE_DAYS
    if len(v) < need:
        return None, None
    recent = sum(v[-rules.VDU_RECENT_DAYS:]) / rules.VDU_RECENT_DAYS
    baseline = sum(v[-(need):-rules.VDU_RECENT_DAYS]) / rules.VDU_BASELINE_DAYS
    if baseline <= 0:
        return None, None
    ratio = recent / baseline
    return ratio < rules.VDU_MAX_RATIO, ratio


def vcp(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> tuple[bool | None, float | None, float | None]:
    """Volatility contraction: the last 5 sessions' range vs the prior 20.

    Returns (contracted, recent_range_pct, prior_range_pct). Ranges are
    expressed as a percentage of price so they are comparable across names.
    """
    h, l, c = _f(highs), _f(lows), _f(closes)
    need = rules.VCP_RECENT_DAYS + rules.VCP_PRIOR_DAYS
    if len(h) < need or len(l) < need or len(c) < need:
        return None, None, None
    last_close = c[-1]
    if last_close <= 0:
        return None, None, None

    recent_high = max(h[-rules.VCP_RECENT_DAYS:])
    recent_low = min(l[-rules.VCP_RECENT_DAYS:])
    recent_range = (recent_high - recent_low) / last_close

    window = need
    prior_high = max(h[-window:-rules.VCP_RECENT_DAYS])
    prior_low = min(l[-window:-rules.VCP_RECENT_DAYS])
    prior_close = c[-(rules.VCP_RECENT_DAYS + 1)]
    if prior_close <= 0:
        return None, None, None
    prior_range = (prior_high - prior_low) / prior_close

    if prior_range <= 0:
        return None, recent_range * 100, prior_range * 100
    return (
        recent_range / prior_range < rules.VCP_MAX_CONTRACTION,
        recent_range * 100,
        prior_range * 100,
    )


def rs_line_new_high(closes: Sequence[float], bench_closes: Sequence[float]) -> tuple[bool | None, float | None]:
    """Relative-strength line (stock / benchmark) at a 3-month high.

    A new high on the RS line while price is still below its own high is the
    classic tell that the stock is being accumulated faster than the market.
    """
    c, b = _f(closes), _f(bench_closes)
    n = min(len(c), len(b))
    window = rules.RS_LINE_LOOKBACK
    if n < window:
        return None, None
    rs = [c[-n + i] / b[-n + i] for i in range(n) if b[-n + i] > 0]
    if len(rs) < window:
        return None, None
    recent = rs[-window:]
    return recent[-1] >= max(recent) * rules.RS_LINE_TOLERANCE, recent[-1]


def rs_3m(closes: Sequence[float], bench_closes: Sequence[float]) -> float | None:
    """Three-month excess return in percentage points, stock minus benchmark."""
    c, b = _f(closes), _f(bench_closes)
    window = rules.RS_3M_DAYS
    if len(c) < window or len(b) < window:
        return None
    stock = (c[-1] / c[-window]) - 1
    bench = (b[-1] / b[-window]) - 1
    return (stock - bench) * 100


@dataclass(frozen=True)
class ChartAudit:
    score: int
    sma_aligned: bool | None
    rs_line_new_high: bool | None
    vdu: bool | None
    vcp: bool | None
    rs_3m_pct: float | None
    vdu_ratio: float | None
    recent_range_pct: float | None
    prior_range_pct: float | None

    def as_dict(self) -> dict:
        return asdict(self)


def audit(bars: dict, benchmark: dict) -> ChartAudit | None:
    """Run all five checks on one stock. None when there is not enough history.

    bars / benchmark: {"close": [...], "high": [...], "low": [...], "volume": [...]}
    """
    closes = bars.get("close") or []
    if len(closes) < max(rules.SMA_WINDOWS):
        return None
    bench = benchmark.get("close") or []

    aligned = sma_alignment(closes)
    rs_high, _ = rs_line_new_high(closes, bench)
    dry, ratio = vdu(bars.get("volume") or [])
    contracted, recent_pct, prior_pct = vcp(
        bars.get("high") or [], bars.get("low") or [], closes
    )
    excess = rs_3m(closes, bench)

    score = sum(1 for x in (aligned, rs_high, dry, contracted) if x)
    score += 1 if (excess is not None and excess > 0) else 0

    return ChartAudit(
        score=score,
        sma_aligned=aligned,
        rs_line_new_high=rs_high,
        vdu=dry,
        vcp=contracted,
        rs_3m_pct=None if excess is None else round(excess, 2),
        vdu_ratio=None if ratio is None else round(ratio, 3),
        recent_range_pct=None if recent_pct is None else round(recent_pct, 2),
        prior_range_pct=None if prior_pct is None else round(prior_pct, 2),
    )
