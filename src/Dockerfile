FROM python:3.13-slim

ARG APP_UID=10001
ARG APP_GID=10001
ARG DOCKER_SOCKET_GID=0

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.10.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/tmp

RUN groupadd --gid "${APP_GID}" app \
    && if ! getent group "${DOCKER_SOCKET_GID}" > /dev/null; then \
        groupadd --gid "${DOCKER_SOCKET_GID}" docker-socket; \
    fi \
    && DOCKER_SOCKET_GROUP="$(getent group "${DOCKER_SOCKET_GID}" | cut -d: -f1)" \
    && useradd \
        --uid "${APP_UID}" \
        --gid app \
        --home-dir /app \
        --no-create-home \
        --shell /usr/sbin/nologin \
        app \
    && usermod --append --groups "${DOCKER_SOCKET_GROUP}" app

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev \
    && chown -R app:app /app

COPY --chown=app:app src ./src

USER app

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
