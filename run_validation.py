#!/usr/bin/env python3
"""
Run judge validation over the 40-case golden set.

OFFLINE (no keys, proves the pipeline works; numbers are SYNTHETIC):
    python run_validation.py --mock

REAL (your keys; these numbers are the ones for the post):
    export OPENAI_API_KEY=sk-...
    export ANTHROPIC_API_KEY=sk-ant-...
    python run_validation.py            # GPT-4o primary, Claude second judge

Flags:
    --mock       use offline stub judges (synthetic output)
    --runs N     runs per dimension for the consistency signal (default 3)
    --json PATH  also write the full report as JSON
"""

import argparse
import json
import sys

from litmus import run_validation, print_report
from litmus.judge import OpenAIJudge, AnthropicJudge, MockJudgeA, MockJudgeB


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="offline stub judges (synthetic)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--json", type=str, default=None)
    args = ap.parse_args()

    if args.mock:
        primary, second = MockJudgeA(runs=args.runs), MockJudgeB(runs=args.runs)
        # target is a Claude-based product in our examples; primary judge is a mock,
        # so the judge!=target check is not triggered here.
        target_family = None
    else:
        # GPT-4o judges; the products under test are Claude-based -> judge != target holds.
        primary = OpenAIJudge(model="gpt-4o", runs=args.runs)
        second = AnthropicJudge(model="claude-sonnet-4-6", runs=args.runs)
        target_family = "claude"

    print(f"Running validation ({'MOCK/synthetic' if args.mock else 'real judges'}), "
          f"runs={args.runs} ...\n")
    report = run_validation(primary, second_judge=second,
                            target_family=target_family, verbose=True)
    print_report(report, synthetic=args.mock)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Wrote report -> {args.json}")

    if args.mock:
        print("Reminder: --mock numbers are SYNTHETIC. Re-run with real keys for the post.")


if __name__ == "__main__":
    sys.exit(main())
