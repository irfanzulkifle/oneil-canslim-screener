"""Command line entry point.

  python -m oneil.cli --demo
  python -m oneil.cli --snapshot snapshot.json
  python -m oneil.cli --gate 4.30 4.32 4.41 ... --vix 17.5

The snapshot format is deliberately plain JSON so a scan produced anywhere
(TradingView export, a database dump, another language) can be re-scored
without re-fetching anything.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import pipeline, rules, score, synthetic


def _print_results(results, funnel) -> None:
    print()
    print(pipeline.funnel_report(funnel))
    print()
    if not results:
        print("  No candidate cleared the funnel. That is a normal outcome;")
        print(f"  the minimum rank is {rules.FINAL_RANK_MIN:.1f} of a "
              f"{rules.FINAL_RANK_CEILING:.1f} ceiling.")
        return

    header = (f"  {'ticker':<16}{'sector':<18}{'screen':>7}{'chart':>7}"
              f"{'rank':>7}{'W':>4}  checks")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in results:
        checks = []
        for key, label in (("sma_aligned", "SMA"), ("rs_line_new_high", "RS"),
                           ("vdu", "VDU"), ("vcp", "VCP")):
            if r.audit.get(key):
                checks.append(label)
        if (r.audit.get("rs_3m_pct") or 0) > 0:
            checks.append("3M")
        print(f"  {r.ticker:<16}{r.sector[:17]:<18}{r.screener_score:>7}"
              f"{r.chart_score:>7}{r.final_rank:>7.2f}{r.weekly_passes:>4}  "
              f"{','.join(checks) if checks else '-'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="O'Neil CAN SLIM screening funnel")
    parser.add_argument("--demo", action="store_true",
                        help="run on the built-in synthetic universe")
    parser.add_argument("--snapshot", help="JSON file with benchmark + candidates")
    parser.add_argument("--min-rank", type=float, default=rules.FINAL_RANK_MIN,
                        help=f"final rank floor (default {rules.FINAL_RANK_MIN})")
    parser.add_argument("--gate", nargs="*", type=float,
                        help="10Y closes, oldest first, for the deploy gate")
    parser.add_argument("--vix", type=float, help="latest VIX close")
    args = parser.parse_args(argv)

    if args.gate or args.vix:
        state = score.deploy_gate(args.gate, args.vix)
        print(json.dumps(state.as_dict(), indent=2))
        if not args.demo and not args.snapshot:
            return 0

    if not args.demo and not args.snapshot:
        parser.print_help()
        return 1

    if args.snapshot:
        with open(args.snapshot, encoding="utf-8") as fh:
            payload = json.load(fh)
        candidates = payload.get("candidates", [])
        benchmark = payload.get("benchmark", {})
        for c in candidates:
            c.setdefault("benchmark", benchmark)
    else:
        candidates = synthetic.demo_universe()

    results, funnel = pipeline.screen(candidates, min_rank=args.min_rank)
    _print_results(results, funnel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
