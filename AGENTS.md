# Repository working agreement

## TL;DR

- Read `CONTRIBUTING.md`; it is the canonical workflow policy.
- Preserve immutable release identities, least privilege and declarative ownership boundaries.
- Keep deployable bundles, reusable charts, synthetic fixtures and local execution distinct.
- Run the exact checks and report their results honestly.

This file is the concise, tool-facing entry point for contributors and coding agents.
[CONTRIBUTING.md](CONTRIBUTING.md) is the canonical workflow policy. Normative terms such as MUST,
SHOULD and MAY have the meanings defined there.

## Before changing anything

1. You MUST read [CONTRIBUTING.md](CONTRIBUTING.md), especially its ambiguity, issue-timing,
   verification and external-side-effect rules.
2. You MUST inspect the branch and working tree and preserve pre-existing work.
3. You MUST read the relevant
   [engineering standards](docs/development/engineering-standards.md), bundle documentation, chart
   values/schema, operational guides, contract lock and accepted [ADRs](docs/decisions/README.md).
4. You MUST use repository-local checks and MUST NOT claim an unavailable or unexecuted check
   passed.

If charts, bundles, hashes, runtime-loader behavior and documentation disagree, you MUST NOT
silently pick one. Correct an obvious local defect or create a new immutable bundle/accepted ADR.
Ordinary ambiguity follows CONTRIBUTING.

## Repository responsibility

`perfeng-k8s` owns reviewed deployable runtime-registry bundles, reusable Kubernetes charts,
platform workload definitions, immutable component/configuration promotion and offline deployment
validation. It does not own application code, shared contract definitions, component image builds,
Secrets, live-cluster reconciliation or the disposable local kind environment.

- Deployable bundles bind exact files, hashes, images, principals and environment identities.
- Charts require callers to supply environment selection and externally managed configuration and
  credentials.
- Synthetic values and files under `testdata` prove validation only and are never deployment input.
- `perfeng-environment` owns local composition and Argo CD bootstrap; the control plane owns runtime
  interpretation of the registry bundle.

## Shape of work

- Each task and pull request MUST deliver one coherent, independently reviewable deployment or
  promotion outcome.
- Runtime promotion, chart behavior, validator upgrades, dependencies and broad cleanup MUST stay
  separate unless inseparable for correctness.
- Scope, assumptions, immutable identities, authorization, compatibility, affected environments,
  rollout/recovery and verification evidence MUST be explicit.
- Prefer a complete reviewed bundle or chart behavior over placeholders and floating selections.

## Deployment and implementation rules

- Published bundle versions are immutable. Corrections produce a new version; do not rewrite a
  previously promoted identity.
- Use final registry manifest digests and exact content hashes. Mutable tags and digest-shaped
  placeholders are not deployment configuration.
- Candidate, runner, normalizer and reporter identities remain internally consistent and are
  independently verifiable.
- Principals, RBAC, ServiceAccounts and cross-namespace permissions are authorization data and
  receive focused review.
- Charts do not create Secrets, authentication documents or environment-owned ConfigMaps.
- Separate credential-free compute from narrowly privileged transfer/publisher containers.
- Jobs and Pods define non-root execution, dropped capabilities, read-only filesystems, bounded
  resources/storage and explicit lifecycle behavior.
- Direct benchmark execution is opt-in, confirms an exact context and remains limited to explicitly
  authorized disposable targets.

Follow the engineering standards and relevant README sections.

## Quality and documentation

- Validate on Windows and Linux when path, archive or rendering behavior is portable platform
  surface.
- Prove charts through strict linting, schema validation and rendered-object assertions; do not rely
  on template appearance.
- Validate every deployable bundle with both repository checks and the exact pinned control-plane
  runtime loader.
- Comments SHOULD explain ownership, security, promotion or compatibility constraints and SHOULD
  NOT narrate syntax or silence lint findings.
- Long documents MUST include the TL;DR required by CONTRIBUTING.
- Bundle files, checksums, provenance, charts, fixtures, tests and documentation change together.

## Completion

The canonical required checks and completion-report format are defined in
[CONTRIBUTING.md](CONTRIBUTING.md). Follow them after every work item.
