import pytest

from oneil import chart, rules


def test_sma_alignment_true_on_rising_series():
    closes = [float(i) for i in range(1, 261)]
    assert chart.sma_alignment(closes) is True


def test_sma_alignment_false_on_falling_series():
    closes = [float(i) for i in range(260, 0, -1)]
    assert chart.sma_alignment(closes) is False


def test_sma_alignment_none_without_enough_history():
    assert chart.sma_alignment([1.0] * 199) is None


def test_vdu_ratio_is_measured_against_prior_50():
    volumes = [100.0] * 53
    volumes[-3:] = [30.0, 30.0, 30.0]
    dry, ratio = chart.vdu(volumes)
    assert dry is True
    assert ratio == pytest.approx(0.30)


def test_vdu_false_when_volume_is_average():
    dry, ratio = chart.vdu([100.0] * 53)
    assert dry is False
    assert ratio == pytest.approx(1.0)


def test_vcp_contracts_when_last_five_sessions_are_tight():
    closes = [100.0] * 25
    highs = [110.0] * 20 + [100.4] * 5
    lows = [95.0] * 20 + [99.6] * 5
    contracted, recent, prior = chart.vcp(highs, lows, closes)
    assert contracted is True
    assert prior == pytest.approx(15.0, abs=0.01)     # (110-95)/100
    assert recent == pytest.approx(0.8, abs=0.01)     # (100.4-99.6)/100


def test_vcp_false_when_range_expands():
    closes = [100.0] * 25
    highs = [101.0] * 20 + [112.0] * 5
    lows = [99.0] * 20 + [88.0] * 5
    contracted, _, _ = chart.vcp(highs, lows, closes)
    assert contracted is False


def test_rs_line_new_high_when_outperforming_into_the_close():
    stock = [100.0 * (1.002 ** i) for i in range(120)]
    bench = [100.0] * 120
    is_high, ratio = chart.rs_line_new_high(stock, bench)
    assert is_high is True
    assert ratio == pytest.approx(stock[-1] / bench[-1])


def test_rs_line_not_new_high_after_a_break():
    stock = [100.0 * (1.003 ** i) for i in range(100)] + [120.0, 118.0] * 10
    bench = [100.0] * 120
    is_high, _ = chart.rs_line_new_high(stock, bench)
    assert is_high is False


def test_rs_3m_is_excess_return():
    stock = [100.0] + [110.0] * 62
    bench = [100.0] * 63
    assert chart.rs_3m(stock, bench) == pytest.approx(10.0, abs=0.01)


def test_audit_scores_zero_to_five():
    rising = [float(i) for i in range(1, 261)]
    bars = {
        "close": rising,
        "high": [x * 1.01 for x in rising],
        "low": [x * 0.99 for x in rising],
        "volume": [1e6] * 260,
    }
    result = chart.audit(bars, bars)
    assert result is not None
    assert 0 <= result.score <= rules.CHART_CHECKS


def test_audit_returns_none_without_history():
    assert chart.audit({"close": [1.0] * 50}, {"close": [1.0] * 50}) is None
