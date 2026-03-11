# OCapistaine - Multi-service Docker Image
# Runs both Streamlit UI and FastAPI backend

FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    POETRY_VERSION=2.1.1 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

# Add poetry to path
ENV PATH="$POETRY_HOME/bin:$PATH"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Set working directory
WORKDIR /app

# Copy dependency files first (for layer caching)
COPY pyproject.toml poetry.lock* ./

# Install dependencies (no dev dependencies for production)
RUN poetry install --only main --no-root

# Copy application code
COPY . .

# Fetch docs submodule if not present (Render doesn't init submodules)
# docs/ contains audierne2026 documents needed for scheduled tasks
# Non-fatal: scheduler is disabled on Render, so docs are optional
RUN if [ ! -d docs/docs/audierne2026 ] || [ -z "$(ls -A docs/docs/audierne2026 2>/dev/null)" ]; then \
    echo "Fetching docs submodule..." && \
    rm -rf docs && \
    git clone --depth 1 https://github.com/locki-io/docs.locki.io.git docs && \
    echo "Docs submodule fetched successfully" || \
    echo "WARNING: Could not fetch docs submodule (private repo?) - scheduled tasks may not work"; \
    else \
    echo "Docs submodule already present"; \
    fi

# Create logs directory
RUN mkdir -p /app/logs

# Expose ports
# 8502 = Streamlit UI
# 8050 = FastAPI backend
EXPOSE 8502 8050

# Default command: run both services with a process manager
# Using a simple shell script to run both
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
