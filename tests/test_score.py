import pytest

from oneil import rules, score


def fundamentals(**kw):
    base = {
        "eps_q_yoy": 40.0, "eps_a_yoy": 35.0, "eps_5y_cagr": 20.0,
        "close": 100.0, "high_52w": 103.0, "sma200": 80.0, "sma50": 95.0,
        "rsi": 61.0, "rec_mark": 0.5, "pct_buy": 0.6,
        "rel_vol": 1.3, "change": 1.1,
    }
    base.update(kw)
    return base


def test_all_six_factors_pass():
    f = score.canslim_factors(fundamentals())
    assert f.passes == 6
    assert f.c and f.a and f.n and f.l and f.i and f.m


def test_missing_values_do_not_pass():
    f = score.canslim_factors({})
    assert f.passes == 0
    assert f.total == 0.0


def test_c_threshold():
    assert score.canslim_factors(fundamentals(eps_q_yoy=25.0)).c is False
    assert score.canslim_factors(fundamentals(eps_q_yoy=25.01)).c is True


def test_c_score_is_capped_at_two():
    f = score.canslim_factors(fundamentals(eps_q_yoy=500.0))
    assert f.total <= 12.0


def test_n_is_within_fifteen_percent_of_high():
    assert score.canslim_factors(fundamentals(close=84.0, high_52w=100.0)).n is False
    assert score.canslim_factors(fundamentals(close=85.0, high_52w=100.0)).n is True


def test_final_rank_math():
    assert score.final_rank(6, 5, None) == pytest.approx(5.6)
    assert score.final_rank(6, 5, 2) == pytest.approx(6.1)
    assert score.final_rank(5, 3, 1) == pytest.approx(4.7)
    assert score.final_rank(5, 3, 11) == pytest.approx(3.9)


def test_ceiling_is_the_arithmetic_maximum():
    assert rules.FINAL_RANK_CEILING == pytest.approx(6.1)
    assert score.final_rank(6, 5, 1) == pytest.approx(rules.FINAL_RANK_CEILING)


def test_unreachable_bar_is_detected():
    assert score.rank_is_reachable(4.0) is True
    assert score.rank_is_reachable(6.1) is True
    assert score.rank_is_reachable(7.0) is False


@pytest.mark.parametrize("rank,expected", [
    (1, 0.5), (3, 0.5), (4, 0.2), (6, 0.2), (7, 0.0), (10, 0.0), (11, -0.3), (None, 0.0),
])
def test_sector_boost(rank, expected):
    assert score.sector_boost(rank) == pytest.approx(expected)


def flat(level, n):
    return [level] * n


def test_gate_halts_on_rate_shock():
    series = flat(4.20, 10) + [4.50]
    state = score.deploy_gate(series, vix=15.0)
    assert state.tier == "HALT"
    assert state.can_deploy is False


def test_high_but_stable_rate_halves_size_not_a_ban():
    state = score.deploy_gate(flat(4.70, 11), vix=15.0)
    assert state.tier == "HALF"
    assert state.sizing_multiplier == 0.5
    assert state.can_deploy is True


def test_full_size_below_the_sizing_line():
    state = score.deploy_gate(flat(4.10, 11), vix=14.0)
    assert state.tier == "FULL"
    assert state.sizing_multiplier == 1.0


def test_vix_above_twenty_halts():
    state = score.deploy_gate(flat(4.10, 11), vix=23.0)
    assert state.tier == "HALT"
    assert state.can_deploy is False


def test_blank_leg_is_not_a_pass():
    state = score.deploy_gate([], vix=None)
    assert state.can_deploy is False
    assert state.tier == "NO_DATA"
