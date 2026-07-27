import streamlit as st
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from rank_bm25 import BM25Okapi
import numpy as np
import os

@st.cache_resource
def load_resources():
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vector_store = FAISS.load_local(
        "faiss_index", embeddings,
        allow_dangerous_deserialization=True
    )
    docs = list(vector_store.docstore._dict.values())
    tokenized = [doc.page_content.lower().split() for doc in docs]
    bm25 = BM25Okapi(tokenized)
    return vector_store, bm25, docs

vector_store, bm25, all_docs = load_resources()
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

def rewrite_query(query, history_text):
    if not history_text:
        return query
    recent_history = "\n".join(history_text.split("\n")[-4:])
    rewrite_prompt = f"""Given this recent conversation:
{recent_history}

Rewrite this question as a complete standalone question.
If it already makes complete sense on its own, return it unchanged.

Question: "{query}"

Return only the rewritten question, nothing else."""
    return llm.invoke(rewrite_prompt).content.strip()

def hybrid_search(query, k=3, semantic_weight=0.7):
    semantic_results = vector_store.similarity_search_with_score(query, k=k)
    tokenized_query = query.lower().split()
    bm25_scores = bm25.get_scores(tokenized_query)
    top_bm25_indices = np.argsort(bm25_scores)[::-1][:k]
    combined = {}
    for doc, score in semantic_results:
        key = doc.page_content[:50]
        combined[key] = {
            "doc": doc,
            "score": semantic_weight * (1 / (1 + score))
        }
    for idx in top_bm25_indices:
        doc = all_docs[idx]
        key = doc.page_content[:50]
        bm25_score = (1 - semantic_weight) * (bm25_scores[idx] / (bm25_scores.max() + 1e-9))
        if key in combined:
            combined[key]["score"] += bm25_score
        else:
            combined[key] = {"doc": doc, "score": bm25_score}
    results = sorted(combined.values(), key=lambda x: x["score"], reverse=True)
    return results[:k]

def get_confidence_label(score):
    if score > 0.7:
        return "🟢 High confidence"
    elif score > 0.4:
        return "🟡 Medium confidence"
    else:
        return "🔴 Low confidence — answer may be incomplete"

# ── Session state ──────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "suggested_query" not in st.session_state:
    st.session_state.suggested_query = None

# ── Title and onboarding ───────────────────────────────────
st.title("🧠 Advanced RAG Chatbot on Human Chakras")

st.markdown("""
**This chatbot answers questions from a private knowledge base covering:**
- 🧘 Human Chakras & Energy Centers
- 🌬️ Breathing Techniques & Relaxation
- 👨‍👩‍👧 Family Systems & Dysfunctional Families
- 🧠 Hypnotherapy & Behavioral Resolutions
- ❤️ Emotional Health & Anxiety

**Try asking:**
""")

col1, col2 = st.columns(2)
with col1:
    if st.button("🧘 What is the heart chakra?"):
        st.session_state.suggested_query = "What is the heart chakra?"
    if st.button("🌬️ Breathing techniques for relaxation?"):
        st.session_state.suggested_query = "What are breathing techniques for relaxation?"
    if st.button("👨‍👩‍👧 Traits of a dysfunctional family?"):
        st.session_state.suggested_query = "What are traits of a dysfunctional family?"
with col2:
    if st.button("🧠 What is corrective therapy?"):
        st.session_state.suggested_query = "What is corrective therapy?"
    if st.button("❤️ What are the two forms of anxiety?"):
        st.session_state.suggested_query = "What are the two forms of anxiety?"
    if st.button("✨ What is the law of repetition?"):
        st.session_state.suggested_query = "What is the law of repetition?"

st.divider()

# ── Chat history display ───────────────────────────────────
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ── Query handling ─────────────────────────────────────────
typed_query = st.chat_input("Or type your own question...")

query = None
if typed_query:
    query = typed_query
elif st.session_state.suggested_query:
    query = st.session_state.suggested_query
    st.session_state.suggested_query = None

if query:
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    history_text = ""
    for m in st.session_state.messages[:-1]:
        role = "User" if m["role"] == "user" else "Assistant"
        history_text += f"{role}: {m['content']}\n"

    search_query = rewrite_query(query, history_text)
    results = hybrid_search(search_query, k=3)
    filtered = [r for r in results if r["score"] > 0.3]
    if not filtered:
        filtered = results[:2]

    context = "\n\n".join([r["doc"].page_content for r in filtered])
    sources = list(set([r["doc"].metadata.get("source", "Unknown") for r in filtered]))
    top_score = filtered[0]["score"] if filtered else 0
    confidence = get_confidence_label(top_score)

    final_prompt = f"""You are a helpful assistant. Use the context below to answer the question.
If the answer is not in the context, say you don't know.

Previous conversation:
{history_text}

Context:
{context}

Question: {query}
"""
    response = llm.invoke(final_prompt)
    answer = response.content

    st.session_state.messages.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)
        st.caption(confidence)
        with st.expander("📄 Sources"):
            for source in sources:
                st.write("-", source)

# ── Sidebar ────────────────────────────────────────────────
if st.sidebar.button("🗑️ Clear Chat"):
    st.session_state.messages = []
    st.rerun()
