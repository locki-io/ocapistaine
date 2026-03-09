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
st.markdown("""
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
""", unsafe_allow_html=True)

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


# ── Sidebar ──────────────────────────────────────────────

LISTS = {
    "audierne2026": "Audierne-Esquibien 2026 (programme co-construit)",
    "ca": "Construire l'Avenir (LDVG – Florent Lardic)",
    "paa": "Passons à l'Action ! (LDVD – Didier Guillon)",
    "spae": "S'unir pour Audierne-Esquibien (LDVG – Michel Van Praët)",
    "csnf": "Cap sur Notre Futur (LDVD – Eric Bosser)",
}

with st.sidebar:
    st.markdown("### ⚓ Ò Capistaine")
    st.caption(f"Session: `{st.session_state.session_id[:8]}...`")

    # ── Provider / Model selector ─────────────────────────
    from app.providers.config import PROVIDER_UI_CONFIG, get_model_id

    # Check which providers are actually available
    available_providers = []
    try:
        from app.providers.health import get_provider_status

        health = get_provider_status()
        if health:
            if health["ollama"].get("status") == "available":
                available_providers.append("ollama")
            for name in ["openai", "claude", "mistral", "gemini"]:
                if health["cloud"].get(name, {}).get("configured"):
                    available_providers.append(name)
    except Exception:
        pass

    # Fallback: show all if health check unavailable
    if not available_providers:
        available_providers = list(PROVIDER_UI_CONFIG.keys())

    provider_labels = {
        "ollama": "🖥️ Ollama (local)",
        "openai": "🟢 OpenAI",
        "claude": "🟣 Claude",
        "mistral": "🔵 Mistral",
        "gemini": "🔴 Gemini",
    }

    selected_provider = st.selectbox(
        "Fournisseur LLM",
        options=available_providers,
        format_func=lambda x: provider_labels.get(x, x),
    )

    # Model selector for chosen provider
    provider_models = PROVIDER_UI_CONFIG.get(selected_provider, {}).get("models", {})
    default_model = PROVIDER_UI_CONFIG.get(selected_provider, {}).get("default", "")
    default_idx = (
        list(provider_models.keys()).index(default_model)
        if default_model in provider_models
        else 0
    )

    selected_model_key = st.selectbox(
        "Modèle",
        options=list(provider_models.keys()),
        index=default_idx,
        format_func=lambda x: provider_models.get(x, x),
    )

    st.divider()

    # ── Mode selector ─────────────────────────────────────
    mode = st.radio("Mode", ["Chat", "Comparer les programmes"], index=0)
    st.session_state.mode = "compare" if "Comparer" in mode else "chat"

    if st.session_state.mode == "compare":
        selected_lists = st.multiselect(
            "Listes à comparer",
            options=list(LISTS.keys()),
            default=list(LISTS.keys()),
            format_func=lambda x: LISTS[x],
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
_blason_path = Path(__file__).resolve().parent.parent / "ext_data" / "audierne2026" / "assets" / "images" / "Blason_fr_Audierne.svg.png"
if _blason_path.exists():
    import base64
    _blason_b64 = base64.b64encode(_blason_path.read_bytes()).decode()
    st.markdown(f"""
    <div class="audierne-header">
        <img src="data:image/png;base64,{_blason_b64}" alt="Audierne">
        <div>
            <div class="title">Ò Capistaine</div>
            <div class="subtitle">Ensemble, écoutons et co-construisons — Audierne-Esquibien 2026</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.title("Ò Capistaine")

if st.session_state.mode == "compare":
    st.info(
        "Mode comparaison : posez une question pour comparer les programmes des listes sélectionnées."
    )
else:
    st.info("En savoir plus sur les municipales d'Audierne-Esquibien.")

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

        # Feedback buttons for all assistant messages
        if msg["role"] == "assistant":
            existing_feedback = msg.get("feedback")

            if existing_feedback is not None:
                # Already rated — show static indicator
                if existing_feedback > 0.5:
                    st.caption("👍 Merci pour votre retour !")
                else:
                    st.caption("👎 Merci, nous allons améliorer.")
            else:
                # Not yet rated — show interactive buttons
                col1, col2, col3 = st.columns([1, 1, 10])
                with col1:
                    if st.button("👍", key=f"up_{i}", help="Bonne réponse"):
                        _send_feedback(msg.get("trace_id"), 1.0, i)
                        st.rerun()
                with col2:
                    if st.button("👎", key=f"down_{i}", help="Réponse à améliorer"):
                        _send_feedback(msg.get("trace_id"), 0.0, i)
                        st.rerun()

# Auto-scroll to bottom after rendering message history
if st.session_state.messages:
    import streamlit.components.v1 as components
    components.html("""
    <script>
        window.parent.document.querySelector('section.main').scrollTo({
            top: window.parent.document.querySelector('section.main').scrollHeight,
            behavior: 'smooth'
        });
    </script>
    """, height=0)

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
        loop.run_until_complete(ait.aclose())
        loop.close()


# ── Input ─────────────────────────────────────────────────

if prompt := st.chat_input("Votre question..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Build agent
    from app.agents.ocapistaine import OCapistaineAgent
    from app.providers.config import get_model_id

    model_id = get_model_id(selected_provider, selected_model_key)
    agent = OCapistaineAgent(
        provider_name=selected_provider,
        model_override=model_id,
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

            # Save assistant message
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": result["response"],
                    "sources": sources,
                    "trace_id": trace_id,
                    "feedback": None,
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
st.markdown("""
<div class="audierne-footer">
    <a href="https://audierne2026.fr" target="_blank">audierne2026.fr</a>
    &nbsp;·&nbsp; Participons — Audierne-Esquibien 2026
</div>
""", unsafe_allow_html=True)
