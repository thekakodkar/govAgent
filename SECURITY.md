# Security Policy

## Reporting a Vulnerability

Please report security issues **privately** through GitHub Security Advisories:

https://github.com/thekakodkar/govAgent/security/advisories/new

Do not open a public GitHub issue, discussion, or pull request for a vulnerability, and do not post exploit details in email threads that are not encrypted.

Include, where you can, the affected version, a reproduction, and the impact. We will not ask you to withhold a well-reasoned public disclosure indefinitely, but we do ask for a coordinated window so a fix can be published first.

## Response Times

These are targets, not contractual SLAs:

| Step | Target |
| --- | --- |
| Acknowledge a private report | Within **3 business days** |
| Initial triage and severity assessment | Within **7 days** of the report |
| Fix or mitigation for critical issues in a supported release | Within **30 days** of confirmation, or a documented status update if more time is needed |
| Credit in the advisory (if you want it) | When the advisory is published |

If we cannot meet a target we will say so in the advisory thread and give a revised date.

## Supported Versions

Security fixes are provided for the latest minor release line of the published `govagent` library. Older lines receive fixes only when the issue is severe and a backport is practical.

| Version | Supported |
| --- | --- |
| 3.5.x | Yes (current) |
| 3.4.x | Security fixes until the first 3.6.x or 4.x release, whichever comes first |
| 3.3.x and earlier | No |
| Pre-release / untagged `main` | Best effort only; not a supported product channel |

The private control plane (`govagent-platform`) is out of scope for this public policy. This document covers the open-source `govagent` package only.

## Scope

In scope: the published `govagent` wheel and sdist, their declared dependencies as used by this repo, and the GitHub Actions workflows in this repository.

Out of scope: third-party model providers, a deployer's own policy files, Slack workspaces, Harbor registries, or systems you wrap with GovAgent.
