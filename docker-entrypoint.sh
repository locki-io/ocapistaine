#!/bin/bash
set -e

# OCapistaine Docker Entrypoint
# Starts both Streamlit UI and FastAPI backend

echo "Starting OCapistaine services..."

# Start FastAPI in background
echo "Starting FastAPI on port 8050..."
uvicorn app.main:app --host 0.0.0.0 --port 8050 &
FASTAPI_PID=$!

# Give FastAPI a moment to start
sleep 2

# Start Streamlit in foreground
echo "Starting Streamlit on port 8502..."
streamlit run app/front.py \
    --server.port 8502 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false &
STREAMLIT_PID=$!

# Handle shutdown gracefully
trap "kill $FASTAPI_PID $STREAMLIT_PID 2>/dev/null; exit 0" SIGTERM SIGINT

echo "OCapistaine is running!"
echo "  - Streamlit UI: http://localhost:8502"
echo "  - FastAPI docs: http://localhost:8050/docs"

# Wait for either process to exit
wait -n $FASTAPI_PID $STREAMLIT_PID

# If one exits, kill the other
kill $FASTAPI_PID $STREAMLIT_PID 2>/dev/null
