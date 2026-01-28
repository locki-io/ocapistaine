#!/bin/bash
# Run Streamlit with dynamic CORS configuration

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🏛️  Starting OCapistaine Streamlit App"
echo ""

# Load .env file
if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
    echo "✓ Loaded .env configuration"
else
    echo "⚠️  Warning: No .env file found, using defaults"
fi

# Set Streamlit environment variables dynamically
echo "🔧 Configuring CORS..."
eval $(poetry run python "$SCRIPT_DIR/set_streamlit_env.py")

# Set port
STREAMLIT_PORT=${STREAMLIT_PORT:-8502}

# Kill any existing process on the port
if lsof -ti:$STREAMLIT_PORT > /dev/null 2>&1; then
    echo "⚠️  Port $STREAMLIT_PORT is in use, killing existing process..."
    kill -9 $(lsof -ti:$STREAMLIT_PORT) 2>/dev/null || true
    sleep 1
    echo "✓ Port $STREAMLIT_PORT is now free"
fi

echo ""
echo "✓ Streamlit will run on: http://localhost:$STREAMLIT_PORT"

# Show ngrok domain if configured
if [ -n "$NGROK_DOMAIN" ]; then
    echo "✓ Ngrok domain: https://$NGROK_DOMAIN"
fi

echo ""
echo "Starting Streamlit..."
echo "---"

# Add project root to PYTHONPATH for proper module resolution
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Run Streamlit via Poetry (ensures correct virtual environment)
cd "$PROJECT_ROOT"
poetry run streamlit run app/front.py \
    --server.port "$STREAMLIT_PORT" \
    --server.address "0.0.0.0"
