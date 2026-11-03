"""Stage 2 and 3: the weekly O'Neil gate and the weekly CAN SLIM score.

Two different questions, deliberately kept apart:

  gate()  - may this stock be looked at at all?  (price above 10W and 30W,
            weekly RSI(7) above 60)
  score() - once seen, how many of C/A/N/L/M does it actually pass?

A name that fails the gate never reaches the score, and a name that passes the
gate but scores 0 is still not a candidate. Conflating the two is how screens
end up ranking stocks that are below their own trend lines.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping

from . import rules


@dataclass(frozen=True)
class WeeklyScore:
    c_pass: bool
    a_pass: bool
    n_pass: bool
    l_pass: bool
    m_pass: bool
    c_score: float
    a_score: float
    m_score: float
    pct_above_10w: float
    pct_above_30w: float
    pct_from_52w_high: float | None
    w_total: float
    w_passes: int

    def as_dict(self) -> dict:
        return asdict(self)


def _num(row: Mapping[str, float], key: str, default: float = 0.0) -> float:
    value = row.get(key)
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def gate(row: Mapping[str, float]) -> bool:
    """The weekly where-clause: trend and momentum, before any fundamentals.

    row needs: close, sma10w, sma30w, rsi7w, market_cap
    """
    close = _num(row, "close")
    sma10w = _num(row, "sma10w")
    sma30w = _num(row, "sma30w")
    rsi = _num(row, "rsi7w")
    mcap = _num(row, "market_cap")

    # A missing market cap must fail, not skip the leg. `if mcap and ...` let a
    # 0.0 default through, so a row with no market cap at all cleared the $1B
    # floor and the gate returned True.
    if mcap <= 0 or mcap < rules.WEEKLY_MIN_MCAP:
        return False
    if not (sma10w > 0 and sma30w > 0):
        return False
    return close > sma10w and close > sma30w and rsi > rules.RSI7_WEEKLY_MIN


def score(row: Mapping[str, float]) -> WeeklyScore:
    """Weekly CAN SLIM score, 0-5 passes, continuous total.

    The total is not normalised to 0-1 and is not comparable across vendors.
    It exists to sort within one scan: C and A contribute up to 10 each, the
    trend term up to 3, volume up to 3 and RSI up to ~2.
    """
    close = _num(row, "close")
    sma10w = _num(row, "sma10w")
    sma30w = _num(row, "sma30w")
    rsi = _num(row, "rsi7w", 50.0)
    # No default to `close`: that made pct_from_52w exactly 0.0, which passes
    # N, so a stock with no 52-week-high data scored full marks. Missing data
    # must fail the factor - the promise the README makes.
    high52 = _num(row, "high_52w", 0.0)
    rel_vol = _num(row, "rel_vol_w", 0.0)

    eps_q = row.get("eps_q_yoy")
    eps_a = row.get("eps_a_yoy")
    eps_q_f = float(eps_q) if eps_q is not None else -999.0
    eps_a_f = float(eps_a) if eps_a is not None else -999.0

    pct_above_10w = (close / sma10w - 1) * 100 if sma10w > 0 else 0.0
    pct_above_30w = (close / sma30w - 1) * 100 if sma30w > 0 else 0.0
    pct_from_52w = (close - high52) / high52 * 100 if high52 > 0 else None

    low_band, high_band = rules.RSI7_WEEKLY_SCORE_BAND
    l_pass = (
        pct_above_10w > 0
        and pct_above_30w > 0
        and low_band <= rsi <= high_band
    )

    c_pass = eps_q_f > rules.EPS_GROWTH_MIN_PCT
    c_score = max(-100.0, min(500.0, eps_q_f if eps_q is not None else 0.0)) / 50

    a_pass = eps_a_f > rules.EPS_GROWTH_MIN_PCT
    a_score = max(-100.0, min(200.0, eps_a_f if eps_a is not None else 0.0)) / 50

    n_pass = pct_from_52w is not None and pct_from_52w >= rules.NEAR_HIGH_MAX_DRAWDOWN

    m_pass = rel_vol > rules.REL_VOLUME_MIN
    m_score = max(0.0, min(3.0, rel_vol))

    w_total = (
        c_score
        + a_score
        + max(0.0, min(30.0, pct_above_10w)) / 10
        + m_score
        + rsi / 50
    )

    passes = sum([c_pass, a_pass, n_pass, l_pass, m_pass])

    return WeeklyScore(
        c_pass=c_pass, a_pass=a_pass, n_pass=n_pass, l_pass=l_pass, m_pass=m_pass,
        c_score=round(c_score, 3), a_score=round(a_score, 3), m_score=round(m_score, 3),
        pct_above_10w=round(pct_above_10w, 2),
        pct_above_30w=round(pct_above_30w, 2),
        pct_from_52w_high=None if pct_from_52w is None else round(pct_from_52w, 2),
        w_total=round(w_total, 3),
        w_passes=passes,
    )
