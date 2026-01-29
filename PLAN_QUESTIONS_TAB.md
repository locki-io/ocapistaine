# Plan: Transform Questions Tab into Contribution Assistant

## Summary

Transform the placeholder "Questions" tab into an interactive contribution creation assistant that helps users create charter-compliant contributions by:
1. Selecting inspiration sources (Audierne2026 docs or custom text)
2. Choosing a category
3. Getting AI-assisted draft generation
4. Editing and saving their contribution in Framaforms format

## Files to Modify/Create

| File | Action | Description |
|------|--------|-------------|
| `app/front.py` | Modify | Replace `chat_view()` with new implementation |
| `app/questions/__init__.py` | Create | Module exports |
| `app/questions/contribution_assistant.py` | Create | LLM helper for draft generation |
| `app/questions/views.py` | Create | Streamlit UI components for 5-step workflow |
| `app/translations/fr.json` | Modify | Add ~25 French translation keys |
| `app/translations/en.json` | Modify | Add ~25 English translation keys |
| `tests/test_contribution_assistant.py` | Create | Unit tests |
| `tests/test_questions_integration.py` | Create | Integration tests |

## Workflow Design (5 Steps)

```
Step 1: Select Source     → Document from Audierne2026 OR paste custom text
Step 2: Choose Category   → One of 7 categories (economie, logement, etc.)
Step 3: Get Inspired      → AI generates draft contribution
Step 4: Edit Contribution → User edits constat_factuel & idees_ameliorations
Step 5: Save              → Store to Redis with source="input"
```

## Key Implementation Details

### 1. New Module: `app/questions/contribution_assistant.py`

```python
class ContributionAssistant:
    """Help users create contributions (NO violations - valid only)"""

    async def generate_draft(
        self,
        source_text: str,
        category: str,
        language: str = "fr"  # Support en/fr
    ) -> DraftContribution:
        """Generate draft constat_factuel + idees_ameliorations"""
```

Key differences from `FieldInputGenerator`:
- No violation injection
- Single contribution focus (not batch)
- User-editable output
- Simpler prompts focused on helping users

### 2. UI Components in `app/questions/views.py`

- `render_source_selection()` - Reuses `list_audierne_docs()` from mockup
- `render_category_selection()` - Uses `CATEGORIES` from forseti
- `render_inspiration()` - Generates draft, shows preview
- `render_edit_contribution()` - Two editable `text_area` widgets
- `render_save_confirmation()` - Success message + new contribution button

### 3. Session State Keys

```python
st.session_state.questions_step         # Current step (1-5)
st.session_state.questions_source_content  # Selected/pasted content
st.session_state.questions_category     # Selected category
st.session_state.questions_draft_constat   # Generated draft
st.session_state.questions_draft_idees     # Generated draft
```

### 4. Save to Redis

```python
record = ValidationRecord(
    id=f"input_{uuid.uuid4().hex[:12]}",
    source="input",  # Distinguishes from mockup-generated
    is_valid=True,   # User-created
    confidence=1.0,  # User-validated
    ...
)
storage.save_validation(record)
```

### 5. Translation Keys (~25 per language)

Key categories:
- `questions_title`, `questions_subtitle`
- `questions_step1_title` through `questions_step5_title`
- `questions_source_*` (source selection labels)
- `questions_constat_*`, `questions_idees_*` (contribution fields)
- `questions_next`, `questions_back`, `questions_save`

## Reused Components

From `app/mockup/`:
- `field_input.py`: `list_audierne_docs()`, `read_markdown_input()`
- `storage.py`: `get_storage()`, `ValidationRecord`

From `app/agents/forseti/`:
- `CATEGORIES`, `CATEGORY_DESCRIPTIONS`

From `app/`:
- `providers.py`: `get_provider()`
- `sidebar.py`: `get_selected_provider()`, `get_model_id()`

## Testing Strategy

### Unit Tests
- Test `ContributionAssistant.generate_draft()` returns valid structure
- Test draft contains no violation language
- Test dataclass structure

### Integration Tests
- Test save to Redis works with `source="input"`
- Test saved contribution retrievable and has correct format

### Manual Testing Checklist
1. Source selection works (docs + paste)
2. Category selection persists
3. Draft generation with spinner
4. Edit fields pre-populated
5. Save creates Redis record
6. Both EN and FR languages work

## Verification

After implementation:
1. Run `poetry run streamlit run app/front.py`
2. Navigate to Questions tab
3. Complete full 5-step workflow
4. Check Redis for saved contribution: `redis-cli -n 5 keys "contribution_mockup:*input*"`
5. Toggle language and verify all labels switch
6. Run `poetry run pytest tests/test_contribution_assistant.py tests/test_questions_integration.py`

## How to Resume

To implement this plan later, tell Claude:
```
Implement the plan in PLAN_QUESTIONS_TAB.md
```
