# Release image for govagent-platform 0.3.0.
# Installs govagent from PyPI. It does not copy src/govagent and it does not use the path dependency.
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "govagent[enterprise]==3.0.3" \
    "fastapi>=0.100.0" \
    "uvicorn>=0.22.0" \
    "sqlalchemy>=2.0.0" \
    "alembic>=1.13.0" \
    "psycopg[binary]>=3.1.0" \
    "pydantic>=2.0.0" \
    "bcrypt>=4.0.0" \
    "opentelemetry-api>=1.15.0" \
    "opentelemetry-sdk>=1.15.0" \
    && python -m spacy download en_core_web_lg

COPY pyproject.toml README.md CHANGELOG.md /app/platform/
COPY govagent_platform /app/platform/govagent_platform
COPY migrations /app/platform/migrations
COPY alembic.ini /app/platform/alembic.ini

WORKDIR /app/platform
RUN pip install --no-cache-dir --no-deps .

ENV PLATFORM_LLM_PROVIDER=scripted
EXPOSE 8070
CMD ["uvicorn", "govagent_platform.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8070"]
