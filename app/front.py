# front.py
"""
OCapistaine - Citizen Q&A Interface

Simplified Streamlit UI for civic transparency.
User identification via single UUID (cookie-based).
"""

import asyncio

import requests
import streamlit as st

# MUST be first Streamlit command
st.set_page_config(
    page_title="Ò Capistaine - Civic Transparency",
    page_icon="🏛️",
    layout="wide",
)

from app.sidebar import sidebar_setup, get_user_id
from app.agents.forseti import ForsetiAgent
from data.redis_client import get_redis_connection

# TODO: Import services when implemented
# from app.services.chat_service import ChatService
# from app.services.rag_service import RAGService


# Initialize Forseti agent (singleton)
@st.cache_resource
def get_forseti_agent():
    """Get or create Forseti agent instance."""
    return ForsetiAgent()


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
    tabs = st.tabs(["💬 Questions", "📝 Contributions", "📄 Documents", "ℹ️ À propos"])

    with tabs[0]:
        chat_view(user_id)

    with tabs[1]:
        contributions_view(user_id)

    with tabs[2]:
        documents_view(user_id)

    with tabs[3]:
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


# N8N Webhook URL for fetching issues
N8N_ISSUES_WEBHOOK = "https://vaettir.locki.io/webhook/participons/issues"


# Available category labels in audierne2026/participons
CATEGORY_LABELS = [
    "",  # All (no filter)
    "economie",
    "logement",
    "culture",
    "ecologie",
    "associations",
    "jeunesse",
    "alimentation-bien-etre-soins",
    "conforme charte",
]


@st.cache_data(ttl=300)  # Cache for 5 minutes
def _fetch_issues(state: str = "open", labels: str = "", per_page: int = 50) -> dict:
    """Fetch issues from N8N workflow webhook."""
    try:
        payload = {"state": state, "per_page": per_page}
        if labels:  # Only add labels filter if specified
            payload["labels"] = labels
        response = requests.post(
            N8N_ISSUES_WEBHOOK,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"success": False, "error": str(e), "count": 0, "issues": []}


def _validate_with_forseti(title: str, body: str, category: str | None) -> dict:
    """Validate a contribution with Forseti agent."""
    try:
        agent = get_forseti_agent()
        result = asyncio.run(agent.validate(title=title, body=body, category=category))
        return {
            "success": True,
            "is_valid": result.is_valid,
            "category": result.category,
            "original_category": result.original_category,
            "violations": result.violations,
            "encouraged_aspects": result.encouraged_aspects,
            "reasoning": result.reasoning,
            "confidence": result.confidence,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _display_forseti_result(result: dict):
    """Display Forseti validation result."""
    st.markdown("---")
    st.markdown("**🔍 Analyse Forseti 461**")

    if not result.get("success"):
        st.error(f"Erreur: {result.get('error', 'Erreur inconnue')}")
        return

    # Validation status
    if result.get("is_valid"):
        st.success("✅ Conforme à la charte")
    else:
        st.warning("⚠️ Non conforme à la charte")

    # Violations
    violations = result.get("violations", [])
    if violations:
        st.markdown("**Violations:**")
        for v in violations:
            st.markdown(f"- ❌ {v}")

    # Encouraged aspects
    encouraged = result.get("encouraged_aspects", [])
    if encouraged:
        st.markdown("**Points positifs:**")
        for e in encouraged:
            st.markdown(f"- ✨ {e}")

    # Category
    category = result.get("category")
    original = result.get("original_category")
    if category:
        cat_text = f"📁 Catégorie: **{category}**"
        if original and original != category:
            cat_text += f" (suggérée, était: {original})"
        st.markdown(cat_text)

    # Confidence
    confidence = result.get("confidence", 0)
    st.progress(confidence, text=f"Confiance: {confidence:.0%}")

    # Reasoning (collapsed)
    with st.expander("💭 Raisonnement", expanded=False):
        st.markdown(result.get("reasoning", ""))


def contributions_view(user_id: str):
    """Display contributions from audierne2026/participons repository."""

    st.subheader("📝 Contributions Citoyennes")
    st.markdown(
        "Contributions de la communauté sur [audierne2026/participons](https://github.com/audierne2026/participons)"
    )

    # Filters
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        state_filter = st.selectbox(
            "Statut",
            options=["open", "closed", "all"],
            format_func=lambda x: {
                "open": "🟢 Ouvertes",
                "closed": "🔴 Fermées",
                "all": "📋 Toutes",
            }[x],
        )

    with col2:
        label_filter = st.selectbox(
            "Catégorie",
            options=CATEGORY_LABELS,
            format_func=lambda x: "📋 Toutes" if x == "" else x.capitalize(),
        )

    with col3:
        if st.button("🔄 Actualiser"):
            st.cache_data.clear()

    st.markdown("---")

    # Fetch issues
    with st.spinner("Chargement des contributions..."):
        data = _fetch_issues(state=state_filter, labels=label_filter)

    if not data.get("success"):
        st.error(f"Erreur lors du chargement : {data.get('error', 'Erreur inconnue')}")
        return

    issues = data.get("issues", [])
    count = data.get("count", 0)

    # Stats
    st.metric("Contributions trouvées", count)

    if not issues:
        st.info("Aucune contribution trouvée avec ces critères.")
        return

    # Category color mapping
    category_colors = {
        "economie": "🔵",
        "logement": "🟠",
        "culture": "🟣",
        "ecologie": "🟢",
        "associations": "🟡",
        "jeunesse": "🔴",
        "alimentation-bien-etre-soins": "🩷",
    }

    # Display issues
    for issue in issues:
        issue_id = issue.get("id")
        category = issue.get("category")
        category_icon = category_colors.get(category, "⚪")
        has_charte = issue.get("has_conforme_charte", False)
        charte_badge = "✅" if has_charte else ""

        with st.expander(
            f"{category_icon} {issue.get('title', 'Sans titre')} {charte_badge}",
            expanded=False,
        ):
            # Metadata row
            meta_col1, meta_col2, meta_col3 = st.columns(3)
            with meta_col1:
                st.caption(f"**#{issue_id}** par {issue.get('user', 'inconnu')}")
            with meta_col2:
                if category:
                    st.caption(f"📁 {category.capitalize()}")
            with meta_col3:
                if has_charte:
                    st.caption("✅ Conforme à la charte")

            # Labels
            labels = issue.get("labels", [])
            if labels:
                st.markdown(" ".join([f"`{label}`" for label in labels]))

            # Body
            title = issue.get("title", "")
            body = issue.get("body", "")
            if body:
                st.markdown(body[:500] + ("..." if len(body) > 500 else ""))

            # Actions row
            action_col1, action_col2 = st.columns([1, 3])

            with action_col1:
                # Forseti validation button
                if st.button("🔍 Vérifier charte", key=f"validate_{issue_id}"):
                    with st.spinner("Analyse par Forseti 461..."):
                        result = _validate_with_forseti(title, body, category)
                        st.session_state[f"forseti_result_{issue_id}"] = result

            with action_col2:
                # Link to GitHub
                html_url = issue.get("html_url")
                if html_url:
                    st.markdown(f"[Voir sur GitHub]({html_url})")

            # Display Forseti result if available
            result_key = f"forseti_result_{issue_id}"
            if result_key in st.session_state:
                result = st.session_state[result_key]
                _display_forseti_result(result)


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
