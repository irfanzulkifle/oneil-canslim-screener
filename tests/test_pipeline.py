from oneil import pipeline, rules, synthetic


def test_demo_funnel_counts():
    results, funnel = pipeline.screen(synthetic.demo_universe())
    assert funnel.universe == 5
    assert funnel.weekly_gate == 3          # trend gate removes two
    assert funnel.fundamentals == 3         # all three score >= 3 factors
    assert funnel.chart_audited == 3
    assert funnel.above_min_rank == 2


def test_clean_setup_ranks_first_and_near_ceiling():
    results, _ = pipeline.screen(synthetic.demo_universe())
    assert results[0].ticker == "SYN-CLEAN"
    assert results[0].final_rank <= rules.FINAL_RANK_CEILING
    assert results[0].chart_score == 5


def test_microcap_never_reaches_the_chart_audit():
    results, _ = pipeline.screen(synthetic.demo_universe())
    assert "SYN-MICROCAP" not in [r.ticker for r in results]


def test_weak_fundamentals_are_dropped_before_the_chart():
    results, funnel = pipeline.screen(synthetic.demo_universe())
    assert "SYN-WEAK-EPS" not in [r.ticker for r in results]


def test_min_rank_filter_is_applied():
    results, funnel = pipeline.screen(synthetic.demo_universe(), min_rank=5.5)
    assert [r.ticker for r in results] == ["SYN-CLEAN"]
    assert funnel.above_min_rank == 1


def test_results_are_sorted_by_rank():
    results, _ = pipeline.screen(synthetic.demo_universe())
    ranks = [r.final_rank for r in results]
    assert ranks == sorted(ranks, reverse=True)


def test_short_history_is_unaudited_not_scored_zero():
    candidates = synthetic.demo_universe()
    candidates[0]["bars"] = {k: v[:60] for k, v in candidates[0]["bars"].items()}
    results, funnel = pipeline.screen(candidates)
    assert funnel.unaudited == 1
    assert "SYN-CLEAN" not in [r.ticker for r in results]


def test_unaudited_can_be_ranked_only_on_request():
    candidates = synthetic.demo_universe()
    candidates[0]["bars"] = {k: v[:60] for k, v in candidates[0]["bars"].items()}
    results, funnel = pipeline.screen(candidates, allow_unaudited=True, min_rank=0)
    scores = {r.ticker: r.chart_score for r in results}
    assert scores["SYN-CLEAN"] == 0
    assert funnel.unaudited == 1
