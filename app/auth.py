# auth.py
"""
Simple password authentication for OCapistaine.

Uses Streamlit secrets for password storage.
Password is stored in .streamlit/secrets.toml (gitignored).
"""

import os
import streamlit as st
import hashlib
import hmac

# Discord invite URL from environment
DISCORD_INVITE_URL = os.getenv("DISCORD_INVITE_URL", "https://discord.gg/locki")


def check_password() -> bool:
    """
    Check if user has entered the correct password.

    Returns True if authenticated, False otherwise.
    Shows login form if not authenticated.

    Usage:
        if not check_password():
            st.stop()
        # ... rest of your app
    """

    # Check if authentication is disabled (for local development)
    if not _auth_enabled():
        return True

    # Check if already authenticated this session
    if st.session_state.get("authenticated", False):
        return True

    # Show login form
    _show_login_form()
    return False


def _auth_enabled() -> bool:
    """Check if authentication is enabled via secrets."""
    try:
        # Auth is enabled if password is set in secrets
        return bool(st.secrets.get("auth", {}).get("password"))
    except Exception:
        # No secrets file or auth section
        return False


def _show_login_form():
    """Display the login form."""
    st.markdown(
        """
        <style>
        .login-container {
            max-width: 400px;
            margin: 100px auto;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("## Authentication")
        st.markdown("Enter the password to access OCapistaine.")

        with st.form("login_form"):
            password = st.text_input(
                "Password", type="password", placeholder="Enter password..."
            )
            submitted = st.form_submit_button("Sign in", use_container_width=True)

            if submitted:
                if _verify_password(password):
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")

        st.markdown("---")
        st.markdown(
            f"🐇 Need the password? Join our [Discord]({DISCORD_INVITE_URL}) to request access.",
            help="Contact the team on Discord to get the password",
        )


def _verify_password(password: str) -> bool:
    """Verify the entered password against the stored hash."""
    try:
        stored_password = st.secrets.get("auth", {}).get("password", "")

        # Support both plain text and hashed passwords
        if stored_password.startswith("sha256:"):
            # Hashed password
            stored_hash = stored_password[7:]
            input_hash = hashlib.sha256(password.encode()).hexdigest()
            return hmac.compare_digest(stored_hash, input_hash)
        else:
            # Plain text password (for simplicity)
            return hmac.compare_digest(password, stored_password)
    except Exception:
        return False


def logout():
    """Log out the current user."""
    st.session_state["authenticated"] = False
    st.rerun()


def hash_password(password: str) -> str:
    """
    Hash a password for storage in secrets.toml.

    Usage:
        python -c "from app.auth import hash_password; print(hash_password('your-password'))"
    """
    return f"sha256:{hashlib.sha256(password.encode()).hexdigest()}"
