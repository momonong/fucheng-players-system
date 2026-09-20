FROM node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/tsconfig*.json frontend/vite.config.ts ./
COPY frontend/src ./src
RUN npm run build -- --outDir /built-static

FROM ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 AS uv
FROM python:3.14.6-slim-bookworm@sha256:4c92ffcde4dd6f1ff72a24518f49fd4990b27134987dfa31a733badde66df9f8 AS python-deps
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-editable --python /usr/local/bin/python

FROM scratch AS context-audit
COPY . /

FROM python:3.14.6-slim-bookworm@sha256:4c92ffcde4dd6f1ff72a24518f49fd4990b27134987dfa31a733badde66df9f8 AS runtime
ENV PATH=/app/.venv/bin:$PATH PYTHONPATH=/app/src PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 FUCHENG_STATIC_DIR=/app/static
WORKDIR /app
COPY --from=python-deps /app/.venv /app/.venv
COPY --from=frontend /built-static /app/static
COPY src/fucheng/*.py /app/src/fucheng/
COPY migrations /app/migrations
COPY alembic.ini /app/alembic.ini
COPY deploy/docker/runtime.py /app/runtime.py
COPY deploy/docker/source-manifest.json /app/source-manifest.json
ARG SOURCE_SHA256
LABEL org.opencontainers.image.title="Fucheng portable deployment" io.fucheng.source-manifest-sha256=$SOURCE_SHA256
RUN mkdir /data /backups && chown 10001:10001 /data /backups
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 CMD ["python", "/app/runtime.py", "health"]
ENTRYPOINT ["python", "/app/runtime.py"]
CMD ["serve"]
