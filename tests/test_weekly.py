import math

import pytest

from oneil import rules, weekly


def row(**kw):
    base = {
        "close": 100.0, "sma10w": 88.0, "sma30w": 75.0, "rsi7w": 65.0,
        "high_52w": 104.0, "rel_vol_w": 1.4, "eps_q_yoy": 40.0,
        "eps_a_yoy": 35.0, "market_cap": 5e9,
    }
    base.update(kw)
    return base


def test_gate_passes_on_trending_name():
    assert weekly.gate(row()) is True


@pytest.mark.parametrize("override", [
    {"rsi7w": 59.9},
    {"close": 87.0},          # below the 10-week
    {"close": 70.0},          # below the 30-week
    {"market_cap": 9e8},      # under the weekly floor
    {"sma10w": 0},            # no data is not a pass
])
def test_gate_rejects(override):
    assert weekly.gate(row(**override)) is False


def test_score_counts_five_factors():
    s = weekly.score(row())
    assert s.w_passes == 5
    assert all([s.c_pass, s.a_pass, s.n_pass, s.l_pass, s.m_pass])


def test_eps_threshold_is_strict():
    assert weekly.score(row(eps_q_yoy=25.0)).c_pass is False
    assert weekly.score(row(eps_q_yoy=25.1)).c_pass is True


def test_missing_eps_fails_rather_than_passes():
    s = weekly.score(row(eps_q_yoy=None, eps_a_yoy=None))
    assert s.c_pass is False and s.a_pass is False
    assert s.w_passes == 3


def test_full_marks_arithmetic():
    # c 2.0 + a 2.0 + trend (10% -> 1.0) + volume 2.0 + rsi 60/50
    s = weekly.score(row(eps_q_yoy=100.0, eps_a_yoy=100.0, rsi7w=60.0,
                         close=96.8, sma10w=88.0, rel_vol_w=2.0))
    assert s.pct_above_10w == pytest.approx(10.0, abs=0.01)
    assert s.w_total == pytest.approx(2.0 + 2.0 + 1.0 + 2.0 + 1.2, abs=0.01)


def test_rsi_band_is_a_score_not_a_gate():
    # 90 weekly RSI still passes the gate (momentum), but L fails as exhaustion
    s = weekly.score(row(rsi7w=90.0))
    assert s.l_pass is False
    assert s.w_passes == 4


def test_missing_52w_high_fails_n():
    """No 52-week high must fail N, not default to today's close.

    The old default made pct_from_52w exactly 0.0, so a stock with no high data
    scored a perfect 5/5 - the precise failure the README promises cannot happen.
    """
    r = row()
    del r["high_52w"]
    s = weekly.score(r)
    assert s.n_pass is False
    assert s.pct_from_52w_high is None
    assert s.w_passes == 4


def test_zero_52w_high_fails_n():
    assert weekly.score(row(high_52w=0.0)).n_pass is False


def test_missing_market_cap_fails_gate():
    """A blank cap is not a pass: the old `if mcap and ...` let 0.0 through."""
    r = row()
    del r["market_cap"]
    assert weekly.gate(r) is False


def test_negative_market_cap_fails_gate():
    assert weekly.gate(row(market_cap=-1.0)) is False

