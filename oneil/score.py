"""Stage 5: fundamental scoring, ranking, and the deploy gates.

Three things happen here, in this order, and they answer different questions:

  canslim_factors()  how many of C/A/N/L/I/M does the stock pass, and how
                     strongly (score 0-12)?
  final_rank()       of the survivors, which are worth looking at first
                     (0.6 x screen + 0.4 x chart + sector boost, max 6.1)?
  deploy_gate()      is today a day to buy anything at all (market regime)?

Mixing a stock-level score with a market-level gate is the mistake that
produces "top pick" lists in a market that should not be bought.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping, Sequence

from . import rules


def _n(src: Mapping, key: str, default: float | None = None) -> float | None:
    v = src.get(key, default)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Factors:
    c: bool
    a: bool
    n: bool
    l: bool
    i: bool
    m: bool
    total: float
    passes: int

    def as_dict(self) -> dict:
        return asdict(self)


def canslim_factors(f: Mapping) -> Factors:
    """C/A/N/L/I/M on one stock's fundamentals.

    Data needed: eps_q_yoy, eps_a_yoy, eps_5y_cagr, close, high_52w, sma200,
    sma50, rsi, rec_mark (-1..1 analyst mean), pct_buy, rel_vol, change.
    Missing values fail a check rather than passing it.
    """
    eps_q = _n(f, "eps_q_yoy")
    eps_a = _n(f, "eps_a_yoy")
    cagr5 = _n(f, "eps_5y_cagr")
    close = _n(f, "close")
    high52 = _n(f, "high_52w")
    sma200 = _n(f, "sma200")
    sma50 = _n(f, "sma50")
    rsi = _n(f, "rsi")
    rec = _n(f, "rec_mark")
    pct_buy = _n(f, "pct_buy")
    rel_vol = _n(f, "rel_vol")
    change = _n(f, "change")

    # C: current quarterly earnings growth. O'Neil's single most important
    # fundamental. 25% is the floor; the score scales to a 2.0 cap.
    c_pass = eps_q is not None and eps_q > rules.EPS_GROWTH_MIN_PCT
    c_score = 0.0
    if eps_q is not None:
        c_score = max(0.0, min(2.0, max(-100.0, min(500.0, eps_q)) / 50))

    # A: annual earnings growth, plus a bonus for a 5-year record.
    a_pass = eps_a is not None and eps_a > rules.EPS_GROWTH_MIN_PCT
    a_score = 0.0
    if eps_a is not None:
        a_score = max(0.0, min(2.0, max(-100.0, min(200.0, eps_a)) / 50))
    if cagr5 is not None and cagr5 > rules.EPS_GROWTH_MIN_PCT:
        a_score += 0.5
    a_score = min(a_score, 2.5)

    # N: new high. Within 15% of the 52-week high is the pass; the score is
    # continuous, so a name 3% off the high scores higher than one 12% off.
    pct_from_high = None
    if close is not None and high52:
        pct_from_high = (close - high52) / high52 * 100
    n_pass = pct_from_high is not None and pct_from_high >= rules.DAILY_NEAR_HIGH_MAX_DRAWDOWN
    n_score = 0.0
    if pct_from_high is not None:
        n_score = max(0.0, min(2.0, (100 + pct_from_high) / 20))

    # L: leader. Above the 200-day, with a bonus for the 50-day and for RSI
    # in the 50-80 band (trending but not exhausted).
    l_pass = close is not None and sma200 is not None and close > sma200
    l_score = 0.0
    if close is not None and sma200:
        pct_above = (close / sma200 - 1) * 100
        l_score = max(0.0, min(2.0, pct_above / 20 + 1))
        if sma50 is not None and close > sma50:
            l_score += 0.3
        if rsi is not None and 50 <= rsi <= 80:
            l_score += 0.2
    l_score = min(l_score, 2.5)

    # I: institutional sponsorship. Analyst recommendation is a proxy, not
    # ownership data, and it is labelled as such in the docs.
    i_pass = rec is not None and rec > rules.ANALYST_MARK_MIN
    i_score = 0.0
    if rec is not None:
        i_score = (max(-1.0, min(1.0, rec)) + 1) / 2 * 2
        if pct_buy is not None and pct_buy > rules.ANALYST_BUY_SHARE_BONUS:
            i_score += 0.3
    i_score = min(i_score, 2.3)

    # M: market/volume confirmation at the stock level.
    m_pass = rel_vol is not None and rel_vol > rules.REL_VOLUME_MIN
    m_score = 0.0
    if rel_vol is not None:
        m_score = max(0.0, min(3.0, rel_vol))
        if change is not None and change > 0 and rel_vol > rules.REL_VOLUME_SURGE_BONUS:
            m_score += 0.3

    total = c_score + a_score + n_score + l_score + i_score + m_score
    passes = sum([c_pass, a_pass, n_pass, l_pass, i_pass, m_pass])
    return Factors(
        c=c_pass, a=a_pass, n=n_pass, l=l_pass, i=i_pass, m=m_pass,
        total=round(total, 2), passes=passes,
    )


def sector_boost(rank: int | None) -> float:
    """O'Neil's M factor at the sector level: buy in the leading groups."""
    if rank is None:
        return 0.0
    if rank <= rules.M_TOP_SECTOR_RANKS:
        return rules.M_TOP_BOOST
    if rank <= rules.M_SECOND_TIER_RANKS:
        return rules.M_SECOND_BOOST
    if rank > rules.M_LAGGARD_RANK:
        return rules.M_LAGGARD_PENALTY
    return 0.0


def final_rank(screener_score: int, chart_score: int, sector_rank: int | None = None) -> float:
    """Weighted rank. Screener is 0-6, chart is 0-5, sector boost is -0.3..+0.5."""
    raw = screener_score * rules.W_SCREENER + chart_score * rules.W_CHART
    return round(raw + sector_boost(sector_rank), 3)


def rank_is_reachable(threshold: float = rules.FINAL_RANK_MIN) -> bool:
    """Guard against re-introducing an unsatisfiable bar."""
    return threshold <= rules.FINAL_RANK_CEILING


@dataclass(frozen=True)
class GateState:
    teny_level: float | None
    teny_change_bp: float | None
    vix: float | None
    tier: str
    sizing_multiplier: float
    can_deploy: bool
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def deploy_gate(teny_series: Sequence[float] | None, vix: float | None) -> GateState:
    """Market-level permission to deploy, independent of any single stock.

    teny_series: oldest -> newest 10Y closes, percent (e.g. 4.35).
    A rate shock halts; a high but stable level only halves size.
    """
    clean = [float(x) for x in (teny_series or []) if x is not None]
    level = clean[-1] if clean else None
    change_bp = None
    if len(clean) > rules.TENY_SHOCK_LOOKBACK:
        change_bp = round(
            (clean[-1] - clean[-1 - rules.TENY_SHOCK_LOOKBACK]) * 100, 1
        )

    if vix is None:
        return GateState(level, change_bp, None, "NO_DATA", 0.0, False,
                         "VIX unavailable: a blank leg is not a pass")

    if vix > rules.VIX_MAX:
        return GateState(level, change_bp, vix, "HALT", 0.0, False,
                         f"VIX {vix:.2f} above {rules.VIX_MAX:.0f}")

    if level is None:
        return GateState(level, change_bp, vix, "NO_DATA", 0.0, False,
                         "10Y series empty: no verdict")

    if rules.USE_ABSOLUTE_HALT and level > rules.TENY_LEGACY_HALT_LEVEL:
        return GateState(level, change_bp, vix, "HALT", 0.0, False,
                         f"10Y {level:.2f}% above legacy halt")

    if change_bp is not None and change_bp >= rules.TENY_SHOCK_BP:
        return GateState(level, change_bp, vix, "HALT", 0.0, False,
                         f"rate shock: +{change_bp:.0f}bp over "
                         f"{rules.TENY_SHOCK_LOOKBACK} sessions")

    if level > rules.TENY_HALF_SIZE_LEVEL:
        return GateState(level, change_bp, vix, "HALF", 0.5, True,
                         f"10Y {level:.2f}% above {rules.TENY_HALF_SIZE_LEVEL:.2f}% "
                         "but no shock: half size")

    return GateState(level, change_bp, vix, "FULL", 1.0, True,
                     f"10Y {level:.2f}%, no shock: full size")
