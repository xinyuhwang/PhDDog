FROM python:3.12-slim

RUN pip install --no-cache-dir uv

# Keep the virtualenv outside /app so the source bind mount doesn't hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
