FROM ghcr.io/astral-sh/uv:python3.13-alpine

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

COPY temperature_forwarder.py .

CMD ["/app/.venv/bin/python", "temperature_forwarder.py"]
