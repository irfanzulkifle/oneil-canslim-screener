"""Tests for the CAN SLIM screen, chart audit, and ranking.

These assert the exact boundaries, because an off-by-one in a threshold is
invisible in a lineup and only shows up months later as "why did this never
appear?". Every `pass` rule is tested on both sides of its boundary.
"""

from __future__ import annotations

import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src import chart_audit, ranking, scoring  # noqa: E402


def one(**overrides) -> pd.DataFrame:
    """A single-row frame with every column the scorer requires, all neutral.

    Defaults are chosen so that nothing passes: negative growth, far from the
    high, below the averages. Each test moves exactly one column.
    """
    base = {
        "close": 100.0,
        "change": 0.0,
        "SMA50": 105.0,
        "SMA200": 110.0,
        "RSI": 40.0,
        "price_52_week_high": 200.0,
        "price_52_week_low": 50.0,
        "earnings_per_share_diluted_yoy_growth_fq": 0.0,
        "earnings_per_share_diluted_yoy_growth_fy": 0.0,
        "earnings_per_share_diluted_5y_growth_fy": 0.0,
        "recommendation_mark": -0.5,
        "recommendation_buy": 0,
        "recommendation_total": 0,
        "relative_volume_10d_calc": 0.5,
    }
    base.update(overrides)
    return pd.DataFrame([base])


class TestUniverseDefaults(unittest.TestCase):
    def test_neutral_row_passes_nothing(self):
        row = scoring.score_canslim(one()).iloc[0]
        self.assertEqual(row["canslim_passes"], 0)
        for factor in scoring.FACTORS:
            self.assertFalse(row[f"{factor}_pass"], f"{factor} should not pass on defaults")


class TestCFactor(unittest.TestCase):
    def test_above_25_passes(self):
        row = scoring.score_canslim(one(earnings_per_share_diluted_yoy_growth_fq=26)).iloc[0]
        self.assertTrue(row["C_pass"])

    def test_exactly_25_fails(self):
        """The rule is strictly greater than 25, so 25.0 must not pass."""
        row = scoring.score_canslim(one(earnings_per_share_diluted_yoy_growth_fq=25)).iloc[0]
        self.assertFalse(row["C_pass"])

    def test_missing_data_fails_rather_than_passes(self):
        row = scoring.score_canslim(one(earnings_per_share_diluted_yoy_growth_fq=None)).iloc[0]
        self.assertFalse(row["C_pass"])


class TestAFactor(unittest.TestCase):
    def test_above_threshold_passes(self):
        row = scoring.score_canslim(one(earnings_per_share_diluted_yoy_growth_fy=30)).iloc[0]
        self.assertTrue(row["A_pass"])

    def test_exactly_25_fails(self):
        row = scoring.score_canslim(one(earnings_per_share_diluted_yoy_growth_fy=25)).iloc[0]
        self.assertFalse(row["A_pass"])

    def test_five_year_cagr_earns_bonus(self):
        weak = scoring.score_canslim(one(earnings_per_share_diluted_yoy_growth_fy=30)).iloc[0]["A_score"]
        strong = scoring.score_canslim(
            one(earnings_per_share_diluted_yoy_growth_fy=30,
                earnings_per_share_diluted_5y_growth_fy=30)
        ).iloc[0]["A_score"]
        self.assertAlmostEqual(strong - weak, 0.5)


class TestNFactor(unittest.TestCase):
    def test_within_15_percent_of_high_passes(self):
        row = scoring.score_canslim(one(close=90, price_52_week_high=100)).iloc[0]
        self.assertAlmostEqual(row["pct_from_52w_high"], -10.0)
        self.assertTrue(row["N_pass"])

    def test_beyond_15_percent_fails(self):
        row = scoring.score_canslim(one(close=80, price_52_week_high=100)).iloc[0]
        self.assertAlmostEqual(row["pct_from_52w_high"], -20.0)
        self.assertFalse(row["N_pass"])

    def test_exactly_15_percent_passes(self):
        """The comparison is >= -15, so -15.0 is inside the band."""
        row = scoring.score_canslim(one(close=85, price_52_week_high=100)).iloc[0]
        self.assertAlmostEqual(row["pct_from_52w_high"], -15.0)
        self.assertTrue(row["N_pass"])


class TestLFactor(unittest.TestCase):
    def test_above_200sma_passes(self):
        row = scoring.score_canslim(one(close=120, SMA200=110)).iloc[0]
        self.assertTrue(row["L_pass"])

    def test_below_200sma_fails(self):
        row = scoring.score_canslim(one(close=100, SMA200=110)).iloc[0]
        self.assertFalse(row["L_pass"])


class TestIFactor(unittest.TestCase):
    def test_positive_mark_passes(self):
        row = scoring.score_canslim(one(recommendation_mark=0.2)).iloc[0]
        self.assertTrue(row["I_pass"])

    def test_neutral_mark_fails(self):
        row = scoring.score_canslim(one(recommendation_mark=0.0)).iloc[0]
        self.assertFalse(row["I_pass"])

    def test_missing_mark_fails(self):
        row = scoring.score_canslim(one(recommendation_mark=None)).iloc[0]
        self.assertFalse(row["I_pass"])


class TestMFactor(unittest.TestCase):
    def test_above_average_volume_passes(self):
        row = scoring.score_canslim(one(relative_volume_10d_calc=1.1)).iloc[0]
        self.assertTrue(row["M_pass"])

    def test_exactly_average_volume_fails(self):
        """Strictly greater than 1.0, so exactly 1.0 is not accumulation."""
        row = scoring.score_canslim(one(relative_volume_10d_calc=1.0)).iloc[0]
        self.assertFalse(row["M_pass"])


class TestSurvivorGate(unittest.TestCase):
    def _frame(self, n_pass: int) -> pd.DataFrame:
        """Build a frame whose row passes exactly n_pass factors."""
        kwargs = {}
        if n_pass >= 1:
            kwargs["earnings_per_share_diluted_yoy_growth_fq"] = 50
        if n_pass >= 2:
            kwargs["earnings_per_share_diluted_yoy_growth_fy"] = 50
        if n_pass >= 3:
            kwargs["close"] = 95
            kwargs["price_52_week_high"] = 100
        if n_pass >= 4:
            kwargs["SMA200"] = 90
        if n_pass >= 5:
            kwargs["recommendation_mark"] = 0.5
        if n_pass >= 6:
            kwargs["relative_volume_10d_calc"] = 1.5
        return scoring.score_canslim(one(**kwargs))

    def test_three_of_six_is_excluded(self):
        scored = self._frame(3)
        self.assertEqual(scored.iloc[0]["canslim_passes"], 3)
        self.assertEqual(len(scoring.survivors(scored)), 0)

    def test_four_of_six_is_included(self):
        scored = self._frame(4)
        self.assertEqual(scored.iloc[0]["canslim_passes"], 4)
        self.assertEqual(len(scoring.survivors(scored)), 1)

    def test_survivors_are_sorted_by_score(self):
        low = self._frame(4).assign(ticker="LOW")
        high = self._frame(6).assign(ticker="HIGH")
        out = scoring.survivors(pd.concat([low, high]))
        self.assertEqual(list(out["ticker"]), ["HIGH", "LOW"])


class TestChartAudit(unittest.TestCase):
    @staticmethod
    def _bars(n=260, start=100.0, step=0.5, volume=1_000_000):
        closes = [start + step * i for i in range(n)]
        return pd.DataFrame({
            "Close": closes,
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Volume": [volume] * n,
        })

    def test_insufficient_history_returns_none_not_zero(self):
        """A data gap must be 'unknown', never scored as a bad chart."""
        self.assertIsNone(chart_audit.audit(self._bars(n=50), self._bars(n=260)))

    def test_none_input_returns_none(self):
        self.assertIsNone(chart_audit.audit(None, self._bars()))

    def test_score_is_within_range(self):
        result = chart_audit.audit(self._bars(), self._bars(step=0.1))
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 5)

    def test_clean_uptrend_beats_benchmark_and_aligns(self):
        result = chart_audit.audit(self._bars(step=0.5), self._bars(step=0.05))
        self.assertTrue(result["checks"]["sma_aligned"])
        self.assertTrue(result["checks"]["rs_3m_positive"])

    def test_volume_dry_up_detected(self):
        bars = self._bars()
        bars.loc[bars.index[-3:], "Volume"] = 100_000  # far below baseline
        result = chart_audit.audit(bars, self._bars(step=0.1))
        self.assertTrue(result["checks"]["vdu"])

    def test_no_dry_up_when_volume_steady(self):
        result = chart_audit.audit(self._bars(), self._bars(step=0.1))
        self.assertFalse(result["checks"]["vdu"])


class TestRanking(unittest.TestCase):
    def test_weights_are_sixty_forty(self):
        out = ranking.rank([{"screener_score": 10, "chart_score": 0}])
        self.assertAlmostEqual(out[0]["final_rank"], 6.0)

        out = ranking.rank([{"screener_score": 0, "chart_score": 5}])
        self.assertAlmostEqual(out[0]["final_rank"], 2.0)

    def test_sorted_best_first(self):
        out = ranking.rank([
            {"ticker": "B", "screener_score": 2, "chart_score": 1},
            {"ticker": "A", "screener_score": 5, "chart_score": 4},
        ])
        self.assertEqual([c["ticker"] for c in out], ["A", "B"])

    def test_leading_sector_gets_bonus(self):
        ranked = ranking.rank([{"screener_score": 5, "chart_score": 3, "sector": "Technology"}])
        before = ranked[0]["final_rank"]
        ranking.apply_m_factor(ranked, {"Technology": (1, 100.0)})
        self.assertAlmostEqual(ranked[0]["final_rank"], before + 0.5)

    def test_lagging_sector_gets_penalty(self):
        ranked = ranking.rank([{"screener_score": 5, "chart_score": 3, "sector": "Utilities"}])
        before = ranked[0]["final_rank"]
        ranking.apply_m_factor(ranked, {"Utilities": (20, 1.0)})
        self.assertAlmostEqual(ranked[0]["final_rank"], round(before - 0.3, 10))

    def test_empty_sector_map_skips_adjustment(self):
        """No data must not be treated as a penalty bucket."""
        ranked = ranking.rank([{"screener_score": 5, "chart_score": 3, "sector": "Utilities"}])
        before = ranked[0]["final_rank"]
        ranking.apply_m_factor(ranked, {})
        self.assertAlmostEqual(ranked[0]["final_rank"], before)
        self.assertNotIn("sector_rs_rank", ranked[0])

    def test_unmapped_sector_is_recorded_as_unknown(self):
        ranked = ranking.rank([{"screener_score": 5, "chart_score": 3, "sector": "Nonsense"}])
        ranking.apply_m_factor(ranked, {"Technology": (1, 100.0)})
        self.assertIsNone(ranked[0]["sector_rs_rank"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
