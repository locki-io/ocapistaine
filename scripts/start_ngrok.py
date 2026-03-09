#!/usr/bin/env python3
"""
Start ngrok tunnel for Streamlit apps.

Usage:
    python scripts/start_ngrok.py                    # Training center (port 8502, NGROK_DOMAIN)
    python scripts/start_ngrok.py --chat             # Chat (port 8503, NGROK_CHAT_DOMAIN)
    python scripts/start_ngrok.py --port 8503 --domain ocap-beta.ngrok-free.app
"""
import argparse
import os
import re
import subprocess
import sys
from dotenv import load_dotenv

load_dotenv()

parser = argparse.ArgumentParser(description="Start ngrok tunnel")
parser.add_argument("--chat", action="store_true", help="Launch chat tunnel (port 8503)")
parser.add_argument("--port", type=int, default=None, help="Override port")
parser.add_argument("--domain", type=str, default=None, help="Override domain")
args = parser.parse_args()

if args.chat:
    PORT = args.port or int(os.getenv("CHAT_PORT", "8503"))
    NGROK_DOMAIN = args.domain or os.getenv("NGROK_CHAT_DOMAIN", "")
    label = "Chat"
else:
    PORT = args.port or int(os.getenv("STREAMLIT_PORT", "8502"))
    NGROK_DOMAIN = args.domain or os.getenv("NGROK_DOMAIN", "")
    label = "Training Center"

if not NGROK_DOMAIN:
    print(f"Warning: No domain set for {label}. Using random ngrok URL.")

print(f"Starting ngrok tunnel ({label}) on port {PORT}… (Ctrl+C to stop)")

# Build ngrok command
ngrok_cmd = ["ngrok", "http", f"http://localhost:{PORT}", "--log=stdout"]
if NGROK_DOMAIN:
    ngrok_cmd.insert(3, f"--domain={NGROK_DOMAIN}")
    print(f"Fixed domain: https://{NGROK_DOMAIN}")

process = subprocess.Popen(
    ngrok_cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    universal_newlines=True,
)

url_pattern = re.compile(r"https?://[a-z0-9-]+\.ngrok(?:-free)?\.(?:io|app)")

for line in process.stdout:
    print(line, end="")

    # Show URL when detected (for random domains)
    if not NGROK_DOMAIN and (match := url_pattern.search(line)):
        print(f"\n→ Public URL: {match.group(0)}\n")

try:
    process.wait()
except KeyboardInterrupt:
    print("\nShutting down ngrok…")
    process.terminate()
