"""The funnel: universe -> weekly gate -> fundamentals -> chart -> rank.

The order is not arbitrary. Trend first, because a cheap stock in a downtrend
is cheap for a reason. Fundamentals second, because they are the slowest and
most expensive data to refresh. Chart last, because it is the check that
changes most often and therefore the one that must run on the freshest bars.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable

from . import chart, rules, score, weekly


@dataclass
class Funnel:
    universe: int = 0
    weekly_gate: int = 0
    fundamentals: int = 0
    chart_audited: int = 0
    unaudited: int = 0
    above_min_rank: int = 0

    def pct(self, stage: str) -> str:
        base = self.universe or 1
        return f"{getattr(self, stage) / base * 100:.1f}%"


@dataclass
class Result:
    ticker: str
    sector: str
    sector_rank: int | None
    weekly_passes: int
    weekly_total: float
    screener_score: int
    chart_score: int
    final_rank: float
    factors: dict = field(default_factory=dict)
    audit: dict = field(default_factory=dict)
    weekly: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def screen(
    candidates: Iterable[dict],
    min_screener: int = rules.MIN_SCREENER_PASSES,
    min_rank: float | None = None,
    allow_unaudited: bool = False,
) -> tuple[list[Result], Funnel]:
    """Run one screening pass.

    A candidate whose bars are too short to audit is counted as unaudited and
    left out of the ranked list. It is not scored as a zero: a data gap and a
    bad chart are different findings, and only one of them is evidence about
    the stock. Set allow_unaudited=True to rank it with a zero instead, and say
    so wherever the output is published.

    candidate = {
      "ticker", "sector", "sector_rank",
      "weekly": {close, sma10w, sma30w, rsi7w, high_52w, rel_vol_w, eps_q_yoy, ...},
      "fundamentals": {eps_q_yoy, eps_a_yoy, close, high_52w, sma200, ...},
      "bars": {"close", "high", "low", "volume"},
      "benchmark": same shape as bars, or omitted to use a shared benchmark,
    }
    """
    funnel = Funnel()
    results: list[Result] = []
    min_rank = rules.FINAL_RANK_MIN if min_rank is None else min_rank

    candidates = list(candidates)
    funnel.universe = len(candidates)

    for c in candidates:
        wrow = c.get("weekly") or {}
        if not weekly.gate(wrow):
            continue
        funnel.weekly_gate += 1

        wscore = weekly.score(wrow)

        fundamentals = dict(c.get("fundamentals") or {})
        bars = c.get("bars") or {}
        if bars.get("close"):
            fundamentals.setdefault("close", bars["close"][-1])
        if wrow.get("high_52w") is not None:
            fundamentals.setdefault("high_52w", wrow["high_52w"])

        factors = score.canslim_factors(fundamentals)
        if factors.passes < min_screener:
            continue
        funnel.fundamentals += 1

        benchmark = c.get("benchmark") or {}
        audit = chart.audit(bars, benchmark)
        if audit is None:
            funnel.unaudited += 1
            if not allow_unaudited:
                continue
            chart_score = 0
        else:
            funnel.chart_audited += 1
            chart_score = audit.score

        rank = score.final_rank(factors.passes, chart_score, c.get("sector_rank"))
        if rank < min_rank:
            continue
        funnel.above_min_rank += 1

        results.append(Result(
            ticker=c.get("ticker", "?"),
            sector=c.get("sector", "?"),
            sector_rank=c.get("sector_rank"),
            weekly_passes=wscore.w_passes,
            weekly_total=wscore.w_total,
            screener_score=factors.passes,
            chart_score=chart_score,
            final_rank=rank,
            factors=factors.as_dict(),
            audit=audit.as_dict() if audit else {},
            weekly=wscore.as_dict(),
        ))

    results.sort(key=lambda r: r.final_rank, reverse=True)
    return results, funnel


def funnel_report(funnel: Funnel) -> str:
    """Human-readable funnel, the same shape the daily scan prints."""
    width = max(len(s) for s in
                ("universe", "weekly gate", "fundamentals", "chart audited",
                 "unaudited (excluded)", "above min rank")) + 2
    rows = [
        ("universe", funnel.universe, "100.0%"),
        ("weekly gate", funnel.weekly_gate, funnel.pct("weekly_gate")),
        ("fundamentals", funnel.fundamentals, funnel.pct("fundamentals")),
        ("chart audited", funnel.chart_audited, funnel.pct("chart_audited")),
        ("unaudited (excluded)", funnel.unaudited, funnel.pct("unaudited")),
        ("above min rank", funnel.above_min_rank, funnel.pct("above_min_rank")),
    ]
    lines = [f"  {'stage':<{width}}{'count':>8}{'of universe':>14}"]
    lines.append("  " + "-" * (width + 22))
    for name, count, pct in rows:
        lines.append(f"  {name:<{width}}{count:>8}{pct:>14}")
    return "\n".join(lines)
