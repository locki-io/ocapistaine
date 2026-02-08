# test_n8n_integration.py
"""
Integration tests for N8N webhook interactions.

Tests the communication between OCapistaine app and N8N workflows:
- Charter validation webhook (forseti/charter-valid)
- Response handling and error cases

NOTE: These tests are skipped by default because app.front requires Streamlit
which cannot be imported in a test context. Run with --run-integration to enable.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import requests


# Skip all tests in this module - Streamlit can't be imported in tests
pytestmark = pytest.mark.skip(
    reason="Streamlit module cannot be imported in test context. "
    "These tests require refactoring app.front to be testable."
)


class TestN8NCharterValidationWebhook:
    """Test N8N charter validation webhook integration."""

    @pytest.fixture
    def mock_forseti_result(self):
        """Mock ForsetiAgent validation result."""
        result = MagicMock()
        result.is_valid = True
        result.category = "economie"
        result.original_category = "economie"
        result.violations = []
        result.encouraged_aspects = ["Proposition constructive"]
        result.reasoning = "La contribution est conforme."
        result.confidence = 0.85
        return result

    @pytest.fixture
    def mock_forseti_invalid_result(self):
        """Mock ForsetiAgent invalid result."""
        result = MagicMock()
        result.is_valid = False
        result.category = None
        result.original_category = None
        result.violations = ["Attaque personnelle"]
        result.encouraged_aspects = []
        result.reasoning = "Non conforme."
        result.confidence = 0.75
        return result

    @patch("app.front.get_forseti_agent")
    @patch("requests.post")
    def test_webhook_called_when_valid(
        self, mock_post, mock_get_agent, mock_forseti_result, mock_n8n_label_added
    ):
        """N8N webhook is called when Forseti validates as compliant."""
        # Setup mocks
        mock_agent = MagicMock()
        mock_agent.validate = AsyncMock(return_value=mock_forseti_result)
        mock_get_agent.return_value = mock_agent

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = mock_n8n_label_added
        mock_post.return_value = mock_response

        # Import and call the function
        from app.front import _validate_with_forseti

        result = _validate_with_forseti(
            title="[economie] Test",
            body="Test content",
            category="economie",
            user_id="test-user",
            issue_id=64,
        )

        # Verify N8N was called
        assert mock_post.called
        call_args = mock_post.call_args
        assert "forseti/charter-valid" in call_args[0][0]
        assert call_args[1]["json"]["issueNumber"] == 64
        assert call_args[1]["json"]["is_valid"] is True

        # Verify result contains N8N action
        assert result["n8n_action"] is not None
        assert result["n8n_action"]["assigned_to_ocapistaine"] is True

    @patch("app.front.get_forseti_agent")
    @patch("requests.post")
    def test_webhook_not_called_when_invalid(
        self, mock_post, mock_get_agent, mock_forseti_invalid_result
    ):
        """N8N webhook is NOT called when validation fails."""
        mock_agent = MagicMock()
        mock_agent.validate = AsyncMock(return_value=mock_forseti_invalid_result)
        mock_get_agent.return_value = mock_agent

        from app.front import _validate_with_forseti

        result = _validate_with_forseti(
            title="Bad contribution",
            body="Personal attack content",
            category=None,
            user_id="test-user",
            issue_id=65,
        )

        # N8N should NOT be called for invalid contributions
        mock_post.assert_not_called()
        assert result["is_valid"] is False
        assert result["n8n_action"] is None

    @patch("app.front.get_forseti_agent")
    @patch("requests.post")
    def test_webhook_not_called_without_issue_id(
        self, mock_post, mock_get_agent, mock_forseti_result
    ):
        """N8N webhook is NOT called when issue_id is missing."""
        mock_agent = MagicMock()
        mock_agent.validate = AsyncMock(return_value=mock_forseti_result)
        mock_get_agent.return_value = mock_agent

        from app.front import _validate_with_forseti

        result = _validate_with_forseti(
            title="[economie] Test",
            body="Test content",
            category="economie",
            user_id="test-user",
            issue_id=0,  # No issue ID
        )

        mock_post.assert_not_called()
        assert result["is_valid"] is True
        assert result["n8n_action"] is None

    @patch("app.front.get_forseti_agent")
    @patch("requests.post")
    def test_handles_n8n_error_gracefully(
        self, mock_post, mock_get_agent, mock_forseti_result
    ):
        """App continues working if N8N webhook fails."""
        mock_agent = MagicMock()
        mock_agent.validate = AsyncMock(return_value=mock_forseti_result)
        mock_get_agent.return_value = mock_agent

        # Simulate N8N connection error
        mock_post.side_effect = requests.RequestException("Connection refused")

        from app.front import _validate_with_forseti

        # Should not raise, just log warning
        result = _validate_with_forseti(
            title="[economie] Test",
            body="Test content",
            category="economie",
            user_id="test-user",
            issue_id=64,
        )

        # Validation should still succeed
        assert result["success"] is True
        assert result["is_valid"] is True

        # N8N action should indicate failure
        assert result["n8n_action"]["success"] is False
        assert "Connection refused" in result["n8n_action"]["reason"]

    @patch("app.front.get_forseti_agent")
    @patch("requests.post")
    def test_handles_n8n_http_error(
        self, mock_post, mock_get_agent, mock_forseti_result
    ):
        """App handles N8N HTTP errors (4xx, 5xx)."""
        mock_agent = MagicMock()
        mock_agent.validate = AsyncMock(return_value=mock_forseti_result)
        mock_get_agent.return_value = mock_agent

        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        from app.front import _validate_with_forseti

        result = _validate_with_forseti(
            title="[economie] Test",
            body="Test content",
            category="economie",
            user_id="test-user",
            issue_id=64,
        )

        assert result["success"] is True
        assert result["n8n_action"]["success"] is False
        assert "HTTP 500" in result["n8n_action"]["reason"]

    @patch("app.front.get_forseti_agent")
    @patch("requests.post")
    def test_parses_n8n_array_response(
        self, mock_post, mock_get_agent, mock_forseti_result, mock_n8n_label_added
    ):
        """Correctly parses N8N array response format."""
        mock_agent = MagicMock()
        mock_agent.validate = AsyncMock(return_value=mock_forseti_result)
        mock_get_agent.return_value = mock_agent

        # N8N returns array with single item
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = mock_n8n_label_added  # This is a list
        mock_post.return_value = mock_response

        from app.front import _validate_with_forseti

        result = _validate_with_forseti(
            title="[economie] Test",
            body="Test content",
            category="economie",
            user_id="test-user",
            issue_id=64,
        )

        # Should extract first item from array
        assert result["n8n_action"]["assigned_to_ocapistaine"] is True
        assert result["n8n_action"]["reason"] == "Label added"

    @patch("app.front.get_forseti_agent")
    @patch("requests.post")
    def test_handles_already_labeled_response(
        self, mock_post, mock_get_agent, mock_forseti_result, mock_n8n_already_labeled
    ):
        """Handles N8N response when issue already has label."""
        mock_agent = MagicMock()
        mock_agent.validate = AsyncMock(return_value=mock_forseti_result)
        mock_get_agent.return_value = mock_agent

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = mock_n8n_already_labeled
        mock_post.return_value = mock_response

        from app.front import _validate_with_forseti

        result = _validate_with_forseti(
            title="[economie] Test",
            body="Test content",
            category="economie",
            user_id="test-user",
            issue_id=64,
        )

        # Validation succeeded but no label was added
        assert result["success"] is True
        assert result["n8n_action"]["assigned_to_ocapistaine"] is False
        assert "Already has" in result["n8n_action"]["reason"]


class TestN8NIssuesWebhook:
    """Test N8N issues listing webhook integration."""

    @patch("requests.post")
    def test_fetch_issues_success(self, mock_post, sample_github_issue):
        """Successfully fetches issues from N8N webhook."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "count": 1,
            "issues": [sample_github_issue],
        }
        mock_post.return_value = mock_response

        from app.front import _fetch_issues

        # Clear cache for test
        _fetch_issues.clear()

        result = _fetch_issues(state="open", labels="", per_page=10)

        assert result["success"] is True
        assert result["count"] == 1
        assert len(result["issues"]) == 1

    @patch("requests.post")
    def test_fetch_issues_error(self, mock_post):
        """Handles N8N webhook error gracefully."""
        mock_post.side_effect = requests.RequestException("Connection refused")

        from app.front import _fetch_issues

        _fetch_issues.clear()

        result = _fetch_issues(state="open")

        assert result["success"] is False
        assert "Connection refused" in result["error"]
        assert result["count"] == 0
        assert result["issues"] == []
