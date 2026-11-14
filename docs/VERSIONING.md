# Versioning and deprecation policy

govAgent follows [Semantic Versioning](https://semver.org/) for the published `govagent` package: **MAJOR.MINOR.PATCH**.

The version in `pyproject.toml` is the source of truth and is exposed as `govagent.__version__`.

## What counts as a break

A **major** release may remove or change documented public behavior in a way that requires callers to edit their code or their policy documents.

A **minor** release may add features, extras, or documented fields. It may also change behavior when the previous behavior was a bug that violated the published contract, and that change must be recorded under “Behavior changes” in `changelog.md`.

A **patch** release fixes defects, documentation, or packaging without changing the public contract.

The public contract is the top-level `govagent.__all__` exports, the documented attributes of `Policy` and `ExecutionSnapshot`, and the optional extras named in `pyproject.toml`. Repo-local paths such as `api/server.py` are not part of the published wheel and may change in a minor release.

## Deprecation window

Breaking changes land **only in a major version**. Before a public API is removed or its contract changes incompatibly, it is marked deprecated in a **minor** release and remains callable for **at least one subsequent minor** (for example: deprecated in 3.5, still present in 3.6, eligible for removal in 4.0).

The deprecation must appear in `changelog.md` and, where practical, as a `DeprecationWarning` at the call site. After the window, removal happens in the next major.

Security fixes may land as patches on a supported line without waiting for that window when leaving the old behavior in place would keep a vulnerability open. See [SECURITY.md](../SECURITY.md).

## Pre-release and `main`

Untagged commits on `main` are not a release. Do not treat them as a supported version until they appear in a tagged PyPI release. Alpha or release-candidate tags, if used, will carry a SemVer pre-release suffix and are not covered by the deprecation window.
