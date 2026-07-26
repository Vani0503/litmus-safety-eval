"""
Red-team YOUR wellness RAG chatbot (from app.py) with Litmus.

Setup:
  - put this file in the SAME folder as app.py and the `litmus/` package folder
  - your app.py must be importable WITHOUT launching Streamlit (see note below)

Run:
  export OPENAI_API_KEY=sk-...        # your product uses this (embeddings + gpt-4o-mini)
  export ANTHROPIC_API_KEY=sk-ant-... # the JUDGE uses this (Claude judges your GPT product)
  python3 redteam_wellness.py
"""

import os
from litmus.target import CallableTarget
from litmus.judge import AnthropicJudge
from litmus.redteam import run_redteam, print_product_report

# --- 1. Import your product's pipeline from app.py -------------------------
# We reuse your exact functions. This works only if importing app.py does not
# immediately run the Streamlit UI code. If it errors, see the note at the bottom.
import app  # your app.py

def answer_question(query: str) -> str:
    """One-shot version of your chatbot: same retrieval + same final prompt, no UI, no history."""
    search_query = app.rewrite_query(query, "")          # no conversation history in a probe
    results = app.hybrid_search(search_query, k=3)
    filtered = [r for r in results if r["score"] > 0.3] or results[:2]
    context = "\n\n".join(r["doc"].page_content for r in filtered)

    final_prompt = f"""You are a helpful assistant. Use the context below to answer the question.
If the answer is not in the context, say you don't know.

Previous conversation:


Context:
{context}

Question: {query}
"""
    return app.llm.invoke(final_prompt).content


# --- 2. Point Litmus at it -------------------------------------------------
# model_family="gpt" because your chatbot generates with gpt-4o-mini.
# The judge is Claude, so Judge != Target holds.
target = CallableTarget(answer_question, model_family="gpt")
judge = AnthropicJudge(runs=3)   # use runs=1 to spend less

report = run_redteam(target, judge, scope="all", verbose=True)
print_product_report(report, product_name="Wellness RAG Chatbot")

import json
with open("wellness_report.json", "w") as f:
    slim = dict(report); slim.pop("all_results", None)
    json.dump(slim, f, indent=2)
print("Saved -> wellness_report.json")
