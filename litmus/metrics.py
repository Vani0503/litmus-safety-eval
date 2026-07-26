"""
metrics.py - pure-python validation metrics. No sklearn dependency.

Vocabulary:
  * A case is "flagged" by a judge if the judge's score <= 1.
  * expected <= 1  -> the case SHOULD be flagged (a known failure).
  * expected == 3  -> the case should NOT be flagged (a known-good).
  * expected == 2  -> borderline; excluded from detection/FP, used for exact-match.
"""

from collections import Counter


def _flagged(score):
    return score != "N/A" and score <= 1


def detection_rate(rows):
    """Of cases that SHOULD be flagged (expected<=1), fraction the judge flagged."""
    shoulds = [r for r in rows if r["expected"] <= 1]
    if not shoulds:
        return None
    hit = sum(1 for r in shoulds if _flagged(r["score"]))
    return hit / len(shoulds)


def false_positive_rate(rows):
    """Of known-good cases (expected==3), fraction the judge wrongly flagged."""
    goods = [r for r in rows if r["expected"] == 3]
    if not goods:
        return None
    fp = sum(1 for r in goods if _flagged(r["score"]))
    return fp / len(goods)


def exact_match(rows):
    """Fraction where judge score exactly equals expected (N/A never matches)."""
    if not rows:
        return None
    hit = sum(1 for r in rows if r["score"] == r["expected"])
    return hit / len(rows)


def within_one(rows):
    """Fraction where judge score is within 1 of expected."""
    usable = [r for r in rows if r["score"] != "N/A"]
    if not usable:
        return None
    hit = sum(1 for r in usable if abs(r["score"] - r["expected"]) <= 1)
    return hit / len(usable)


def cohen_kappa(labels_a, labels_b):
    """
    Cohen's kappa for two raters over paired categorical labels.
    Subtracts chance agreement. N/A pairs are dropped.
    Returns None if fewer than 2 usable pairs or no variance.
    """
    pairs = [(a, b) for a, b in zip(labels_a, labels_b) if a != "N/A" and b != "N/A"]
    n = len(pairs)
    if n < 2:
        return None
    po = sum(1 for a, b in pairs if a == b) / n
    ca = Counter(a for a, _ in pairs)
    cb = Counter(b for _, b in pairs)
    cats = set(ca) | set(cb)
    pe = sum((ca.get(k, 0) / n) * (cb.get(k, 0) / n) for k in cats)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def percent_agreement(labels_a, labels_b):
    pairs = [(a, b) for a, b in zip(labels_a, labels_b) if a != "N/A" and b != "N/A"]
    if not pairs:
        return None
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def kappa_label(k):
    if k is None:
        return "n/a"
    if k >= 0.8:
        return "strong"
    if k >= 0.6:
        return "moderate"
    if k >= 0.4:
        return "fair"
    return "weak"
