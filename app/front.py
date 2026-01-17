# front.py
"""
OCapistaine - Citizen Q&A Interface

Simplified Streamlit UI for civic transparency.
User identification via single UUID (cookie-based).
"""

import streamlit as st

# MUST be first Streamlit command
st.set_page_config(
    page_title="Ò Capistaine - Civic Transparency",
    page_icon="🏛️",
    layout="wide",
)

from app.sidebar import sidebar_setup, get_user_id
from data.redis_client import get_redis_connection

# TODO: Import services when implemented
# from app.services.chat_service import ChatService
# from app.services.rag_service import RAGService


def main():
    """Main application entry point."""

    # Initialize sidebar and get user_id
    user_id = sidebar_setup()

    # Store in session for cross-component access
    st.session_state.user_id = user_id

    # Header
    st.title("🏛️ Ò Capistaine")
    st.markdown("**Posez vos questions sur la vie municipale d'Audierne**")

    # Main tabs
    tabs = st.tabs(["💬 Questions", "📄 Documents", "ℹ️ À propos"])

    with tabs[0]:
        chat_view(user_id)

    with tabs[1]:
        documents_view(user_id)

    with tabs[2]:
        about_view()


def chat_view(user_id: str):
    """Citizen Q&A chat interface."""

    r = get_redis_connection()
    thread_id = st.session_state.get("thread_id", f"{user_id}:default")

    # Load chat history from Redis
    history_key = f"chat:{user_id}:{thread_id}"
    # TODO: Load history when ChatService is implemented
    # history = ChatService.load_history(r, history_key)
    history = []  # Placeholder

    # Display chat history
    chat_container = st.container()
    with chat_container:
        if not history:
            st.info(
                "👋 Bienvenue ! Posez une question sur les décisions municipales, "
                "le budget, ou tout autre sujet concernant Audierne."
            )
        else:
            for msg in history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Votre question sur la commune..."):
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Recherche dans les documents municipaux..."):
                # TODO: Replace with actual RAG call
                # response = RAGService.query(prompt, user_id)
                response = _placeholder_response(prompt)
                st.markdown(response)

        # TODO: Save to history when ChatService is implemented
        # ChatService.append_message(r, history_key, "user", prompt)
        # ChatService.append_message(r, history_key, "assistant", response)


def _placeholder_response(prompt: str) -> str:
    """Placeholder response until RAG is implemented."""
    return f"""
**🚧 RAG System en cours de développement**

Votre question : *"{prompt}"*

Cette fonctionnalité sera bientôt disponible. Le système RAG permettra de :
- 🔍 Rechercher dans 4,000+ documents municipaux
- 📄 Citer les sources (arrêtés, délibérations)
- ✅ Vérifier l'exactitude via Opik

En attendant, consultez [audierne2026.fr](https://audierne2026.fr) pour participer !
"""


def documents_view(user_id: str):
    """Document corpus overview."""

    st.subheader("📄 Corpus Documentaire")

    # Document stats (placeholder)
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Arrêtés identifiés", "4,010", help="Publications & arrêtés municipaux"
        )

    with col2:
        st.metric(
            "Documents indexés",
            "42",
            delta="🟡 En cours",
            help="Bulletins Gwaien collectés",
        )

    with col3:
        st.metric("Pipeline Firecrawl", "🔴", help="Infrastructure en développement")

    st.markdown("---")

    # Document sources table
    st.markdown("### Sources de données")

    sources_data = {
        "Source": [
            "Mairie - Arrêtés",
            "Mairie - Délibérations",
            "Commission de contrôle",
            "Gwaien (bulletin)",
        ],
        "URL": [
            "audierne.bzh/publications-arretes/",
            "audierne.bzh/deliberations-conseil-municipal/",
            "audierne.bzh/documentheque/",
            "OCR des bulletins PDF",
        ],
        "Status": ["🔴 À crawler", "🔴 À crawler", "🔴 À crawler", "🟡 42 collectés"],
        "Méthode": ["Firecrawl + OCR", "Firecrawl + OCR", "Firecrawl + OCR", "OCR"],
    }

    st.table(sources_data)

    # TODO: Add document search when implemented
    # st.text_input("🔍 Rechercher un document...", key="doc_search")


def about_view():
    """About page with project information."""

    st.subheader("ℹ️ À propos d'Ò Capistaine")

    st.markdown(
        """
    ### Ma résolution 2026

    > *Cette année, je comprendrai enfin mes élections locales et m'impliquerai en tant que citoyen.*

    **Ò Capistaine** est un outil de transparence civique alimenté par l'IA pour la démocratie locale.

    ### Fonctionnalités

    | Fonctionnalité | Description | Status |
    |----------------|-------------|--------|
    | Recherche documentaire | 4,000+ documents municipaux indexés | 🔴 En développement |
    | Questions-Réponses | Réponses sourcées en langage clair | 🔴 En développement |
    | Détection d'hallucinations | Vérification via Opik | 🟡 Planifié |
    | Multi-canal | Facebook, email, chatbot | 🟡 Planifié |

    ### Liens

    - 🌐 [audierne2026.fr](https://audierne2026.fr) - Plateforme de participation citoyenne
    - 📚 [docs.locki.io](https://docs.locki.io) - Documentation technique
    - 💻 [GitHub](https://github.com/locki-io/ocapistaine) - Code source

    ---

    *Si l'IA peut nous aider à tenir nos résolutions du Nouvel An, la plus impactante est peut-être : devenir un meilleur citoyen.*
    """
    )


if __name__ == "__main__":
    main()
