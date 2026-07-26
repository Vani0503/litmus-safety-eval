# Litmus — AI Safety & Ethics Evaluation Harness

An LLM-as-judge that scores an AI product's responses on 9 safety & ethics
dimensions against a fixed rubric — and, crucially, **validates the judge itself**
against a 40-case golden set before you trust a single score.

This is the P1 (grader) + P2 (judge validation) build. The red-team suite (P3)
plugs into the same grader later.

## What's here

```
litmus/
  rubric.py          # 9 dimensions, 0-3 anchors, D2 = pass/fail rule
  golden_set.json    # 40 hand-labeled validation cases
  judge.py           # per-dimension LLM judge: OpenAI + Anthropic + mock backends
  metrics.py         # Cohen's kappa, detection rate, false-positive rate (pure python)
  validate.py        # runs the golden set through two judges, builds the report
run_validation.py    # CLI entry point
```

## The core design decisions (all enforced in code)

1. **Per-dimension scoring.** The judge is called once per dimension, not once for
   all nine — batching bleeds context and inflates scores. See `judge.build_messages`.
2. **Evidence required.** Every score must quote the span of the response that
   justifies it, or the judge returns `N/A`. No span, no score.
3. **D2 (Bias) is pass/fail.** Only 0 or 3 are legal on that dimension; the prompt
   says so and `parse_judgement` re-checks. Every other dimension uses the full 0–3.
4. **Judge ≠ Target.** If the judge shares a model family with the product under
   test, validation refuses to run (override with `allow_same=True`). A model is a
   poor auditor of its own blind spots.
5. **N runs for consistency.** Each dimension is scored N times; run-to-run
   agreement is reported alongside the score, never hidden.

## Run it offline first (no keys — proves the pipeline; numbers are SYNTHETIC)

```bash
pip install --break-system-packages openai anthropic   # only needed for real runs
python run_validation.py --mock
```

The `--mock` judges are a crude keyword matcher. They exist only to show the
pipeline runs and the metrics compute. **Their numbers are fake — do not use them
anywhere, especially not in a post.**

## Run it for real (these are the numbers for the post)

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
python run_validation.py --runs 3 --json report.json
```

- **Primary judge:** GPT-4o. **Second judge:** Claude (for inter-judge agreement).
- The products in the golden set are Claude-based, so GPT-4o-as-judge satisfies
  Judge ≠ Target. (If you ever judge a GPT-based product, flip the judges.)

## What the report tells you

- **Detection rate** — of the 19 known-failure cases (expected ≤ 1), how many did
  the judge flag? This is "does the tester catch real problems?"
- **False-positive rate** — of the 14 known-good cases (expected 3), how many did
  it wrongly flag? This is "does it cry wolf?"
- **Exact-match / within-one** — how close the judge's score is to the human label.
- **Inter-judge kappa** (overall + per dimension) — where GPT-4o and Claude
  *disagree* on the right score. The hypothesis: high agreement on D2 (binary) and
  the clear 0s; more disagreement on the 2-vs-3 borderline calls. That disagreement
  map is the interesting finding.

## Honest limitations (worth stating in the post)

- The judge is an LLM, so it inherits LLM weaknesses. That's *why* validation
  exists — you measure the judge instead of trusting it.
- 40 cases is enough to see the shape, not enough for tight confidence intervals.
- The golden labels encode one person's judgment calls (yours). The rubric anchors
  make them defensible, but they are still calls — the borderlines especially.
- For the most dangerous categories (CSAM, weapon/bio synthesis), Litmus does not
  generate adversarial prompts and defers to specialized classifiers; it only
  checks that the target refuses and routes appropriately.

---

# Red-Team Suite (P3) — testing YOUR live products

The grader above scores canned examples. The red-team suite fires an adversarial
prompt library at a *live* product, collects the real responses, and scores them
with the same grader. This is how you get "I turned Litmus on my own chatbot."

## Safety boundary (built in)
The prompt library (`litmus/redteam_prompts.py`) contains only benign-surface
probes that reveal vulnerabilities (fake-profile asks, caste-inference jailbreaks,
consent traps, empty-retrieval baits). It deliberately generates **no** CSAM or
weapon/bio-synthesis prompts; for self-harm it uses a disclosure that tests only
whether the product recognizes risk and routes to help.

## Offline demo (canned responses, proves the flow)
```bash
python run_redteam.py --target mock --scope all
```

## Real run against your product
Pick the adapter that matches how your product is reachable:

```bash
export OPENAI_API_KEY=sk-...          # for the GPT-4o judge (Judge != Target)

# A) product has an HTTP endpoint:
python run_redteam.py --scope wellness --target http \
    --url https://your-bot/api --target-family claude --json wellness_report.json

# B) product speaks OpenAI chat format:
python run_redteam.py --scope agent --target openai \
    --url https://your-endpoint/v1 --target-family gpt

# C) product has NO API — paste responses by hand:
python run_redteam.py --scope wellness --export prompts.json   # step 1: get prompts
#   ...run each prompt through your product, paste answers into prompts.json...
python run_redteam.py --scope wellness --target manual --responses prompts.json  # step 2
```

For a local product (e.g. your mini-GPT), wrap its generate function in Python:
```python
from litmus.target import CallableTarget
from litmus.judge import OpenAIJudge
from litmus.redteam import run_redteam, print_product_report

target = CallableTarget(lambda p: my_minigpt_generate(p), model_family="other")
report = run_redteam(target, OpenAIJudge(runs=1), scope="mini_gpt")
print_product_report(report, "mini-GPT")
```

## Scopes
`--scope wellness | agent | mini_gpt | all` picks which probes run (domain-relevant
ones for your RAG chatbot vs. consent/action ones for your agent).

## Cost note
Each probe is scored on its targeted dimensions × `--runs`. Use `--runs 1` to keep
a live run cheap; add `--all-dims` only when you want every response scored on all 9.
