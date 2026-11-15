# One image for both the API and the Celery worker; the command differs per service.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

RUN useradd --create-home --uid 1000 app

# Install dependencies first so code changes don't bust the dependency layer.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
    && pip install ".[dev]" \
    && pip uninstall -y analytica-backend \
    && rm -rf app build *.egg-info

COPY . .

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
