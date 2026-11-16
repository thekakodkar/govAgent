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

# Run as an unprivileged user, not root.
RUN groupadd --gid 10001 govagent \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin govagent \
    && install -d -o 10001 -g 10001 /app/logs \
    && chown -R 10001:10001 /app

ENV PYTHONPATH=/app/src:/app
# Required at runtime for the sandbox API. There is no default token.
# ENV GOVAGENT_SECRET_TOKEN=
EXPOSE 8000
USER 10001:10001

CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
