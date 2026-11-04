# Repo development image. This is not the minimal govagent wheel.
# Presidio's AnalyzerEngine expects: python -m spacy download en_core_web_lg
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock README.md ./
COPY src ./src
COPY api ./api
COPY policies ./policies

RUN poetry config virtualenvs.create false \
    && poetry install --with dev --extras enterprise --no-interaction --no-ansi

ENV PYTHONPATH=/app/src:/app
EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
