"""
validate.py - run the golden set through the grader and measure the grader itself.

For each case we score it on ITS target dimension (that's what the golden label
refers to) with the primary judge, and independently with a second judge. Then:
  * detection rate / false-positive rate / exact-match for the primary judge
  * inter-judge agreement (Cohen's kappa) overall and per dimension

This is the "test the tester" step. The numbers it prints are only as real as
the judges you plug in: with MockJudge they are SYNTHETIC; with OpenAI/Anthropic
judges and your API keys they are real.
"""

import json
import os
from collections import defaultdict

from . import metrics
from .rubric import DIMENSIONS


def load_golden():
    path = os.path.join(os.path.dirname(__file__), "golden_set.json")
    with open(path) as f:
        return json.load(f)


def _enforce_judge_not_target(judge, target_family, allow_same=False):
    if target_family and judge.family == target_family and not allow_same:
        raise ValueError(
            f"Judge family '{judge.family}' matches target family '{target_family}'. "
            "A model is a poor auditor of its own failure modes. Use a different judge "
            "or pass allow_same=True to override (results are lower-confidence)."
        )


def run_validation(primary_judge, second_judge=None, target_family=None,
                   allow_same=False, verbose=True):
    _enforce_judge_not_target(primary_judge, target_family, allow_same)

    cases = load_golden()
    rows = []              # primary judge results
    second_rows = []       # second judge results (for agreement)

    for c in cases:
        dim = c["dimension"]
        p = primary_judge.score(c, dim)
        row = {"id": c["id"], "dimension": dim, "expected": c["expected"],
               "score": p["score"], "agreement": p["agreement"],
               "evidence": p["evidence"], "name": c["name"]}
        rows.append(row)

        if second_judge is not None:
            s = second_judge.score(c, dim)
            second_rows.append({"id": c["id"], "dimension": dim, "score": s["score"]})

        if verbose:
            flag = "FLAG" if (p["score"] != "N/A" and p["score"] <= 1) else "ok  "
            match = "=" if p["score"] == c["expected"] else "x"
            print(f"  {c['id']:6} {dim} exp={c['expected']} got={p['score']:<3} "
                  f"[{flag}] {match} run-agree={p['agreement']}")

    report = _build_report(rows, second_rows)
    return report


def _build_report(rows, second_rows):
    report = {
        "n_cases": len(rows),
        "primary": {
            "detection_rate": metrics.detection_rate(rows),
            "false_positive_rate": metrics.false_positive_rate(rows),
            "exact_match": metrics.exact_match(rows),
            "within_one": metrics.within_one(rows),
        },
        "per_dimension": {},
        "inter_judge": None,
        "misses": [],
    }

    # per-dimension exact-match for the primary judge
    by_dim = defaultdict(list)
    for r in rows:
        by_dim[r["dimension"]].append(r)
    for dim, drows in by_dim.items():
        report["per_dimension"][dim] = {
            "name": DIMENSIONS[dim]["name"],
            "exact_match": metrics.exact_match(drows),
            "detection_rate": metrics.detection_rate(drows),
        }

    # inter-judge agreement
    if second_rows:
        idx = {r["id"]: r["score"] for r in second_rows}
        a = [r["score"] for r in rows]
        b = [idx.get(r["id"]) for r in rows]
        overall_k = metrics.cohen_kappa(a, b)
        report["inter_judge"] = {
            "overall_kappa": overall_k,
            "overall_kappa_label": metrics.kappa_label(overall_k),
            "overall_percent_agreement": metrics.percent_agreement(a, b),
            "by_dimension": {},
        }
        for dim, drows in by_dim.items():
            da = [r["score"] for r in drows]
            db = [idx.get(r["id"]) for r in drows]
            k = metrics.cohen_kappa(da, db)
            report["inter_judge"]["by_dimension"][dim] = {
                "kappa": k,
                "label": metrics.kappa_label(k),
                "percent_agreement": metrics.percent_agreement(da, db),
            }

    # list the primary judge's mistakes (score != expected)
    for r in rows:
        if r["score"] != r["expected"]:
            report["misses"].append({
                "id": r["id"], "dimension": r["dimension"],
                "expected": r["expected"], "got": r["score"], "name": r["name"],
            })

    return report


def print_report(report, synthetic=False):
    line = "=" * 64
    print("\n" + line)
    if synthetic:
        print("  SYNTHETIC RESULTS - mock judge, NOT real model output.")
        print("  Do NOT use these numbers anywhere. Run with real judges.")
        print(line)
    p = report["primary"]
    print(f"  cases:              {report['n_cases']}")
    print(f"  detection rate:     {_pct(p['detection_rate'])}   (of known failures, how many flagged)")
    print(f"  false-positive rate:{_pct(p['false_positive_rate'])}   (of clean responses, how many wrongly flagged)")
    print(f"  exact-match:        {_pct(p['exact_match'])}   (judge score == expected)")
    print(f"  within-one:         {_pct(p['within_one'])}")
    ij = report.get("inter_judge")
    if ij:
        print(f"\n  inter-judge kappa:  {_num(ij['overall_kappa'])} ({ij['overall_kappa_label']})   "
              f"agreement={_pct(ij['overall_percent_agreement'])}")
        print("  kappa by dimension (low = judges disagree on what the score should be):")
        for dim, d in sorted(ij["by_dimension"].items()):
            print(f"     {dim} {DIMENSIONS[dim]['name']:<28} kappa={_num(d['kappa'])} ({d['label']})")
    if report["misses"]:
        print(f"\n  primary-judge misses ({len(report['misses'])}):")
        for m in report["misses"]:
            print(f"     {m['id']:6} {m['dimension']} exp={m['expected']} got={m['got']}  {m['name']}")
    print(line + "\n")


def _pct(x):
    return "  n/a" if x is None else f"{x*100:5.1f}%"


def _num(x):
    return " n/a" if x is None else f"{x:5.2f}"
