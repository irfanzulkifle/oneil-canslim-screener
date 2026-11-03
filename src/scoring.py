"""
CAN SLIM fundamental scoring — the six factors, scored from one screen.

This is the first gate every candidate must clear. It takes a DataFrame of raw
TradingView screener columns and adds a pass flag and a 0–2 score per factor,
then a pass count and a total.

Design note — why "pass most factors" instead of "pass all":

A single-factor veto makes the screen brittle. A stock with 25% EPS growth that
happens to sit 16% off its high is not a bad business, it is a stock that has
not set up yet. The original CAN SLIM book expects a candidate to satisfy the
spirit of the model, not six binary switches, so the screen keeps anything that
clears a majority and lets the ranker sort quality afterwards.

Thresholds are deliberately explicit constants — see docs/SCREENING-RULES.md
for the rationale behind each number.
"""

from __future__ import annotations

import pandas as pd

# ── Thresholds ───────────────────────────────────────────────────────────────
C_EPS_GROWTH_MIN = 25.0      # % YoY quarterly diluted EPS growth
A_EPS_GROWTH_MIN = 25.0      # % YoY annual diluted EPS growth
A_CAGR_5Y_BONUS = 25.0       # % 5-year EPS CAGR that earns extra A credit
N_MAX_PCT_FROM_HIGH = -15.0  # % — within 15% of the 52-week high
I_RECOMMENDATION_MIN = 0.1   # analyst mark, -1.0 (sell) .. +1.0 (buy)
M_REL_VOLUME_MIN = 1.0       # relative volume vs 10-day average
M_VOLUME_SURGE = 1.2         # relative volume that counts as a surge

# A stock must clear at least this many of the six factors to stay in the screen.
MIN_FACTORS_PASSED = 4

FACTORS = ("C", "A", "N", "L", "I", "M")


def score_canslim(df: pd.DataFrame) -> pd.DataFrame:
    """Attach per-factor pass flags, per-factor scores, and the aggregate.

    Returns a new DataFrame; the input is not mutated.

    Columns added:
        C_pass, A_pass, N_pass, L_pass, I_pass, M_pass  (bool)
        C_score .. M_score                              (float, 0–2 plus bonuses)
        pct_from_52w_high, pct_above_sma200, RS_52w     (float, %)
        canslim_total                                   (float)
        canslim_passes                                  (int, 0–6)
    """
    df = df.copy()
    if df.empty:
        return df

    # C — Current quarterly earnings. The strongest single predictor O'Neil
    # used: a big jump in the latest reported quarter.
    df["C_pass"] = df["earnings_per_share_diluted_yoy_growth_fq"].fillna(-999) > C_EPS_GROWTH_MIN
    df["C_score"] = (
        df["earnings_per_share_diluted_yoy_growth_fq"].fillna(0).clip(-100, 500) / 50
    ).clip(0, 2)

    # A — Annual earnings. A company can print one good quarter by accident;
    # three years of growth is harder to fake.
    df["A_pass"] = df["earnings_per_share_diluted_yoy_growth_fy"].fillna(-999) > A_EPS_GROWTH_MIN
    df["A_score"] = (
        df["earnings_per_share_diluted_yoy_growth_fy"].fillna(0).clip(-100, 200) / 50
    ).clip(0, 2)
    df["A_cagr_5y"] = df["earnings_per_share_diluted_5y_growth_fy"]
    df.loc[df["A_cagr_5y"] > A_CAGR_5Y_BONUS, "A_score"] += 0.5

    # N — New. Proxied by proximity to the 52-week high: nothing to sell into
    # above, so a breakout has room. This is a proxy, not a news feed.
    df["pct_from_52w_high"] = (
        (df["close"] - df["price_52_week_high"]) / df["price_52_week_high"] * 100
    )
    df["N_pass"] = df["pct_from_52w_high"] >= N_MAX_PCT_FROM_HIGH
    df["N_score"] = ((100 + df["pct_from_52w_high"].fillna(-50)) / 20).clip(0, 2)

    # L — Leader, not laggard. Price above the 200-day average is the long-term
    # trend filter; the SMA50 and RSI terms are bonuses for trend quality.
    df["L_pass"] = df["close"] > df["SMA200"]
    df["pct_above_sma200"] = (df["close"] / df["SMA200"] - 1) * 100
    df["L_score"] = (df["pct_above_sma200"].fillna(-20) / 20 + 1).clip(0, 2)
    df.loc[df["close"] > df["SMA50"], "L_score"] += 0.3
    df.loc[df["RSI"].between(50, 80), "L_score"] += 0.2

    # I — Institutional sponsorship. Proxied by analyst recommendation because
    # TradingView exposes no usable 13F aggregate for a batch screen. Honest
    # label: this is a proxy, and a weak one, which is why it earns no veto.
    df["I_pass"] = df["recommendation_mark"].fillna(0) > I_RECOMMENDATION_MIN
    df["I_score"] = (df["recommendation_mark"].fillna(0) + 1) / 2 * 2
    if "recommendation_total" in df.columns:
        df["pct_buy"] = df["recommendation_buy"] / df["recommendation_total"].replace(0, 1)
        df.loc[df["pct_buy"] > 0.5, "I_score"] += 0.3

    # M — Market direction. Per-stock proxy only: above-average volume implies
    # accumulation. True market direction is a separate, portfolio-level input.
    df["M_pass"] = df["relative_volume_10d_calc"].fillna(0) > M_REL_VOLUME_MIN
    df["M_score"] = df["relative_volume_10d_calc"].fillna(0).clip(0, 3)
    df.loc[(df["change"] > 0) & (df["relative_volume_10d_calc"] > M_VOLUME_SURGE), "M_score"] += 0.3

    # RS — where price sits inside its own 52-week range (0 = at low, 1 = at high).
    df["RS_52w"] = (
        (df["close"] - df["price_52_week_low"])
        / (df["price_52_week_high"] - df["price_52_week_low"]).replace(0, 1)
    ).clip(0, 1)

    df["canslim_total"] = df[["C_score", "A_score", "N_score", "L_score", "I_score", "M_score"]].sum(axis=1)
    df["canslim_passes"] = df[[f"{f}_pass" for f in FACTORS]].astype(int).sum(axis=1)
    return df


def survivors(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only candidates passing at least MIN_FACTORS_PASSED, best first."""
    if df.empty:
        return df
    out = df[df["canslim_passes"] >= MIN_FACTORS_PASSED].copy()
    return out.sort_values("canslim_total", ascending=False)
