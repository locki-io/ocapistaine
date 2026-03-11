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
import streamlit as st

st.set_page_config(
    page_title="Ò Capistaine — Les municipales à Audierne-Esquibien",
    page_icon="⚓",
    layout="centered",
)

# ── UI components from app.ui ─────────────────────────────
from app.ui import (
    apply_theme,
    render_header,
    render_footer,
    init_chat_float,
    scroll_to_bottom,
    scroll_to_bottom_streaming,
)

apply_theme(hide_sidebar=True)
init_chat_float()

# ── Session persistence (app:chat:session:*, 1h TTL) ─────────────
from app.services.chat_session import (
    generate_session_id,
    save_chat_session,
    load_chat_session,
)

# Recovery: check URL param ?session=<id> to restore a previous session
_url_session = st.query_params.get("session")

if "session_id" not in st.session_state:
    if _url_session:
        # Try to restore from Redis
        _restored = load_chat_session(_url_session)
        if _restored:
            st.session_state.session_id = _restored.session_id
            st.session_state.messages = _restored.messages
            st.session_state.mode = _restored.mode
            st.session_state.filter_list = _restored.filter_list
            if _restored.selected_lists:
                st.session_state.selected_lists = _restored.selected_lists
            st.session_state._session_restored = True
        else:
            st.session_state.session_id = generate_session_id()
    else:
        st.session_state.session_id = generate_session_id()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "mode" not in st.session_state:
    st.session_state.mode = "chat"

# Sync URL param with current session ID
if st.query_params.get("session") != st.session_state.session_id:
    st.query_params["session"] = st.session_state.session_id


# ── Session save helper ───────────────────────────────────


def _save_session():
    """Save current session state to Redis (messages + mode + filters)."""
    save_chat_session(
        st.session_state.session_id,
        st.session_state.messages,
        st.session_state.mode,
        filter_list=st.session_state.get("filter_list", ""),
        selected_lists=st.session_state.get("selected_lists", []),
    )


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
        _save_session()


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

# ── Header (with cost counter) ────────────────────────────
from app.services.cost import get_total_cost

_session_cost = st.session_state.get("session_cost_usd", 0.0)
_session_eur = _session_cost * 0.92  # USD→EUR approximate
_total_usd, _total_queries = get_total_cost()
_total_eur = _total_usd * 0.92

_cost_parts = []
if _session_eur > 0:
    _cost_parts.append(f"session : {_session_eur:.4f} €")
if _total_queries > 0:
    _cost_parts.append(f"total : {_total_eur:.4f} € ({_total_queries} requêtes)")
_cost_tag = f" — {' | '.join(_cost_parts)}" if _cost_parts else ""

render_header(
    tagline=f"Ici l'IA n'est pas une boite noire, c'est notre phare vers les municipales{_cost_tag}",
)

# ── Inline mode toggle ───────────────────────────────────
col_clear, col_chat, col_compare, col_spacer = st.columns([1, 2, 2, 3], gap="medium")
with col_clear:
    if st.session_state.messages:
        if st.button("🔄", help="Nouvelle conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.session_id = generate_session_id()
            st.rerun()
with col_chat:
    if st.button(
        "💬 Poser une question",
        use_container_width=True,
        type="primary" if st.session_state.mode == "chat" else "secondary",
        disabled=False,
    ):
        st.session_state.mode = "chat"
        st.rerun()
with col_compare:
    if st.button(
        "⚖️ Comparer les programmes",
        use_container_width=True,
        type="primary" if st.session_state.mode == "compare" else "secondary",
        disabled=False,
    ):
        st.session_state.mode = "compare"
        st.session_state.messages = []
        st.session_state.session_id = generate_session_id()
        st.rerun()

# ── Compare mode: category button grid ───────────────────
selected_lists = list(COMPARE_LISTS.keys()) if st.session_state.mode == "compare" else []
filter_list = ""

if st.session_state.mode == "compare" and not st.session_state.get("_pending_suggestion"):
    st.markdown(
        "<p style='text-align:center; color:#9b9b9d; margin-top:1rem;'>"
        "Choisissez un thème pour comparer les 4 listes</p>",
        unsafe_allow_html=True,
    )
    # 2 rows of buttons: 4 + 3
    row1_cats = list(CATEGORY_LABELS_FR.items())[:4]
    row2_cats = list(CATEGORY_LABELS_FR.items())[4:]

    cols1 = st.columns(len(row1_cats), gap="small")
    for col, (cat_key, cat_label) in zip(cols1, row1_cats):
        icon = CATEGORY_ICONS.get(cat_key, "")
        with col:
            if st.button(
                f"{icon}\n{cat_label}",
                key=f"compare_cat_{cat_key}",
                use_container_width=True,
                disabled=False,
            ):
                st.session_state.messages = []
                st.session_state.session_id = generate_session_id()
                st.session_state["_pending_suggestion"] = {
                    "query": f"Comparer les programmes des listes sur {cat_label.lower()}",
                    "type": "compare",
                }
                st.rerun()

    cols2 = st.columns(len(row2_cats) + 1, gap="small")  # +1 for balanced spacing
    for col, (cat_key, cat_label) in zip(cols2, row2_cats):
        icon = CATEGORY_ICONS.get(cat_key, "")
        with col:
            if st.button(
                f"{icon}\n{cat_label}",
                key=f"compare_cat_{cat_key}",
                use_container_width=True,
                disabled=False,
            ):
                st.session_state.messages = []
                st.session_state.session_id = generate_session_id()
                st.session_state["_pending_suggestion"] = {
                    "query": f"Comparer les programmes des listes sur {cat_label.lower()}",
                    "type": "compare",
                }
                st.rerun()

# ── Empty state (chat mode only) ─────────────────────────
elif st.session_state.mode == "chat" and not st.session_state.messages:
    st.markdown(
        "<p style='text-align:center; color:#9b9b9d; margin-top:2rem;'>"
        "Posez votre question sur les municipales d'Audierne-Esquibien</p>",
        unsafe_allow_html=True,
    )

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

# Scroll to bottom on page load when there's chat history
if st.session_state.messages:
    scroll_to_bottom()

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
            except GeneratorExit:
                break
    finally:
        try:
            loop.run_until_complete(ait.aclose())
        except Exception:
            pass
        loop.close()


# ── Input (native st.chat_input — pinned at bottom by Streamlit) ─────────
# Suggestions inject a prompt via session state, bypassing the input widget.

_pending = st.session_state.pop("_pending_suggestion", None)
if _pending:
    if _pending.get("filter_list"):
        filter_list = _pending["filter_list"]
    if _pending.get("type") == "compare":
        st.session_state.mode = "compare"
        selected_lists = list(COMPARE_LISTS.keys())

# In compare mode: no chat input (category buttons handle it)
# In chat mode: native st.chat_input()
if _pending:
    prompt = _pending["query"]
elif st.session_state.mode == "chat":
    prompt = st.chat_input("Votre question...")
else:
    prompt = None

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Lock ALL buttons during streaming (CSS injection — Streamlit can't re-render mid-stream)
    st.markdown(
        """
    <style>
    .stButton > button { pointer-events: none !important; opacity: 0.5 !important; }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # Scroll: snap to user message, then install streaming observer
    scroll_to_bottom(smooth=False)
    scroll_to_bottom_streaming()

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
            # Refresh selected_lists in case mode changed via _pending
            if st.session_state.mode == "compare":
                selected_lists = list(COMPARE_LISTS.keys())
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
            usage = result.get("usage", {})
            cost_usd = usage.get("cost_usd")
            meta_parts = [f"Modèle: {model}"]
            if confidence is not None:
                meta_parts.append(f"Confiance: {confidence:.1%}")
            if trace_id:
                meta_parts.append(f"Trace: `{trace_id[:8]}...`")
            st.caption(" | ".join(meta_parts))

            # Accumulate session cost
            if cost_usd is not None:
                st.session_state.setdefault("session_cost_usd", 0.0)
                st.session_state["session_cost_usd"] += cost_usd

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

    # Final scroll after assistant reply
    scroll_to_bottom()

    _save_session()

    st.rerun()

# ── Session indicator ────────────────────────────────────
if st.session_state.get("_session_restored"):
    st.toast(f"Session restaurée : {st.session_state.session_id}", icon="🔄")
    del st.session_state._session_restored

if st.session_state.messages:
    session_cost = st.session_state.get("session_cost_usd", 0.0)
    opik_url = "https://www.comet.com/opik/ocapistaine-dev/dashboards/019bfeab-a248-7385-84ca-54391e73af42"
    session_meta = f"Session : `{st.session_state.session_id}` — valide 1h"
    if session_cost > 0:
        session_meta += f" | Coût session : ${session_cost:.6f}"
    session_meta += f" | [Traces Opik]({opik_url})"
    st.caption(session_meta)

# ── Footer ───────────────────────────────────────────────


render_footer()
