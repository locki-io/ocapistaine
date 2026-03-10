# front_chat.py
"""
OCapistaine — RAG Chat Interface

Minimal Streamlit UI for querying municipal documents and comparing electoral programs.
Uses session_id as Opik thread_id for conversation tracing.
User feedback (thumbs up/down) is sent to Opik for prompt optimization.

Run with:
    streamlit run app/front_chat.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import streamlit as st

st.set_page_config(
    page_title="Ò Capistaine — Les municipales à Audierne-Esquibien",
    page_icon="⚓",
    layout="centered",
)

# ── audierne2026.fr theme ─────────────────────────────────
# Colors from the "air" skin of audierne2026.fr
# Primary: #0092ca  |  Text: #222831  |  Links: #393e46  |  BG: #eeeeee
st.markdown(
    """
<style>
/* ── Global ─────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

section[data-testid="stSidebar"] {
    background-color: #f7f8f9;
    border-right: 1px solid #cecfd1;
}

/* ── Header banner ──────────────────────────────── */
.audierne-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: linear-gradient(135deg, #0092ca 0%, #007aab 100%);
    border-radius: 0.5rem;
    margin-bottom: 1rem;
    color: white;
}
.audierne-header img {
    height: 2.5rem;
    border-radius: 4px;
    background: white;
    padding: 2px;
}
.audierne-header .title {
    font-size: 1.25rem;
    font-weight: 600;
    letter-spacing: -0.01em;
}
.audierne-header .subtitle {
    font-size: 0.8rem;
    opacity: 0.85;
}

/* ── Primary color accents ──────────────────────── */
.stButton > button[kind="primary"],
.stButton > button:first-child {
    border-color: #0092ca;
    color: #0092ca;
}
.stButton > button[kind="primary"]:hover,
.stButton > button:first-child:hover {
    border-color: #007aab;
    color: #007aab;
    background-color: rgba(0, 146, 202, 0.08);
}

/* Chat input ring */
.stChatInput > div {
    border-color: #cecfd1 !important;
}
.stChatInput > div:focus-within {
    border-color: #0092ca !important;
    box-shadow: 0 0 0 1px #0092ca;
}

/* ── Chat messages ──────────────────────────────── */
[data-testid="stChatMessage"] {
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
}

/* ── Links ──────────────────────────────────────── */
a {
    color: #393e46;
}
a:hover {
    color: #0092ca;
}

/* ── Source expander ────────────────────────────── */
.streamlit-expanderHeader {
    font-size: 0.85rem;
    color: #393e46;
}

/* ── Info banner ────────────────────────────────── */
.stAlert > div[data-baseweb="notification"] {
    background-color: rgba(0, 146, 202, 0.08);
    border-left-color: #0092ca;
}

/* ── Sidebar title ──────────────────────────────── */
section[data-testid="stSidebar"] h1 {
    color: #222831;
}

/* ── Metrics ────────────────────────────────────── */
[data-testid="stMetricValue"] {
    color: #0092ca;
}

/* ── Selectbox focus ────────────────────────────── */
div[data-baseweb="select"] > div:focus-within {
    border-color: #0092ca !important;
}

/* ── Divider ────────────────────────────────────── */
hr {
    border-color: #cecfd1;
}

/* ── Footer ─────────────────────────────────────── */
.audierne-footer {
    text-align: center;
    padding: 1rem 0 0.5rem;
    font-size: 0.75rem;
    color: #9b9b9d;
    border-top: 1px solid #cecfd1;
    margin-top: 2rem;
}
.audierne-footer a {
    color: #0092ca;
    text-decoration: none;
}
</style>
""",
    unsafe_allow_html=True,
)

# Session ID = thread_id for Opik tracing
if "session_id" not in st.session_state:
    import uuid

    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "mode" not in st.session_state:
    st.session_state.mode = "chat"


# ── Feedback helper ───────────────────────────────────────


def _send_feedback(trace_id: str, score: float, msg_index: int):
    """Send user feedback to Opik and update message state."""
    if not trace_id:
        return

    try:
        from app.agents.tracing import get_tracer

        tracer = get_tracer()
        tracer.log_feedback(
            trace_id=trace_id,
            score=score,
            feedback_type="ocapistaine.user_rating",
            comment=f"{'positive' if score > 0.5 else 'negative'} feedback from chat UI",
        )
    except Exception:
        pass

    # Mark feedback as given in session state
    if 0 <= msg_index < len(st.session_state.messages):
        st.session_state.messages[msg_index]["feedback"] = score


# ── Suggestion engine ────────────────────────────────────

CATEGORY_LABELS_FR = {
    "economie": "Economie & commerce",
    "logement": "Logement & urbanisme",
    "culture": "Culture & patrimoine",
    "ecologie": "Ecologie & environnement",
    "associations": "Vie associative",
    "jeunesse": "Jeunesse & éducation",
    "alimentation-bien-etre-soins": "Santé & bien-être",
}

CATEGORY_ICONS = {
    "economie": "🏗️",
    "logement": "🏠",
    "culture": "🎭",
    "ecologie": "🌿",
    "associations": "🤝",
    "jeunesse": "📚",
    "alimentation-bien-etre-soins": "💊",
}

LIST_SHORT_NAMES = {
    "ca": "Construire l'Avenir",
    "paa": "Passons à l'Action",
    "spae": "S'unir pour Audierne-Esquibien",
    "csnf": "Cap sur Notre Futur",
}


def _build_suggestions(
    result_dict: dict, original_question: str, active_filter: str
) -> list[dict]:
    """
    Build follow-up suggestions based on the result context.

    Returns list of {"label": str, "query": str, "type": "category"|"list"|"followup"}

    Logic:
    - No category detected → suggest category chips
    - Category detected, no list filter → suggest list chips
    - Category + list → suggest template follow-ups
    """
    suggestions = []

    detected_cat = result_dict.get("detected_category")
    sources = result_dict.get("sources", [])
    source_lists = list({s.get("list_name", "") for s in sources if s.get("list_name")})
    refined_query = result_dict.get("refined_query") or original_question

    # ── No category → suggest thematic categories ───────
    if not detected_cat:
        for cat_key, cat_label in CATEGORY_LABELS_FR.items():
            icon = CATEGORY_ICONS.get(cat_key, "📌")
            suggestions.append(
                {
                    "label": f"{icon} {cat_label}",
                    "query": f"{original_question} — thème : {cat_label.lower()}",
                    "type": "category",
                    "filter_category": cat_key,
                }
            )
        return suggestions

    # ── Category detected, no list filter → suggest per-list deep dive ──
    if not active_filter:
        cat_label = CATEGORY_LABELS_FR.get(detected_cat, detected_cat)
        for list_key, list_name in LIST_SHORT_NAMES.items():
            suggestions.append(
                {
                    "label": f"📋 {list_name}",
                    "query": f"Que propose {list_name} sur {cat_label.lower()} ?",
                    "type": "list",
                    "filter_list": list_key,
                }
            )
        # Also suggest comparison mode
        suggestions.append(
            {
                "label": "⚖️ Comparer les programmes",
                "query": f"Comparer les programmes des listes sur {cat_label.lower()}",
                "type": "compare",
            }
        )
        return suggestions

    # ── Category + list filter → template follow-ups ────
    cat_label = CATEGORY_LABELS_FR.get(detected_cat, detected_cat)

    # "What about the other lists?"
    other_lists = [n for k, n in LIST_SHORT_NAMES.items() if k != active_filter]
    if other_lists:
        suggestions.append(
            {
                "label": f"📋 Et {other_lists[0]} ?",
                "query": f"Que propose {other_lists[0]} sur {cat_label.lower()} ?",
                "type": "followup",
                "filter_list": next(
                    k for k, n in LIST_SHORT_NAMES.items() if n == other_lists[0]
                ),
            }
        )

    # "More details"
    suggestions.append(
        {
            "label": "🔍 Plus de détails",
            "query": f"Plus de détails sur les propositions concernant {cat_label.lower()}",
            "type": "followup",
        }
    )

    # "Compare all lists"
    suggestions.append(
        {
            "label": "⚖️ Comparer les listes",
            "query": f"Comparer les programmes des listes sur {cat_label.lower()}",
            "type": "compare",
        }
    )

    return suggestions


# ── Sidebar ──────────────────────────────────────────────

LISTS = {
    "audierne2026": "Audierne-Esquibien 2026 (programme co-construit)",
    "ca": "Construire l'Avenir (LDVG – Florent Lardic)",
    "paa": "Passons à l'Action ! (LDVD – Didier Guillon)",
    "spae": "S'unir pour Audierne-Esquibien (LDVG – Michel Van Praët)",
    "csnf": "Cap sur Notre Futur (LDVD – Eric Bosser)",
}

# Electoral lists only (exclude co-constructed program from comparisons)
COMPARE_LISTS = {k: v for k, v in LISTS.items() if k != "audierne2026"}

with st.sidebar:
    st.markdown("### ⚓ Ò Capistaine")
    st.caption(f"Session: `{st.session_state.session_id[:8]}...`")

    # ── Fixed provider: Mistral medium (failover handles fallback) ──
    st.caption("🔵 Mistral AI")

    st.divider()

    # ── Mode selector ─────────────────────────────────────
    mode = st.radio("Mode", ["Chat", "Comparer les programmes"], index=0)
    st.session_state.mode = "compare" if "Comparer" in mode else "chat"

    if st.session_state.mode == "compare":
        selected_lists = st.multiselect(
            "Listes à comparer",
            options=list(COMPARE_LISTS.keys()),
            default=list(COMPARE_LISTS.keys()),
            format_func=lambda x: COMPARE_LISTS[x],
        )
    else:
        selected_lists = []

    filter_list = st.selectbox(
        "Filtrer par liste (optionnel)",
        options=[""] + list(LISTS.keys()),
        format_func=lambda x: "Toutes les sources" if x == "" else LISTS[x],
    )

    # RAG stats
    try:
        from app.rag.store import collection_stats

        stats = collection_stats()
        st.metric("Chunks indexés", stats["total_chunks"])
    except Exception:
        st.caption("RAG non initialisé")

    if st.button("Effacer la conversation"):
        st.session_state.messages = []
        import uuid

        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# ── Chat area ────────────────────────────────────────────

# Branded header with Audierne blason
_blason_path = (
    Path(__file__).resolve().parent.parent
    / "ext_data"
    / "audierne2026"
    / "assets"
    / "images"
    / "Blason_fr_Audierne.svg.png"
)
if _blason_path.exists():
    import base64

    _blason_b64 = base64.b64encode(_blason_path.read_bytes()).decode()
    st.markdown(
        f"""
    <div class="audierne-header">
        <img src="data:image/png;base64,{_blason_b64}" alt="Audierne">
        <div>
            <div class="title">Ò Capistaine</div>
            <div class="subtitle">Ensemble, écoutons et co-construisons — Audierne-Esquibien 2026</div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )
else:
    st.title("Ò Capistaine")

if st.session_state.mode == "compare":
    st.info("Comparons les programmes des listes ")
else:
    st.info(
        "Ici l'IA n'est pas une boite noire, c'est notre phare vers les élections municipales d'Audierne-Esquibien"
    )

# Display history with feedback buttons
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        if msg.get("sources"):
            with st.expander(f"Sources ({len(msg['sources'])})"):
                for s in msg["sources"]:
                    title = s.get("title") or s.get("doc_id", "")
                    list_name = s.get("list_name", "")
                    url = s.get("url", "")
                    name_label = f" — {list_name}" if list_name else ""
                    if url:
                        st.markdown(f"- [**{title}**]({url}){name_label}")
                    else:
                        st.markdown(f"- **{title}**{name_label}")

        # Feedback + suggestions for assistant messages
        if msg["role"] == "assistant":
            existing_feedback = msg.get("feedback")

            # Check if this is the last assistant message (for suggestions)
            is_last_assistant = i == max(
                j
                for j, m in enumerate(st.session_state.messages)
                if m["role"] == "assistant"
            )
            suggestions = msg.get("suggestions", []) if is_last_assistant else []

            # ── Row: [👍] [👎] [suggestion chips...] ──
            if existing_feedback is not None:
                if existing_feedback > 0.5:
                    st.caption("👍 Merci pour votre retour !")
                else:
                    st.caption("👎 Merci, nous allons améliorer.")
            else:
                # Feedback + suggestions on one line
                n_sug = min(len(suggestions), 4)  # max 4 chips on first row
                widths = (
                    [1, 1]
                    + [2] * n_sug
                    + ([max(1, 8 - 2 * n_sug)] if n_sug < 4 else [])
                )
                cols = st.columns(widths)

                with cols[0]:
                    if st.button("👍", key=f"up_{i}", help="Bonne réponse"):
                        _send_feedback(msg.get("trace_id"), 1.0, i)
                        st.rerun()
                with cols[1]:
                    if st.button("👎", key=f"down_{i}", help="Réponse à améliorer"):
                        _send_feedback(msg.get("trace_id"), 0.0, i)
                        st.rerun()

                for idx, sug in enumerate(suggestions[:n_sug]):
                    with cols[2 + idx]:
                        if st.button(
                            sug["label"],
                            key=f"sug_{i}_{idx}",
                            use_container_width=True,
                        ):
                            st.session_state["_pending_suggestion"] = sug
                            st.rerun()

            # Overflow suggestion rows (if more than 4)
            if suggestions and len(suggestions) > 4:
                for row_start in range(4, len(suggestions), 4):
                    row = suggestions[row_start : row_start + 4]
                    row_cols = st.columns(len(row))
                    for col, sug in zip(row_cols, row):
                        with col:
                            if st.button(
                                sug["label"],
                                key=f"sug_{i}_{row_start}_{sug['label'][:10]}",
                                use_container_width=True,
                            ):
                                st.session_state["_pending_suggestion"] = sug
                                st.rerun()

# Auto-scroll to bottom after rendering message history
if st.session_state.messages:
    import streamlit.components.v1 as components

    components.html(
        """
    <script>
        window.parent.document.querySelector('section.main').scrollTo({
            top: window.parent.document.querySelector('section.main').scrollHeight,
            behavior: 'smooth'
        });
    </script>
    """,
        height=0,
    )

# ── Streaming helpers ─────────────────────────────────────


def _collect_stream(async_gen):
    """
    Consume an async generator from sync Streamlit code.

    Yields text chunks for st.write_stream(), then stores the final
    result model (ChatResult/CompareResult) on the function attribute.
    """
    from app.agents.ocapistaine.models import ChatResult, CompareResult

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    _collect_stream.result = None

    try:
        ait = async_gen.__aiter__()
        while True:
            try:
                item = loop.run_until_complete(ait.__anext__())
                if isinstance(item, (ChatResult, CompareResult)):
                    _collect_stream.result = item
                else:
                    yield item
            except StopAsyncIteration:
                break
    finally:
        # Properly close the async generator before shutting down the loop
        try:
            loop.run_until_complete(ait.aclose())
        except Exception:
            pass
        loop.close()


# ── Input ─────────────────────────────────────────────────

# Handle suggestion click — inject as prompt
_pending = st.session_state.pop("_pending_suggestion", None)
if _pending:
    # Apply filter overrides from the suggestion
    if _pending.get("filter_list"):
        filter_list = _pending["filter_list"]
    if _pending.get("type") == "compare":
        st.session_state.mode = "compare"

prompt = _pending["query"] if _pending else st.chat_input("Votre question...")

if prompt:
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Build agent
    from app.agents.ocapistaine import OCapistaineAgent

    agent = OCapistaineAgent(
        provider_name="mistral",
        model_override="mistral-medium-latest",
    )

    # Build conversation history (last 6 turns = 3 exchanges)
    history = []
    for msg in st.session_state.messages[:-1]:  # exclude current user msg
        if msg["role"] in ("user", "assistant"):
            history.append({"role": msg["role"], "content": msg["content"]})
    history = history[-6:]  # keep last 3 exchanges max

    # Generate streamed response
    with st.chat_message("assistant"):
        with st.status("Recherche dans les documents...", expanded=False) as status:
            # Prepare the async stream
            if st.session_state.mode == "compare" and selected_lists:
                stream = agent.stream_compare(
                    question=prompt,
                    list_names=selected_lists,
                    thread_id=st.session_state.session_id,
                    history=history if history else None,
                )
            else:
                filters = {"list_name": filter_list} if filter_list else None
                stream = agent.stream_chat(
                    question=prompt,
                    filters=filters,
                    thread_id=st.session_state.session_id,
                    history=history if history else None,
                )
            status.update(label="Synthèse en cours...", state="running")

        # Stream LLM output token by token
        st.write_stream(_collect_stream(stream))
        result = _collect_stream.result

        if result:
            result = result.to_dict()

            sources = result.get("sources", [])
            if sources:
                with st.expander(f"Sources ({len(sources)})"):
                    for s in sources:
                        title = s.get("title") or s.get("doc_id", "")
                        list_name = s.get("list_name", "")
                        url = s.get("url", "")
                        name_label = f" — {list_name}" if list_name else ""
                        if url:
                            st.markdown(f"- [**{title}**]({url}){name_label}")
                        else:
                            st.markdown(f"- **{title}**{name_label}")

            # Show trace info
            model = result.get("model", "")
            confidence = result.get("confidence")
            trace_id = result.get("trace_id")
            meta_parts = [f"Modèle: {model}"]
            if confidence is not None:
                meta_parts.append(f"Confiance: {confidence:.1%}")
            if trace_id:
                meta_parts.append(f"Trace: `{trace_id[:8]}...`")
            st.caption(" | ".join(meta_parts))

            # Build suggestions for follow-up
            active_list_filter = filter_list if filter_list else ""
            suggestions = _build_suggestions(result, prompt, active_list_filter)

            # Save assistant message
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": result["response"],
                    "sources": sources,
                    "trace_id": trace_id,
                    "feedback": None,
                    "suggestions": suggestions,
                    "detected_category": result.get("detected_category"),
                }
            )
        else:
            st.error("Aucune réponse reçue.")
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": "Erreur : aucune réponse reçue.",
                    "sources": [],
                    "trace_id": None,
                    "feedback": None,
                }
            )

    # Rerun so the history loop renders feedback buttons immediately
    st.rerun()

# ── Footer ───────────────────────────────────────────────
st.markdown(
    """
<div class="audierne-footer">
    <a href="https://audierne2026.fr" target="_blank">audierne2026.fr</a>
    &nbsp;·&nbsp; Participons — Audierne-Esquibien 2026
</div>
""",
    unsafe_allow_html=True,
)
