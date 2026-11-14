# Publishing govagent

This document is for maintainers. Only the open-source `govagent` library is published to PyPI. Never publish `govagent-platform`.

## Current process (API token)

Releases are tagged as `vMAJOR.MINOR.PATCH` (annotated) after `main` is green. The `release` GitHub Actions workflow builds the sdist and wheel, generates a CycloneDX SBOM, signs the artifacts with Sigstore via GitHub OIDC, and attaches those files to the GitHub Release.

The package is then uploaded to PyPI with a project API token (`PYPI_API_TOKEN` / trusted local secret), and the install is verified in a clean virtualenv with `import govagent` and `govagent.__version__`.

`twine check` is required before upload.

## Sigstore signatures

The `release` workflow uses GitHub’s OIDC token and `sigstore/gh-action-sigstore-python`. The `.sigstore` bundles are attached to the GitHub Release for the matching tag. Verify a downloaded artifact with the [sigstore](https://www.sigstore.dev/) tooling against those bundles and the GitHub identity of this repository.

## Software bill of materials

CI generates a CycloneDX JSON SBOM on every `main` push (uploaded as a workflow artifact). The same generator runs on a release tag and the file `govagent-<version>.cdx.json` is attached to the GitHub Release.

## Switching PyPI to trusted publishing (attestations)

Token upload remains the supported path until a maintainer enables a **trusted publisher** on the PyPI project:

1. On PyPI, open the `govagent` project → Publishing → add a pending GitHub publisher:
   - Owner: `thekakodkar`
   - Repository: `govAgent`
   - Workflow: `release.yml`
   - Environment: `pypi` (create this GitHub Environment if you use one)
2. Confirm the pending publisher after the first successful trusted upload, or as PyPI instructs.
3. In `.github/workflows/release.yml`, uncomment the “Publish to PyPI (trusted publishing)” step. It uses `pypa/gh-action-pypi-publish` with `id-token: write` and does **not** use `PYPI_API_TOKEN`.
4. Remove the token from the maintainer publish procedure once the trusted upload has been verified, so there is only one publisher.

Trusted publishing is also how PyPI attaches **provenance attestations** to the project. Until that publisher is configured, token uploads will not produce those attestations; Sigstore bundles on the GitHub Release still provide a verifiable signature of the same files.
