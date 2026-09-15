FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /uvx /bin/

WORKDIR /app

# Instala dependencias antes de copiar el código para cachear la capa.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY knowledge ./knowledge
RUN uv sync --frozen --no-dev

RUN useradd --create-home appuser && mkdir -p /app/output && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "serve"]
