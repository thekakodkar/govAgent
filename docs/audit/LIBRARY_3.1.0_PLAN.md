# govagent 3.1.0 plan

Status: documentation only. Do not implement this file in the 3.0.3 line, and do not publish it from the platform work.

The platform stays pinned to `govagent>=3.0.3,<3.1.0` until this release exists and the platform suite has been run against it. None of the items below are backward-compatible with the behavior 3.0.3 documents today.

## Policy YAML projection

`Policy.__init__` reads top-level `global_limits`. A document that only sets `fiscal_governance.global_limits` still leaves the code default daily budget of `10.0`. The platform copies those nested keys onto the instance in `hydrate_policy` after construction.

3.1.0 would teach `Policy` to project `fiscal_governance.global_limits` and `alignment` onto the attributes `ExecutiveAgent` already reads (`global_limits`, `alignment`). Callers that relied on the `10.0` default while also sending a nested ceiling would suddenly enforce the nested ceiling. That is a behavior change, not a new optional argument.

Files: `src/govagent/policy.py`, `tests/test_policy_projection.py`. The platform could then stop patching the instance, but only after the pin moves to `>=3.1.0`.

## Real Harbor client

`HarborVerifier` accepts a `mock-token` and otherwise returns `PRODUCTION_BYPASS` unless the repository name contains `malicious`. A 3.1.0 client would call a Harbor HTTP API with a real token and fail closed when the registry is unreachable. Tools that pass today because of the bypass would start failing. That changes who is allowed to run an OCI-backed tool.

Files: `src/govagent/registry/harbor_verifier.py`, `tests/test_harbor_registry.py`. The platform keeps calling the 3.0.3 verifier until that client ships.

## Evidence and CFO as public exports

`CFOAnalyticsEngine` and `EvidencePackGenerator` live under `src/govagent/governance/` and are inside the wheel. `governance/__init__.py` exports only `MetaGovernor`. The platform imports the modules as private API and fills `ComplianceDossier` from SQL rows.

3.1.0 would add both names to `__all__` and document them. That freezes the constructor and the JSON shapes. The file-based `EvidencePackGenerator.generate` reads a JSONL buffer and is not tenant-aware. Promoting it does not make it safe as a multi-tenant exporter. The platform dossier should keep reading SQL even after the export exists.

Files: `src/govagent/governance/__init__.py`, `tests/test_governance_exports.py`, README. The wheel-layout test that rejects those names in `__init__.py` has to be updated in the same release, not before.

## Release order when an owner approves the behavior changes

1. Implement the three items on a library branch. Do not mix them into a platform-only commit.
2. Run the library suite and the platform suite against the branch.
3. Bump the library to `3.1.0`, changelog, tag, and publish only after that approval.
4. Move the platform pin to `>=3.1.0,<3.2.0` in a later platform commit and drop `hydrate_policy`'s copies of the keys `Policy` now reads itself.
