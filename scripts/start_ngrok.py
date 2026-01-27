#!/usr/bin/env python3
"""
Start ngrok tunnel for Streamlit app.

Uses fixed domain from NGROK_DOMAIN env var (requires ngrok paid plan).
"""
import os
import re
import subprocess
import sys
from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("STREAMLIT_PORT", "8501"))
NGROK_DOMAIN = os.getenv("NGROK_DOMAIN", "")

if not NGROK_DOMAIN:
    print("Warning: NGROK_DOMAIN not set. Using random ngrok URL.")

print(f"Starting ngrok tunnel on port {PORT}… (Ctrl+C to stop)")

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
