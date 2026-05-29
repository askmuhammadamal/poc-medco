# Modbus middleware + dashboard (single FastAPI service).
FROM python:3.12-slim

WORKDIR /app

# Runtime deps (kept in sync with pyproject.toml). Installed first for layer caching.
RUN pip install --no-cache-dir \
    "pymodbus==3.7.4" \
    "fastapi>=0.115,<1.0" \
    "uvicorn[standard]>=0.34,<1.0" \
    "pyyaml>=6.0"

# Run from source so STATIC_DIR (../static) resolves and logs/ land under /app.
COPY driftwatch ./driftwatch
COPY static ./static
COPY config.example.yaml ./

EXPOSE 8000

# Bind 0.0.0.0 so the dashboard is reachable from outside the container.
# Mode/transport/target come from DW_* env (see docker-compose.yml).
ENTRYPOINT ["python", "-m", "driftwatch", "--http-host", "0.0.0.0"]
