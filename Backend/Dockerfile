FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN addgroup --system agentstudio && adduser --system --ingroup agentstudio agentstudio
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
ENV EMBEDDING_CACHE_DIR=/app/.model-cache
RUN mkdir -p /app/.model-cache && \
    python -c "from fastembed import TextEmbedding; list(TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/app/.model-cache').embed(['model readiness']))" && \
    chown -R agentstudio:agentstudio /app/.model-cache
COPY alembic.ini ./
COPY migrations ./migrations

USER agentstudio
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
