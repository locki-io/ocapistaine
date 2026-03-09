# front_chat.py
"""
OCapistaine — RAG Chat Interface

Minimal Streamlit UI for querying municipal documents and comparing electoral programs.
Uses session_id as Opik thread_id for conversation tracing.

Run with:
    streamlit run app/front_chat.py
"""

import asyncio
import streamlit as st

st.set_page_config(
    page_title="OCapistaine — Chat",
    page_icon="⚓",
    layout="centered",
)

# Session ID = thread_id for Opik tracing
if "session_id" not in st.session_state:
    import uuid
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "mode" not in st.session_state:
    st.session_state.mode = "chat"

# ── Sidebar ──────────────────────────────────────────────

LISTS = {
    "audierne2026": "Audierne 2026 (co-construit)",
    "construire-avenir": "Construire l'Avenir",
    "paa": "PAA",
    "spae": "SPAE",
    "csnfa": "CSNFA",
}

with st.sidebar:
    st.title("⚓ OCapistaine")
    st.caption(f"Session: `{st.session_state.session_id[:8]}...`")

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

st.title("⚓ OCapistaine — Chat")

if st.session_state.mode == "compare":
    st.info("Mode comparaison : posez une question pour comparer les programmes des listes sélectionnées.")
else:
    st.info("Posez une question sur les documents municipaux d'Audierne-Esquibien.")

# Display history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander(f"Sources ({len(msg['sources'])})"):
                for s in msg["sources"]:
                    title = s.get("title") or s.get("doc_id", "")
                    list_name = s.get("list_name", "")
                    label = f"**{title}**" + (f" — {list_name}" if list_name else "")
                    st.markdown(f"- {label}")

# Input
if prompt := st.chat_input("Votre question..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Recherche en cours..."):
            from app.rag import RAGService

            service = RAGService()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                if st.session_state.mode == "compare" and selected_lists:
                    result = loop.run_until_complete(
                        service.compare(
                            question=prompt,
                            list_names=selected_lists,
                            thread_id=st.session_state.session_id,
                        )
                    )
                else:
                    filters = {"list_name": filter_list} if filter_list else None
                    result = loop.run_until_complete(
                        service.query(
                            question=prompt,
                            filters=filters,
                            thread_id=st.session_state.session_id,
                        )
                    )
            finally:
                loop.close()

        # Display response
        st.markdown(result["response"])

        sources = result.get("sources", [])
        if sources:
            with st.expander(f"Sources ({len(sources)})"):
                for s in sources:
                    title = s.get("title") or s.get("doc_id", "")
                    list_name = s.get("list_name", "")
                    label = f"**{title}**" + (f" — {list_name}" if list_name else "")
                    st.markdown(f"- {label}")

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
    st.session_state.messages.append({
        "role": "assistant",
        "content": result["response"],
        "sources": sources,
    })
