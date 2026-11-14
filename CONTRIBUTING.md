# Contributing to govAgent

Thank you for contributing. This repository publishes the open-source `govagent` library. Please keep changes backward compatible unless you are deliberately making a major-version break, and document any behavior change in `changelog.md`. See [docs/VERSIONING.md](docs/VERSIONING.md) for the deprecation policy.

## Development setup

```bash
poetry install --with dev --extras "crewai enterprise mcp"
python -m spacy download en_core_web_lg
```

Optional extras for local work: `openai`, `anthropic`.

## Checks we run on `main`

Run the same gates as CI before you open a change:

```bash
poetry run ruff check src/govagent
poetry run mypy src/govagent
poetry run pytest -v --tb=short --asyncio-mode=auto
# wheel layout (also run on Python 3.12 in CI)
poetry run pytest tests/test_wheel_layout.py -v --tb=short
```

`tests/test_readme_contract.py` asserts that `docs/index.html` stays consistent with the public API. When you edit the docs page, change **text only** unless a visual change is explicitly requested; do not restyle the landing page as a side effect of a docs typo fix.

## Live tests

Tests marked `live` call real services or a local official MCP server:

```bash
poetry run pytest -m live -v --tb=short
```

- `GovernedMCPGateway` against a local stdio MCP server needs the `mcp` extra and no API keys. It runs in the default suite whenever `mcp` is installed.
- `OpenAIClient`, `AzureOpenAIClient`, and `AnthropicClient` live tests skip unless the matching environment keys are set (`OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT` or `AZURE_OPENAI_MODEL`, `ANTHROPIC_API_KEY`). Never commit or print those values.

## Pull requests and issues

- Open an issue first for design or security-adjacent work. **Vulnerabilities must go through [SECURITY.md](SECURITY.md)** (GitHub Security Advisories), not a public issue.
- Include tests for new behavior. Prefer mocked network I/O in the default suite.
- Do not publish packages, create tags, or change PyPI credentials from a contribution unless a maintainer asks you to.

## Supply chain and releases

Release process, Sigstore signatures, SBOMs, and how a maintainer can switch PyPI to trusted publishing are documented in [docs/PUBLISHING.md](docs/PUBLISHING.md).
