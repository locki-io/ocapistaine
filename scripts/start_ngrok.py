#!/usr/bin/env python3
import os
import re
import subprocess
import sys
import time
from dotenv import load_dotenv

load_dotenv()

try:
    import pyperclip
except ImportError:
    print("pyperclip not found. Run: poetry add pyperclip --group dev")
    sys.exit(1)

# Change this port if your .env (or other) app uses a different one
PORT = int(os.getenv("STREAMLIT_PORT", "8501"))
# Set a fixed ngrok domain (requires paid plan with reserved domain)
NGROK_DOMAIN = os.getenv("NGROK_DOMAIN", "")

print("Starting ngrok tunnel… (Ctrl+C to stop)")

# Build ngrok command
ngrok_cmd = ["ngrok", "http", f"http://localhost:{PORT}", "--log=stdout"]
if NGROK_DOMAIN:
    ngrok_cmd.insert(3, f"--domain={NGROK_DOMAIN}")
    print(f"Using fixed domain: {NGROK_DOMAIN}")

# This works perfectly with Poetry because `poetry run` or `poetry shell` puts ngrok in PATH if you also added it as dev dependency
process = subprocess.Popen(
    ngrok_cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    universal_newlines=True,
)

url_pattern = re.compile(r"https?://[a-z0-9-]+\.ngrok(?:-free)?\.(?:io|app)")

found = False
for line in process.stdout:
    print(line, end="")

    if not found and (match := url_pattern.search(line)):
        url = match.group(0)
        pyperclip.copy(url)
        print(f"\nPublic URL copied to clipboard: {url}")
        found = True

# Keep running until you press Ctrl+C
try:
    process.wait()
except KeyboardInterrupt:
    print("\nShutting down ngrok…")
    process.terminate()
