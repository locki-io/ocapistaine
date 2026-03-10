# front_chat.py
"""
OCapistaine — RAG Chat Interface

Minimal Streamlit UI for querying municipal documents and comparing electoral programs.
Uses session_id as Opik thread_id for conversation tracing.
User feedback (thumbs up/down) is sent to Opik for prompt optimization.
UI components from app.ui (Niove's domain).

Run with:
    streamlit run app/front_chat.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import uuid
import streamlit as st

st.set_page_config(
    page_title="Ò Capistaine — Les municipales à Audierne-Esquibien",
    page_icon="⚓",
    layout="centered",
)

# ── UI components from app.ui ─────────────────────────────
from app.ui import apply_theme, render_header, render_footer, init_chat_float

apply_theme(hide_sidebar=True)
init_chat_float()

# ── Session state ─────────────────────────────────────────
if "session_id" not in st.session_state:
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
    - No category detected -> suggest category chips
    - Category detected, no list filter -> suggest list chips
    - Category + list -> suggest template follow-ups
    """
    suggestions = []

    detected_cat = result_dict.get("detected_category")
    sources = result_dict.get("sources", [])
    source_lists = list({s.get("list_name", "") for s in sources if s.get("list_name")})
    refined_query = result_dict.get("refined_query") or original_question

    # No category -> suggest thematic categories
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

    # Category detected, no list filter -> suggest per-list deep dive
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
        suggestions.append(
            {
                "label": "⚖️ Comparer les programmes",
                "query": f"Comparer les programmes des listes sur {cat_label.lower()}",
                "type": "compare",
            }
        )
        return suggestions

    # Category + list filter -> template follow-ups
    cat_label = CATEGORY_LABELS_FR.get(detected_cat, detected_cat)

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

    suggestions.append(
        {
            "label": "🔍 Plus de détails",
            "query": f"Plus de détails sur les propositions concernant {cat_label.lower()}",
            "type": "followup",
        }
    )

    suggestions.append(
        {
            "label": "⚖️ Comparer les listes",
            "query": f"Comparer les programmes des listes sur {cat_label.lower()}",
            "type": "compare",
        }
    )

    return suggestions


# ── Lists config ─────────────────────────────────────────

LISTS = {
    "audierne2026": "Programme co-construit",
    "ca": "Construire l'Avenir",
    "paa": "Passons à l'Action !",
    "spae": "S'unir pour Audierne-Esquibien",
    "csnf": "Cap sur Notre Futur",
}

COMPARE_LISTS = {k: v for k, v in LISTS.items() if k != "audierne2026"}

# ── Header ────────────────────────────────────────────────
render_header()

# ── Inline mode toggle ───────────────────────────────────
col_chat, col_compare, col_spacer = st.columns([1, 1, 2])
with col_chat:
    if st.button(
        "💬 Poser une question",
        use_container_width=True,
        type="primary" if st.session_state.mode == "chat" else "secondary",
    ):
        st.session_state.mode = "chat"
        st.rerun()
with col_compare:
    if st.button(
        "⚖️ Comparer les programmes",
        use_container_width=True,
        type="primary" if st.session_state.mode == "compare" else "secondary",
    ):
        st.session_state.mode = "compare"
        st.rerun()

# ── Mode-specific controls (inline) ──────────────────────
if st.session_state.mode == "compare":
    selected_lists = st.multiselect(
        "Listes à comparer",
        options=list(COMPARE_LISTS.keys()),
        default=list(COMPARE_LISTS.keys()),
        format_func=lambda x: COMPARE_LISTS[x],
    )
    filter_list = ""
else:
    selected_lists = []
    filter_list = st.selectbox(
        "Filtrer par liste (optionnel)",
        options=[""] + list(LISTS.keys()),
        format_func=lambda x: "Toutes les sources" if x == "" else LISTS[x],
    )

# ── Empty state: starter suggestions ──────────────────────
if not st.session_state.messages:
    st.markdown(
        "<p style='text-align:center; color:#9b9b9d; margin-top:2rem;'>"
        "Posez une question ou essayez :</p>",
        unsafe_allow_html=True,
    )
    _starters = [
        ("🏠 Logement", "Que proposent les listes sur le logement ?"),
        ("🌿 Ecologie", "Quelles mesures pour l'environnement ?"),
        ("🏗️ Economie", "Que proposent les listes pour l'economie locale ?"),
        ("📚 Jeunesse", "Quelles propositions pour la jeunesse et l'education ?"),
    ]
    _starter_cols = st.columns(len(_starters))
    for _col, (_label, _query) in zip(_starter_cols, _starters):
        with _col:
            if st.button(_label, key=f"starter_{_label}", use_container_width=True):
                st.session_state["_pending_suggestion"] = {"query": _query}
                st.rerun()

# ── Chat history ──────────────────────────────────────────
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

            is_last_assistant = i == max(
                j
                for j, m in enumerate(st.session_state.messages)
                if m["role"] == "assistant"
            )
            suggestions = msg.get("suggestions", []) if is_last_assistant else []

            if existing_feedback is not None:
                if existing_feedback > 0.5:
                    st.caption("👍 Merci pour votre retour !")
                else:
                    st.caption("👎 Merci, nous allons améliorer.")
            else:
                n_sug = min(len(suggestions), 4)
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

# Auto-scroll to bottom after rendering message history (no iframe = no sandbox warning)
if st.session_state.messages:
    st.markdown(
        """
    <script>
        const main = window.parent.document.querySelector('section.main');
        if (main) main.scrollTo({ top: main.scrollHeight, behavior: 'smooth' });
    </script>
    """,
        unsafe_allow_html=True,
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
        try:
            loop.run_until_complete(ait.aclose())
        except Exception:
            pass
        loop.close()


# ── Input (floating) ─────────────────────────────────────
# The floating input stays pinned to the viewport bottom via streamlit-float.
# Suggestions can also inject a prompt (bypassing the chat_input).

_pending = st.session_state.pop("_pending_suggestion", None)
if _pending:
    if _pending.get("filter_list"):
        filter_list = _pending["filter_list"]
    if _pending.get("type") == "compare":
        st.session_state.mode = "compare"

# Use floating input from app.ui
from app.ui import render_floating_input

prompt = _pending["query"] if _pending else render_floating_input("Votre question...")

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    from app.agents.ocapistaine import OCapistaineAgent

    agent = OCapistaineAgent(
        provider_name="mistral",
        model_override="mistral-medium-latest",
    )

    # Build conversation history (last 6 turns = 3 exchanges)
    history = []
    for msg in st.session_state.messages[:-1]:
        if msg["role"] in ("user", "assistant"):
            history.append({"role": msg["role"], "content": msg["content"]})
    history = history[-6:]

    with st.chat_message("assistant"):
        with st.status("Recherche dans les documents...", expanded=False) as status:
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

            model = result.get("model", "")
            confidence = result.get("confidence")
            trace_id = result.get("trace_id")
            meta_parts = [f"Modèle: {model}"]
            if confidence is not None:
                meta_parts.append(f"Confiance: {confidence:.1%}")
            if trace_id:
                meta_parts.append(f"Trace: `{trace_id[:8]}...`")
            st.caption(" | ".join(meta_parts))

            active_list_filter = filter_list if filter_list else ""
            suggestions = _build_suggestions(result, prompt, active_list_filter)

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

    st.rerun()

# ── Footer ───────────────────────────────────────────────


def _clear_conversation():
    st.session_state.messages = []
    st.session_state.session_id = str(uuid.uuid4())
    st.rerun()


render_footer(
    show_clear=bool(st.session_state.messages),
    on_clear=_clear_conversation,
)
