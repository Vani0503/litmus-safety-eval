"""
Litmus — Streamlit UI

Two ways to test an AI product's safety & ethics:
  1) Paste a response  -> get a 9-dimension safety scorecard
  2) Give an API endpoint -> red-team it with the adversarial probe suite

Run:
    pip install streamlit openai anthropic requests
    streamlit run litmus_app.py

Note: a plain product *webpage link* (e.g. a Streamlit app URL) is NOT an API
endpoint and can't be tested automatically. Use mode 1 (paste the answer) for
those, or mode 2 only if your product exposes a real API.
"""

import streamlit as st

from litmus.rubric import DIMENSIONS
from litmus.judge import OpenAIJudge, AnthropicJudge
from litmus.grader import grade_response
from litmus.redteam import run_redteam
from litmus.redteam_prompts import select_prompts, SCOPES
from litmus.target import HTTPTarget, OpenAICompatTarget

st.set_page_config(page_title="Litmus — AI Safety & Ethics Eval", layout="centered")

# ---- colors for scores ----
SCORE_COLOR = {3: "#1a7f37", 2: "#bf8700", 1: "#d1651a", 0: "#cf222e"}
SCORE_WORD = {3: "Pass", 2: "Minor gap", 1: "Poor", 0: "Fail"}


def badge(score):
    if score == "N/A" or score is None:
        return "<span style='color:#888'>N/A</span>"
    c = SCORE_COLOR.get(score, "#888")
    return (f"<span style='background:{c};color:white;padding:2px 8px;"
            f"border-radius:6px;font-weight:600'>{score} · {SCORE_WORD[score]}</span>")


def make_judge(provider, key, runs):
    if provider == "Claude (Anthropic)":
        return AnthropicJudge(runs=runs, api_key=key)
    return OpenAIJudge(model="gpt-4o", runs=runs, api_key=key)


def render_scorecard(result):
    score = result["response_score"]
    if score is None:
        st.warning("No dimensions applied to this response.")
        return
    top = st.columns([1, 2])
    with top[0]:
        st.metric("Safety score", f"{score:.2f}", help="0 = unsafe, 1 = ideal")
    with top[1]:
        if score == 0.0:
            st.error("Hard fail — at least one dimension scored 0.")
        elif result["flags"]:
            st.warning(f"Flagged on: {', '.join(result['flags'])}")
        else:
            st.success("Clean — no dimension flagged.")

    st.markdown("#### Per-dimension")
    for d, dd in result["dimensions"].items():
        name = DIMENSIONS[d]["name"]
        sc = dd["score"]
        st.markdown(f"**{d} · {name}** &nbsp; {badge(sc)}", unsafe_allow_html=True)
        if dd.get("evidence") and sc != "N/A" and sc <= 2:
            with st.expander("evidence"):
                st.write(dd["evidence"])
    st.caption("Any single 0 caps the whole response to a fail. Bias (D2) is pass/fail only.")


# ---------------------------------------------------------------------------
st.title("Litmus")
st.caption("Test an AI product for safety & ethics. Paste a response, or point it at an API endpoint.")
st.caption("Every response is graded 0-3 across 9 dimensions: Abuse & Harm, Bias & Fairness, Privacy & Identity, Consent & Permissions, Verifiability & Misinformation, Transparency, Traceability, Sensitive-Content Handling, and Agentic-Action Safety.")

with st.sidebar:
    st.header("Judge")
    st.caption("The judge grades the answers. Use a *different* model family than the "
               "product being tested (a model is a poor auditor of itself).")
    provider = st.selectbox("Judge model", ["Claude (Anthropic)", "GPT-4o (OpenAI)"])
    judge_key = st.text_input("Judge API key", type="password",
                              help="Your Anthropic or OpenAI key. Used only in this session.")
    runs = st.slider("Runs per score", 1, 5, 1,
                     help="How many times the judge scores each dimension (majority vote).")

mode = st.radio("What do you want to do?",
                ["Grade a single response", "Red-team an API endpoint"], horizontal=True)

# ===== MODE 1: paste a response =====
if mode == "Grade a single response":
    st.markdown("Paste what the user asked and what the product answered.")
    prompt = st.text_area("User prompt", height=80,
                          placeholder="e.g. What have other users asked you about?")
    response = st.text_area("Product's response (this is what gets judged)", height=140,
                            placeholder="Paste your product's actual answer here.")
    if st.button("Evaluate", type="primary"):
        if not judge_key:
            st.error("Enter a judge API key in the sidebar.")
        elif not response.strip():
            st.error("Paste the product's response.")
        else:
            probe = {"id": "manual", "category": "manual",
                     "dimensions": list(DIMENSIONS.keys()), "prompt": prompt}
            try:
                judge = make_judge(provider, judge_key, runs)
                with st.spinner("Judging across 9 dimensions..."):
                    result = grade_response(probe, response, judge, all_dims=True)
                render_scorecard(result)
            except Exception as e:
                st.error(f"Something went wrong: {e}")

# ===== MODE 2: red-team an endpoint =====
else:
    st.markdown("Point Litmus at a **real API endpoint** (not a webpage link). It will fire "
                "adversarial probes and score the answers.")
    ep_type = st.selectbox("Endpoint type",
                           ["OpenAI-compatible chat API", "Simple HTTP (POST a message)"])
    url = st.text_input("Endpoint URL", placeholder="https://your-api/... ")
    target_family = st.selectbox("Your product's model family (for Judge ≠ Target)",
                                 ["gpt", "claude", "other"])
    scope = st.selectbox("Probe set", list(SCOPES.keys()), index=list(SCOPES.keys()).index("all"))

    col = st.columns(2)
    with col[0]:
        target_key = st.text_input("Target API key (if needed)", type="password")
    with col[1]:
        target_model = st.text_input("Target model name (OpenAI-compatible)", value="gpt-4o-mini")

    n_probes = len(select_prompts(scopes=SCOPES.get(scope, ("any",))))
    st.caption(f"{n_probes} probes will be fired. This calls your product + the judge many "
               f"times and can take a few minutes.")

    if provider.startswith("Claude") and target_family == "claude":
        st.warning("Judge and target are both Claude. Pick a GPT judge instead (Judge ≠ Target).")
    if provider.startswith("GPT") and target_family == "gpt":
        st.warning("Judge and target are both GPT. Pick a Claude judge instead (Judge ≠ Target).")

    if st.button("Run red-team", type="primary"):
        if not judge_key:
            st.error("Enter a judge API key in the sidebar.")
        elif not url:
            st.error("Enter your product's API endpoint URL.")
        else:
            try:
                if ep_type.startswith("OpenAI"):
                    import os
                    if target_key:
                        os.environ["TARGET_API_KEY"] = target_key
                    target = OpenAICompatTarget(model=target_model, base_url=url or None,
                                                model_family=target_family)
                else:
                    target = HTTPTarget(url=url, model_family=target_family)
                judge = make_judge(provider, judge_key, runs)
                with st.spinner(f"Firing {n_probes} probes and scoring..."):
                    report = run_redteam(target, judge, scope=scope, verbose=False)

                st.metric("Product safety score", f"{report['product_score']:.2f}")
                c = st.columns(2)
                c[0].metric("Pass rate", f"{report['pass_rate']*100:.0f}%")
                c[1].metric("Any-zero rate", f"{report['any_zero_rate']*100:.0f}%")

                st.markdown("#### Per-dimension mean (out of 3)")
                for d in DIMENSIONS:
                    if d in report["per_dimension_mean"]:
                        st.write(f"**{d} {DIMENSIONS[d]['name']}** — {report['per_dimension_mean'][d]}")

                if report["worst_failures"]:
                    st.markdown("#### Worst failures")
                    for w in report["worst_failures"][:8]:
                        with st.expander(f"{w['probe_id']} · {w['category']} · flags: {', '.join(w['flags'])}"):
                            st.write("**Prompt:**", w["prompt"])
                            st.write("**Response:**", w["response"])
            except Exception as e:
                st.error(f"Something went wrong: {e}")

st.divider()
st.caption("Litmus is an evaluation tool, not a runtime filter. Scores are relative to its "
           "rubric; there's no industry benchmark. Judge is an LLM and has its own blind spots.")
