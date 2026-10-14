FROM ghcr.io/astral-sh/uv:0.10.2 AS uv
FROM python:3.13-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev && useradd --uid 10001 --create-home demo
COPY app ./app
COPY web ./web
USER demo
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')"
CMD ["/srv/.venv/bin/uvicorn", "app.main:build_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
