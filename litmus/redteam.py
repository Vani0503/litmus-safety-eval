"""
redteam.py - fire the adversarial suite at a live product and score what comes back.

Flow (this is input-mode B from the spec; the grader is the same engine used in
validation, input-mode A):

    for each probe:
        response = target.ask(probe.prompt)     # calls YOUR product
        result   = grade_response(probe, response, judge)   # same grader
    -> aggregate into a product-level safety report
"""

from collections import defaultdict

from .grader import grade_response
from .redteam_prompts import select_prompts, SCOPES
from .rubric import DIMENSIONS


def _enforce_judge_not_target(judge, target, allow_same=False):
    tf = getattr(target, "model_family", "other")
    if tf and judge.family == tf and tf != "other" and not allow_same:
        raise ValueError(
            f"Judge family '{judge.family}' matches target family '{tf}'. "
            "Use a different judge (a model is a poor auditor of its own blind "
            "spots) or pass allow_same=True."
        )


def run_redteam(target, judge, scope="all", categories=None, all_dims=False,
                allow_same=False, verbose=True):
    _enforce_judge_not_target(judge, target, allow_same)
    probes = select_prompts(scopes=SCOPES.get(scope, ("any",)), categories=categories)

    results = []
    for p in probes:
        if hasattr(target, "bind"):
            target.bind(p["id"])            # ManualFileTarget needs the id
        try:
            response = target.ask(p["prompt"])
        except Exception as e:
            if verbose:
                print(f"  {p['id']:7} ERROR calling target: {e}")
            continue
        res = grade_response(p, response, judge, all_dims=all_dims)
        results.append(res)
        if verbose:
            tag = "FAIL" if res["response_score"] == 0.0 else \
                  ("flag" if res["flags"] else "ok  ")
            print(f"  {p['id']:7} {p['category']:24} score={_fmt(res['response_score'])} "
                  f"[{tag}] {' '.join(res['flags'])}")

    return _product_report(results)


def _product_report(results):
    graded = [r for r in results if r["response_score"] is not None]
    n = len(graded)
    passed = [r for r in graded if not r["flags"]]
    any_zero = [r for r in graded if r["response_score"] == 0.0]

    # per-dimension mean across everywhere that dimension was scored
    dim_scores = defaultdict(list)
    for r in graded:
        for d, dd in r["dimensions"].items():
            if dd["score"] != "N/A":
                dim_scores[d].append(dd["score"])
    per_dim = {d: round(sum(v) / len(v), 2) for d, v in dim_scores.items() if v}

    worst = sorted(
        [r for r in graded if r["flags"]],
        key=lambda r: (r["worst"] if r["worst"] is not None else 9, r["probe_id"]),
    )

    return {
        "n_prompts": n,
        "product_score": round(sum(r["response_score"] for r in graded) / n, 3) if n else None,
        "pass_rate": round(len(passed) / n, 3) if n else None,
        "any_zero_rate": round(len(any_zero) / n, 3) if n else None,
        "per_dimension_mean": per_dim,
        "worst_failures": [
            {"probe_id": r["probe_id"], "category": r["category"],
             "prompt": r["prompt"], "response": r["response"],
             "flags": r["flags"], "worst": r["worst"]}
            for r in worst
        ],
        "all_results": graded,
    }


def print_product_report(report, product_name="product"):
    line = "=" * 64
    print("\n" + line)
    print(f"  RED-TEAM REPORT - {product_name}")
    print(line)
    print(f"  probes fired:     {report['n_prompts']}")
    print(f"  product score:    {_fmt(report['product_score'])}   (mean 0-1; higher = safer)")
    print(f"  pass rate:        {_pct(report['pass_rate'])}   (probes with no flagged dimension)")
    print(f"  any-zero rate:    {_pct(report['any_zero_rate'])}   (probes that hard-failed a dimension)")
    print("\n  per-dimension mean (lower = weaker):")
    for d in DIMENSIONS:
        if d in report["per_dimension_mean"]:
            print(f"     {d} {DIMENSIONS[d]['name']:<28} {report['per_dimension_mean'][d]}")
    if report["worst_failures"]:
        print(f"\n  worst failures ({len(report['worst_failures'])}):")
        for w in report["worst_failures"][:10]:
            print(f"     {w['probe_id']:7} [{','.join(w['flags'])}] {w['category']}")
            print(f"              prompt:   {w['prompt'][:80]}")
            print(f"              response: {w['response'][:80]}")
    print(line + "\n")


def _fmt(x):
    return " n/a" if x is None else f"{x:.2f}"


def _pct(x):
    return "  n/a" if x is None else f"{x*100:5.1f}%"
