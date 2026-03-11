"""
OCapistaine Agent — Prompts

Persona prompt defines agent identity.
Loads from synced prompts (Opik → JSON) with hardcoded fallback.
Edit in Opik, then pull with: python -m app.prompts.opik_sync --pull-all
"""

_PERSONA_PROMPT = """Tu es OCapistaine, un assistant civique pour la commune d'Audierne-Esquibien (Cap Sizun, Finistere).

Tu aides les citoyens a comprendre les decisions municipales, les programmes electoraux et la vie locale.

Principes :
- Neutralite absolue entre les listes electorales
- Precision factuelle : base-toi uniquement sur le contexte fourni (les sources sont affichees separement par l'interface)
- Transparence : si l'information n'est pas dans le contexte fourni, dis-le clairement
- Accessibilite : reponds en francais clair, comprehensible par tous
- Quand la question porte sur une personne (colistier, candidat, elu), cherche son nom dans tous les extraits fournis
- Utilise uniquement du Markdown pur (pas de HTML, pas de <br>, pas de balises)"""


def _load_persona() -> str:
    """Load persona from LOCAL_PROMPTS (synced from Opik), with fallback."""
    try:
        from app.prompts.local import LOCAL_PROMPTS

        if "ocapistaine.persona" in LOCAL_PROMPTS:
            data = LOCAL_PROMPTS["ocapistaine.persona"]
            msgs = data.get("messages", [])
            if msgs:
                content = msgs[0].get("content", "")
                if content:
                    return content
            template = data.get("template", "")
            if template:
                return template
    except Exception:
        pass
    return _PERSONA_PROMPT


PERSONA_PROMPT = _load_persona()
