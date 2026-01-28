#!/bin/bash
# Run Streamlit with dynamic CORS configuration

set -e

# Parse arguments
USE_NGROK=""
for arg in "$@"; do
    case $arg in
        --ngrok)
            USE_NGROK="true"
            shift
            ;;
        --no-ngrok)
            USE_NGROK="false"
            shift
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🏛️  Starting OCapistaine Streamlit App"
echo ""

# Load .env file
if [ -f "$PROJECT_ROOT/.env" ]; then
    # Filter out comments and empty lines, then export
    while IFS= read -r line || [ -n "$line" ]; do
        if [[ ! "$line" =~ ^# ]] && [[ -n "$line" ]]; then
            export "$line"
        fi
    done < "$PROJECT_ROOT/.env"
    echo "✓ Loaded .env configuration"
else
    echo "⚠️  Warning: No .env file found, using defaults"
fi

# Set port
STREAMLIT_PORT=${STREAMLIT_PORT:-8502}

# Check if current user is admin (only admin can use ngrok)
GIT_USER_EMAIL=$(git config user.email || echo "")
ADMIN_EMAIL="jeannoel.schilling@gmail.com"
IS_ADMIN=false
if [ "$GIT_USER_EMAIL" == "$ADMIN_EMAIL" ]; then
    IS_ADMIN=true
fi

# Ask for ngrok if not specified and NGROK_DOMAIN exists and user is admin
if [ -z "$USE_NGROK" ] && [ -n "$NGROK_DOMAIN" ]; then
    if [ "$IS_ADMIN" = true ]; then
        echo -n "❓ Do you want to start an ngrok tunnel? (y/N): "
        read -n 1 answer
        echo ""
        if [[ "$answer" =~ ^[Yy]$ ]]; then
            USE_NGROK="true"
        else
            USE_NGROK="false"
        fi
    else
        echo "ℹ️  Ngrok tunnel restricted to admin users, skipping."
        USE_NGROK="false"
    fi
fi
export USE_NGROK

# Set Streamlit environment variables dynamically
echo "🔧 Configuring CORS..."
eval $(poetry run python "$SCRIPT_DIR/set_streamlit_env.py")

# Kill any existing process on the port
if lsof -ti:$STREAMLIT_PORT > /dev/null 2>&1; then
    echo "⚠️  Port $STREAMLIT_PORT is in use, killing existing process..."
    kill -9 $(lsof -ti:$STREAMLIT_PORT) 2>/dev/null || true
    sleep 1
    echo "✓ Port $STREAMLIT_PORT is now free"
fi

# Start ngrok in background if requested
NGROK_PID=""
if [ "$USE_NGROK" = "true" ]; then
    echo "🌐 Starting ngrok tunnel..."
    poetry run python "$SCRIPT_DIR/start_ngrok.py" > /tmp/ngrok_stream.log 2>&1 &
    NGROK_PID=$!
    echo "✓ Ngrok started (PID: $NGROK_PID)"
    
    # Setup cleanup trap to kill ngrok when script exits
    trap 'echo -e "\n🛑 Stopping Streamlit and ngrok..."; kill $NGROK_PID 2>/dev/null || true; exit' SIGINT SIGTERM EXIT
else
    echo "⏩ Skipping ngrok tunnel"
    # Simple cleanup trap for Streamlit only
    trap 'echo -e "\n🛑 Stopping Streamlit..."; exit' SIGINT SIGTERM EXIT
fi

echo ""
echo "----------------------------------------------------------------"
echo "🚀 OCapistaine is ready!"
echo "   Local URL:  http://localhost:$STREAMLIT_PORT"

# Show public proxy if ngrok is started
if [ "$USE_NGROK" = "true" ]; then
    echo "   Public URL: https://ocapistaine.vaettir.locki.io"
fi
echo "----------------------------------------------------------------"

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
