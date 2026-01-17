#!/bin/bash

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Default port if not set
UVICORN_PORT=${UVICORN_PORT:-8050}

echo "Terminating stale Uvicorn processes on port $UVICORN_PORT..."
PIDS=$(lsof -t -i :$UVICORN_PORT 2>/dev/null || ps aux | grep -E "[u]vicorn.*app.main" | grep -v grep | awk '{print $2}')

if [ -n "$PIDS" ]; then
    for PID in $PIDS; do
        echo "Terminating process $PID"
        kill -15 "$PID" 2>/dev/null
        sleep 1
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Force terminating process $PID"
            kill -9 "$PID" 2>/dev/null
        fi
    done
else
    echo "No stale Uvicorn processes found"
fi

if ! lsof -t -i :$UVICORN_PORT > /dev/null 2>&1; then
    echo "Clearing Redis locks..."
    # redis-cli DEL scheduler:lock event_loop:lock 2>/dev/null
    # redis-cli KEYS "lock:*" | xargs redis-cli DEL 2>/dev/null
else
    echo "Warning: app still running on port $UVICORN_PORT, skipping Redis cleanup"
fi

# Start app in development mode
echo "Starting Ò Capistaine API on port $UVICORN_PORT..."
poetry run uvicorn app.main:app --reload --port $UVICORN_PORT &
UVICORN_PID=$!
echo "Uvicorn running with PID $UVICORN_PID"
