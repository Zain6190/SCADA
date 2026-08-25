# ── Stage 1: Build Python wheels ────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for compiling native extensions (psycopg2, xgboost, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /build/requirements.txt

# Build all wheels into /build/wheels (cached by Docker layer)
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r /build/requirements.txt

# ── Stage 2: Lean runtime image ────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Runtime system deps only (libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Install pre-built wheels from builder stage (no compilation needed)
COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r /tmp/wheels/../requirements.txt && \
    rm -rf /tmp/wheels

# Copy application code
COPY . /app/

# Expose port
EXPOSE 8100

# Health check (uses PORT env var at runtime)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=120s \
    CMD curl -f http://localhost:${PORT:-8100}/health/live || exit 1

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Run setup + API
CMD ["/app/entrypoint.sh"]
