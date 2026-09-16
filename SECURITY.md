# Security policy

## TL;DR

- Do not disclose suspected vulnerabilities in public issues or pull requests.
- Use GitHub private vulnerability reporting when available.
- If no private channel exists, request one without sensitive details.
- The project is pre-release; only the current default branch is supported.
- Do not apply manifests or run benchmarks against systems you are not authorized to modify.

## Supported versions

The deployment configuration has no supported production release. Security fixes target the current
default branch and new bundle versions; previously published bundle bytes remain historical. Replace
this section with an explicit supported-version and promotion policy when stable releases begin.

## Reporting a vulnerability

Use the repository Security page's **Report a vulnerability** action when it is available. If
private reporting is unavailable, do not publish the report. Request a private channel without
naming the vulnerable component, exploit, affected cluster/data or reproduction details.

Include the affected revision, bundle/chart/environment, impact and preconditions, minimal
reproduction, sanitized evidence, known mitigations, and prior disclosure where applicable. Do not
retain, alter or disclose accessed data beyond what is necessary to demonstrate the issue safely.

## Triage and disclosure

Maintainers SHOULD acknowledge a private report, validate severity and scope, and agree on
communication before disclosure. Response times are best-effort until a staffed process exists.
Coordinate disclosure after a fix or effective mitigation. Good-faith reports SHOULD be handled
respectfully.

## Security expectations for contributions

Contributors MUST follow the authorization, least-privilege, secret/configuration ownership,
untrusted-input, dependency and verification requirements in [CONTRIBUTING.md](CONTRIBUTING.md) and
the [engineering standards](docs/development/engineering-standards.md). Changes to principals, RBAC,
ServiceAccounts, namespace boundaries, credential-bearing containers, image identities, artifact
publication, chart inputs, native execution or cluster reconciliation MUST document their threat
and failure model and receive focused security review.
