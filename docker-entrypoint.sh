#!/bin/bash
set -e

# OCapistaine Docker Entrypoint
# Starts both Streamlit UI and FastAPI backend
# Render.com: Uses PORT env var for primary service (Streamlit)

echo "Starting OCapistaine services..."

# Render provides PORT env var - use it for Streamlit (the public-facing UI)
# Default to 8502 if not set (local development)
STREAMLIT_PORT=${PORT:-8502}
FASTAPI_PORT=${FASTAPI_PORT:-8050}

# Start FastAPI in background (internal API)
echo "Starting FastAPI on port $FASTAPI_PORT..."
uvicorn app.main:app --host 0.0.0.0 --port $FASTAPI_PORT &
FASTAPI_PID=$!

# Give FastAPI a moment to start
sleep 2

# Streamlit CORS settings from environment
ENABLE_CORS=${STREAMLIT_SERVER_ENABLE_CORS:-true}
ENABLE_XSRF=${STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION:-false}

# Start Streamlit on the main PORT (public-facing)
echo "Starting Streamlit on port $STREAMLIT_PORT..."
echo "  CORS enabled: $ENABLE_CORS"
echo "  XSRF protection: $ENABLE_XSRF"

streamlit run app/front_chat.py \
    --server.port $STREAMLIT_PORT \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS $ENABLE_CORS \
    --server.enableXsrfProtection $ENABLE_XSRF \
    --browser.gatherUsageStats false &
STREAMLIT_PID=$!

# Handle shutdown gracefully
trap "kill $FASTAPI_PID $STREAMLIT_PID 2>/dev/null; exit 0" SIGTERM SIGINT

echo ""
echo "OCapistaine is running!"
echo "  - Streamlit UI: http://0.0.0.0:$STREAMLIT_PORT"
echo "  - FastAPI docs: http://0.0.0.0:$FASTAPI_PORT/docs"
echo ""

# Wait for either process to exit
wait -n $FASTAPI_PID $STREAMLIT_PID

# If one exits, kill the other
kill $FASTAPI_PID $STREAMLIT_PID 2>/dev/null
