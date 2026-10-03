# Build stage: installs the locked runtime dependencies into a virtual environment.
FROM ghcr.io/astral-sh/uv:0.12.23-python3.14-trixie-slim AS build

# Compile to bytecode ahead of time for a faster start, copy files out of the cache rather
# than linking to it, and use the image's own Python instead of downloading one.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-default-groups


# Runtime stage: the virtual environment and the package, without uv or the build tools.
# The build image is based on this one, so the environment's Python path is the same.
FROM python:3.14-slim-trixie

RUN groupadd --system satara \
    && useradd --system --gid satara --no-create-home satara

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY satara /app/satara
COPY scripts/consumer.py /app/scripts/consumer.py

# The package is not installed, so a script run from `scripts/` finds it through the path.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER satara
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", \
    "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# The list form runs the server directly, without a shell, so it receives the stop signal.
CMD ["uvicorn", "--factory", "satara.wiring:create_app", "--host", "0.0.0.0", "--port", "8000"]
