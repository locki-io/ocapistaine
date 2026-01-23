#!/usr/bin/env python3
"""
Set Streamlit environment variables dynamically based on .env configuration.

This script reads NGROK_DOMAIN and other settings from .env and generates
the STREAMLIT_SERVER_ALLOWED_ORIGINS list automatically.

Usage:
    # Export variables for current shell
    eval $(python scripts/set_streamlit_env.py)

    # Or run streamlit with the script
    python scripts/set_streamlit_env.py && streamlit run app/front.py
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

def build_allowed_origins():
    """Build allowed origins list from environment configuration."""
    origins = []

    # Always include localhost for development
    streamlit_port = os.getenv("STREAMLIT_PORT", "8502")
    origins.extend([
        f"http://localhost:{streamlit_port}",
        f"http://127.0.0.1:{streamlit_port}",
    ])

    # Add ngrok domain if configured
    ngrok_domain = os.getenv("NGROK_DOMAIN", "").strip()
    if ngrok_domain:
        # Remove protocol if present
        ngrok_domain = ngrok_domain.replace("https://", "").replace("http://", "")
        origins.append(f"https://{ngrok_domain}")

    # Add production domains
    production_domains = [
        "https://ocapistaine.vaettir.locki.io",
        "https://vaettir.locki.io",
    ]
    origins.extend(production_domains)

    # Add any custom origins from environment
    custom_origins = os.getenv("STREAMLIT_CUSTOM_ORIGINS", "").strip()
    if custom_origins:
        origins.extend([o.strip() for o in custom_origins.split(",") if o.strip()])

    # Remove duplicates while preserving order
    seen = set()
    unique_origins = []
    for origin in origins:
        if origin not in seen:
            seen.add(origin)
            unique_origins.append(origin)

    return unique_origins


def main():
    """Generate environment variable export commands."""
    origins = build_allowed_origins()
    origins_str = ",".join(origins)

    # Print export commands for shell evaluation
    print(f'export STREAMLIT_SERVER_ALLOWED_ORIGINS="{origins_str}"')
    print(f'export STREAMLIT_SERVER_ENABLE_CORS=true')
    print(f'export STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false')

    # Optional: Set browser config if NGROK_DOMAIN is set
    ngrok_domain = os.getenv("NGROK_DOMAIN", "").strip()
    if ngrok_domain:
        ngrok_domain = ngrok_domain.replace("https://", "").replace("http://", "")
        print(f'export STREAMLIT_BROWSER_SERVER_ADDRESS="{ngrok_domain}"')
        print(f'export STREAMLIT_BROWSER_SERVER_PORT=443')

    # Show what we configured (as a comment)
    print(f"\n# Configured allowed origins:", file=os.sys.stderr)
    for origin in origins:
        print(f"#   - {origin}", file=os.sys.stderr)


if __name__ == "__main__":
    main()
