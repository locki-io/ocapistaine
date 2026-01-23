#!/usr/bin/env python3
"""
Verify CORS configuration for Streamlit.

Checks if the running Streamlit instance has proper CORS settings.
"""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load .env
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

def check_env_vars():
    """Check if CORS environment variables are set."""
    print("🔍 Checking environment variables...")
    print()

    required_vars = {
        "STREAMLIT_SERVER_ENABLE_CORS": os.getenv("STREAMLIT_SERVER_ENABLE_CORS"),
        "STREAMLIT_SERVER_ALLOWED_ORIGINS": os.getenv("STREAMLIT_SERVER_ALLOWED_ORIGINS"),
        "NGROK_DOMAIN": os.getenv("NGROK_DOMAIN"),
    }

    all_set = True
    for var, value in required_vars.items():
        if value:
            print(f"  ✓ {var} = {value[:80]}{'...' if len(value) > 80 else ''}")
        else:
            print(f"  ✗ {var} NOT SET")
            all_set = False

    print()
    return all_set

def check_streamlit_health():
    """Check if Streamlit is running and responding."""
    port = os.getenv("STREAMLIT_PORT", "8502")
    print(f"🏥 Checking Streamlit health (localhost:{port})...")

    try:
        response = requests.get(f"http://localhost:{port}/_stcore/health", timeout=5)
        if response.status_code == 200:
            print(f"  ✓ Streamlit is running on port {port}")
            return True
        else:
            print(f"  ✗ Unexpected status: {response.status_code}")
            return False
    except requests.RequestException as e:
        print(f"  ✗ Streamlit not responding: {e}")
        return False

def check_ngrok_tunnel():
    """Check if ngrok tunnel is active."""
    print("🌐 Checking ngrok tunnel...")

    ngrok_domain = os.getenv("NGROK_DOMAIN", "").replace("https://", "").replace("http://", "")
    if not ngrok_domain:
        print("  ⚠️  NGROK_DOMAIN not set in .env")
        return False

    try:
        response = requests.get(f"https://{ngrok_domain}/_stcore/health", timeout=10)
        if response.status_code == 200:
            print(f"  ✓ Tunnel active at https://{ngrok_domain}")
            return True
        else:
            print(f"  ✗ Tunnel responding with status {response.status_code}")
            return False
    except requests.RequestException as e:
        print(f"  ✗ Cannot reach tunnel: {e}")
        return False

def check_production_url():
    """Check production URL."""
    print("🏛️  Checking production URL...")

    try:
        response = requests.get("https://ocapistaine.vaettir.locki.io/_stcore/health", timeout=10)
        if response.status_code == 200:
            print("  ✓ Production URL responding")
            return True
        else:
            print(f"  ⚠️  Status: {response.status_code}")
            return False
    except requests.RequestException as e:
        print(f"  ✗ Cannot reach production: {e}")
        return False

def main():
    print("=" * 60)
    print("🏛️  OCapistaine CORS Configuration Verification")
    print("=" * 60)
    print()

    checks = []

    # Check environment
    checks.append(("Environment Variables", check_env_vars()))
    print()

    # Check local Streamlit
    checks.append(("Local Streamlit", check_streamlit_health()))
    print()

    # Check ngrok
    checks.append(("Ngrok Tunnel", check_ngrok_tunnel()))
    print()

    # Check production
    checks.append(("Production URL", check_production_url()))
    print()

    # Summary
    print("=" * 60)
    print("📊 Summary")
    print("=" * 60)

    for name, passed in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status:10} {name}")

    all_passed = all(passed for _, passed in checks)
    print()

    if all_passed:
        print("🎉 All checks passed! Your CORS configuration is correct.")
        print()
        print("🌐 Access your app at:")
        ngrok_domain = os.getenv("NGROK_DOMAIN", "").replace("https://", "").replace("http://", "")
        if ngrok_domain:
            print(f"   • https://{ngrok_domain}")
        print("   • https://ocapistaine.vaettir.locki.io")
        return 0
    else:
        print("⚠️  Some checks failed. Please:")
        print("   1. Make sure CORS variables are set in .env")
        print("   2. Restart Streamlit to apply changes")
        print("   3. Check that ngrok is running with the correct domain")
        return 1

if __name__ == "__main__":
    sys.exit(main())
