"""
Ranking — turning two independent gates into one ordered lineup.

The screen answers "is the business growing?" and returns a 0–6 pass count.
The chart audit answers "is the chart set up?" and returns 0–5. They are not
the same unit, so they are blended as weighted points rather than summed.

    final_rank = screener_score * 0.60 + chart_score * 0.40

Fundamentals carry the larger weight because a good chart on a deteriorating
business is the more common way to lose money; the chart is the timing input,
not the thesis.

On top of that blend sits the M factor — O'Neil's market-direction rule applied
as a sector-rotation tilt. It reads the latest sector relative-strength ranking
and nudges names in leading sectors up, laggards down. When no sector table is
available the adjustment is skipped entirely rather than defaulted to zero,
because "no data" and "rank 0" are not the same claim.
"""

from __future__ import annotations

from typing import Iterable, Optional

FUNDAMENTAL_WEIGHT = 0.60
CHART_WEIGHT = 0.40

# Sector tilt, applied to final_rank as bonus/penalty points.
TOP_SECTOR_RANK = 3
TOP_SECTOR_BONUS = 0.5
NEAR_TOP_SECTOR_RANK = 6
NEAR_TOP_SECTOR_BONUS = 0.2
LAGGING_SECTOR_RANK = 10
LAGGING_SECTOR_PENALTY = -0.3

# TradingView/yfinance sector labels mapped onto our sector-RS taxonomy.
# First alias present in the ranking table wins.
SECTOR_ALIAS = {
    "technology services": ["Technology", "Tech"],
    "electronic technology": ["Semiconductors", "Technology", "Tech"],
    "health technology": ["Healthcare"],
    "health services": ["Healthcare"],
    "retail trade": ["Retail", "Consumer Cyclical"],
    "producer manufacturing": ["Industrials", "Industrial"],
    "finance": ["Financial Services", "Financial (Regional Banks)"],
    "energy minerals": ["Energy", "Oil & Gas"],
    "consumer non-durables": ["Consumer Defensive"],
    "consumer durables": ["Consumer Cyclical"],
    "consumer services": ["Consumer Cyclical"],
    "distribution services": ["Industrials", "Industrial"],
    "commercial services": ["Industrials", "Industrial"],
    "industrial services": ["Industrials", "Industrial"],
    "transportation": ["Transportation"],
    "process industries": ["Basic Materials"],
    "non-energy minerals": ["Basic Materials", "Metals & Mining"],
    "communications": ["Communication Services"],
    "utilities": ["Utilities"],
}

INDUSTRY_KEYWORDS = [
    ("semiconductor", ["Semiconductors", "Technology"]),
    ("biotech", ["Biotech", "Healthcare"]),
    ("software", ["Cloud", "Technology", "Tech"]),
    ("internet", ["Technology", "Tech"]),
    ("bank", ["Financial (Regional Banks)", "Financial Services"]),
    ("insurance", ["Financial Services"]),
    ("oil & gas", ["Oil & Gas E&P", "Oil & Gas", "Energy"]),
    ("aerospace", ["Aerospace & Defense", "Defense"]),
    ("homebuild", ["Homebuilders", "Consumer Cyclical"]),
    ("airline", ["Transportation"]),
    ("utility", ["Utilities"]),
]


def rank(candidates: Iterable[dict]) -> list[dict]:
    """Blend both scores and sort best-first.

    Each candidate needs `screener_score` and `chart_score`. Mutates and
    returns the same list, sorted.
    """
    out = list(candidates)
    for c in out:
        c["final_rank"] = c["screener_score"] * FUNDAMENTAL_WEIGHT + c["chart_score"] * CHART_WEIGHT
    out.sort(key=lambda c: c["final_rank"], reverse=True)
    return out


def resolve_sector(sector: Optional[str], industry: Optional[str],
                   sector_map: dict[str, tuple[int, float]]) -> Optional[str]:
    """Map a stock's sector label onto a key present in the ranking table."""
    if sector and sector in sector_map:
        return sector
    for cand in SECTOR_ALIAS.get((sector or "").strip().lower(), []):
        if cand in sector_map:
            return cand
    blob = f"{sector or ''} {industry or ''}".lower()
    for keyword, cands in INDUSTRY_KEYWORDS:
        if keyword in blob:
            for cand in cands:
                if cand in sector_map:
                    return cand
    return None


def apply_m_factor(candidates: list[dict],
                   sector_map: dict[str, tuple[int, float]]) -> list[dict]:
    """Tilt final_rank by sector relative strength, then re-sort.

    Args:
        candidates: dicts with `final_rank`, and `sector` / `industry`.
        sector_map: sector -> (rank, score). An empty map means "no data", and
            the whole adjustment is skipped.
    """
    if not sector_map:
        return candidates

    for c in candidates:
        matched = resolve_sector(c.get("sector"), c.get("industry"), sector_map)
        if not matched:
            c["sector_rs_rank"] = None
            c["sector_rs_score"] = None
            continue
        sector_rank, sector_score = sector_map[matched]
        c["sector_rs_rank"] = sector_rank
        c["sector_rs_score"] = sector_score
        if sector_rank <= TOP_SECTOR_RANK:
            c["final_rank"] += TOP_SECTOR_BONUS
        elif sector_rank <= NEAR_TOP_SECTOR_RANK:
            c["final_rank"] += NEAR_TOP_SECTOR_BONUS
        elif sector_rank > LAGGING_SECTOR_RANK:
            c["final_rank"] += LAGGING_SECTOR_PENALTY

    candidates.sort(key=lambda c: c["final_rank"], reverse=True)
    return candidates
