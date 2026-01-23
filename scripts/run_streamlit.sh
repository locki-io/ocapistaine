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
eval $(python "$SCRIPT_DIR/set_streamlit_env.py")

# Show port
STREAMLIT_PORT=${STREAMLIT_PORT:-8502}
echo ""
echo "✓ Streamlit will run on: http://localhost:$STREAMLIT_PORT"

# Show ngrok domain if configured
if [ -n "$NGROK_DOMAIN" ]; then
    echo "✓ Ngrok domain: https://$NGROK_DOMAIN"
fi

echo ""
echo "Starting Streamlit..."
echo "---"

# Run Streamlit
cd "$PROJECT_ROOT"
streamlit run app/front.py \
    --server.port "$STREAMLIT_PORT" \
    --server.address "0.0.0.0"
