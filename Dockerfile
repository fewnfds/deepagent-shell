# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

FROM node:22-bookworm-slim@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3 AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm --prefix frontend ci
COPY frontend ./frontend
RUN npm --prefix frontend run build

FROM ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa AS uv

FROM python:3.12.9-slim-bookworm@sha256:48a11b7ba705fd53bf15248d1f94d36c39549903c5d59edcfa2f3f84126e7b44 AS python-build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
COPY server/pyproject.toml server/uv.lock server/README.md ./server/
COPY server/src ./server/src
COPY --from=frontend-build /build/server/src/agent_shell/frontend_dist \
    ./server/src/agent_shell/frontend_dist
RUN uv sync --project /build/server --locked --no-dev --no-editable \
    && find /opt/venv -name direct_url.json -type f -delete \
    && test -z "$(find /opt/venv -name direct_url.json -type f -print -quit)"

FROM python:3.12.9-slim-bookworm@sha256:48a11b7ba705fd53bf15248d1f94d36c39549903c5d59edcfa2f3f84126e7b44 AS runtime
LABEL org.opencontainers.image.source="https://github.com/fewnfds/agent-shell" \
      org.opencontainers.image.licenses="MIT"
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/app/runtime/home \
    XDG_CACHE_HOME=/app/runtime/cache
RUN useradd --uid 10001 --user-group --create-home --shell /usr/sbin/nologin agent-shell
WORKDIR /app
COPY --from=python-build /opt/venv /opt/venv
COPY --chown=10001:10001 .env.example README.md LICENSE THIRD_PARTY_NOTICES.md ./
RUN mkdir -p data runtime/cache runtime/tmp runtime/home \
    && chown -R 10001:10001 /app
USER 10001:10001
EXPOSE 19100
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-I", "-B", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('AGENT_SHELL_PORT', '19100') + '/api/health', timeout=2).read()"]
CMD ["python", "-I", "-B", "-m", "agent_shell", "--home", "/app", "--data-dir", "/app/data", "--mode", "portable"]
