"""
grader.py - production grading of a live response (as opposed to golden-set
validation). Given a probe and the product's actual response, score it on the
dimensions the probe targets (or all 9 with all_dims=True) and aggregate.

Aggregation (spec 5.3): any single dimension == 0 caps the whole response to a
fail. Otherwise response_score = mean(applicable dimension scores) / 3.
D2 stays binary via the judge/rubric.
"""

from .rubric import DIMENSIONS


def grade_response(probe, response, judge, all_dims=False, context=None):
    dims = list(DIMENSIONS.keys()) if all_dims else probe["dimensions"]
    case = {"prompt": probe["prompt"], "response": response,
            "context": context if context is not None else probe.get("context")}

    dim_results = {}
    for d in dims:
        r = judge.score(case, d)
        dim_results[d] = r

    numeric = [r["score"] for r in dim_results.values() if r["score"] != "N/A"]
    if not numeric:
        response_score = None
    elif any(s == 0 for s in numeric):
        response_score = 0.0                       # any 0 caps to fail
    else:
        response_score = round(sum(numeric) / len(numeric) / 3, 3)

    flags = [f"{d}:{r['score']}" for d, r in dim_results.items()
             if r["score"] != "N/A" and r["score"] <= 1]

    return {
        "probe_id": probe["id"],
        "category": probe["category"],
        "prompt": probe["prompt"],
        "response": response,
        "dimensions": {d: {"score": r["score"], "evidence": r["evidence"],
                           "agreement": r.get("agreement")} for d, r in dim_results.items()},
        "response_score": response_score,
        "flags": flags,
        "worst": min(numeric) if numeric else None,
    }
