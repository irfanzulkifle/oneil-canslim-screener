"""Deterministic synthetic price series.

There is no real market data in this repository. The demo and the tests need
bars with known properties (a clean uptrend, a tight contraction, a volume
dry-up, a downtrend), so the series are generated here with a fixed seed and
labelled as synthetic everywhere they are used.

Do not read anything into these prices. They exist to exercise the rules.
"""
from __future__ import annotations

import numpy as np


def make_bars(
    n: int = 260,
    start: float = 100.0,
    drift: float = 0.0015,
    vol: float = 0.014,
    seed: int = 7,
    dry_up: bool = False,
    contract: bool = False,
    volume_base: float = 1_000_000.0,
) -> dict:
    """Return {"close", "high", "low", "open", "volume"} as plain lists."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    closes = start * np.exp(np.cumsum(returns))
    opens = np.concatenate([closes[:1], closes[:-1]]) * (1 + rng.normal(0, 0.002, n))
    highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, 0.004, n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, 0.004, n)))
    volumes = volume_base * rng.lognormal(0.0, 0.25, n)

    if contract:
        # Last five sessions pinned inside a 0.8% band: a textbook contraction.
        anchor = closes[-1]
        highs[-5:] = anchor * 1.004
        lows[-5:] = anchor * 0.996

    if dry_up:
        # Last three sessions at a quarter of the trailing average volume.
        baseline = float(np.mean(volumes[-53:-3]))
        volumes[-3:] = baseline * 0.25

    return {
        "close": [round(float(x), 4) for x in closes],
        "high": [round(float(x), 4) for x in highs],
        "low": [round(float(x), 4) for x in lows],
        "open": [round(float(x), 4) for x in opens],
        "volume": [int(x) for x in volumes],
    }


def demo_universe() -> list[dict]:
    """Five synthetic candidates: one clean setup, one extended, three rejects.

    The point is to show the funnel doing its job: the clean name reaches the
    top, and each kind of flaw is rejected at a specific stage.
    """
    benchmark = make_bars(n=260, start=400.0, drift=0.0004, vol=0.008, seed=1)

    def weekly(close, sma10w, sma30w, rsi, high52, rel_vol, eps_q, eps_a, mcap=5e9):
        return {
            "close": close, "sma10w": sma10w, "sma30w": sma30w, "rsi7w": rsi,
            "high_52w": high52, "rel_vol_w": rel_vol,
            "eps_q_yoy": eps_q, "eps_a_yoy": eps_a, "market_cap": mcap,
        }

    clean_bars = make_bars(n=260, start=40.0, drift=0.0035, vol=0.011, seed=11,
                           dry_up=True, contract=True)
    extended_bars = make_bars(n=260, start=40.0, drift=0.0045, vol=0.020, seed=12)
    downtrend_bars = make_bars(n=260, start=90.0, drift=-0.0025, vol=0.016, seed=13)
    choppy_bars = make_bars(n=260, start=60.0, drift=0.0002, vol=0.020, seed=14)

    candidates = [
        {
            "ticker": "SYN-CLEAN", "sector": "Software", "sector_rank": 2,
            "bars": clean_bars, "benchmark": benchmark,
            "weekly": weekly(clean_bars["close"][-1], clean_bars["close"][-1] / 1.06,
                             clean_bars["close"][-1] / 1.18, 64.0,
                             clean_bars["close"][-1] * 1.02, 1.4, 41.0, 33.0),
            "fundamentals": {"eps_q_yoy": 41.0, "eps_a_yoy": 33.0, "eps_5y_cagr": 28.0,
                             "sma50": clean_bars["close"][-1] / 1.03,
                             "sma200": clean_bars["close"][-1] / 1.15,
                             "rsi": 61.0, "rec_mark": 0.55, "pct_buy": 0.7,
                             "rel_vol": 1.3, "change": 1.2},
        },
        {
            "ticker": "SYN-EXTENDED", "sector": "Semiconductors", "sector_rank": 1,
            "bars": extended_bars, "benchmark": benchmark,
            "weekly": weekly(extended_bars["close"][-1], extended_bars["close"][-1] / 1.22,
                             extended_bars["close"][-1] / 1.45, 82.0,
                             extended_bars["close"][-1] * 1.01, 2.1, 55.0, 48.0),
            "fundamentals": {"eps_q_yoy": 55.0, "eps_a_yoy": 48.0, "eps_5y_cagr": 40.0,
                             "sma50": extended_bars["close"][-1] / 1.10,
                             "sma200": extended_bars["close"][-1] / 1.40,
                             "rsi": 78.0, "rec_mark": 0.7, "pct_buy": 0.8,
                             "rel_vol": 1.8, "change": 2.5},
        },
        {
            "ticker": "SYN-BELOW-TREND", "sector": "Retail", "sector_rank": 9,
            "bars": downtrend_bars, "benchmark": benchmark,
            "weekly": weekly(downtrend_bars["close"][-1], downtrend_bars["close"][-1] * 1.08,
                             downtrend_bars["close"][-1] * 1.25, 42.0,
                             downtrend_bars["close"][-1] * 1.60, 0.8, 12.0, 9.0),
            "fundamentals": {"eps_q_yoy": 12.0, "eps_a_yoy": 9.0, "eps_5y_cagr": 4.0,
                             "sma50": downtrend_bars["close"][-1] * 1.10,
                             "sma200": downtrend_bars["close"][-1] * 1.30,
                             "rsi": 38.0, "rec_mark": -0.2, "pct_buy": 0.2,
                             "rel_vol": 0.7, "change": -1.4},
        },
        {
            "ticker": "SYN-WEAK-EPS", "sector": "Utilities", "sector_rank": 11,
            "bars": choppy_bars, "benchmark": benchmark,
            "weekly": weekly(choppy_bars["close"][-1], choppy_bars["close"][-1] / 1.01,
                             choppy_bars["close"][-1] / 1.02, 63.0,
                             choppy_bars["close"][-1] * 1.04, 1.1, 6.0, 4.0),
            "fundamentals": {"eps_q_yoy": 6.0, "eps_a_yoy": 4.0, "eps_5y_cagr": 2.0,
                             "sma50": choppy_bars["close"][-1] * 0.99,
                             "sma200": choppy_bars["close"][-1] * 0.95,
                             "rsi": 55.0, "rec_mark": 0.0, "pct_buy": 0.3,
                             "rel_vol": 1.05, "change": 0.2},
        },
        {
            "ticker": "SYN-MICROCAP", "sector": "Industrials", "sector_rank": 5,
            "bars": make_bars(n=260, start=12.0, drift=0.002, vol=0.018, seed=15),
            "benchmark": benchmark,
            "weekly": weekly(12.0 * 1.4, 12.0 * 1.4 / 1.05, 12.0 * 1.4 / 1.12, 66.0,
                             12.0 * 1.5, 1.2, 30.0, 26.0, mcap=80_000_000),
            "fundamentals": {"eps_q_yoy": 30.0, "eps_a_yoy": 26.0, "eps_5y_cagr": 20.0,
                             "sma50": 16.0, "sma200": 14.0, "rsi": 60.0,
                             "rec_mark": 0.3, "pct_buy": 0.5,
                             "rel_vol": 1.2, "change": 0.9},
        },
    ]
    return candidates
