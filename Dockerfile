FROM python:3.11-slim

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY services/aquavision-service/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r /build/requirements.txt

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=0 /build/wheels /tmp/wheels
COPY services/aquavision-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r /tmp/requirements.txt && \
    rm -rf /tmp/wheels

COPY services/aquavision-service/ /app/

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=120s \
    CMD curl -f http://localhost:${PORT:-8100}/health/live || exit 1

RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
