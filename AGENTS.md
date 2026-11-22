# Repository agent guide

## Agent skills

Use `mattpocock/skills` as the primary workflow for planning, ticketing,
implementation, TDD, review, and pull requests. The skills take precedence where
contributor guidance covers the same steps. Follow the repository's technical
requirements, CI gates, and authorization boundaries.

### Issue tracker

Use GitHub Issues in `stanimirivanov/perfeng-k8s`. See [issue tracker configuration](docs/agents/issue-tracker.md).

### Triage labels

Use the default Matt Pocock label mapping. See [triage labels](docs/agents/triage-labels.md).

### Domain docs

Single context with a root glossary and ADRs in `docs/decisions/`. See [domain docs](docs/agents/domain.md).

## Repository responsibility

`perfeng-k8s` owns reviewed deployable runtime-registry bundles, reusable Kubernetes charts,
platform workload definitions, immutable component/configuration promotion and offline deployment
validation. It also packages the reviewed upstream kube-burner executable with the small
contained execution/capture/publication adapters documented in ADR 0002. It does not own application
benchmark engines, shared contract definitions, other component image builds,
Secrets, live-cluster reconciliation or the disposable local kind environment.

- Deployable bundles bind exact files, hashes, images, principals and environment identities.
- Charts require callers to supply environment selection and externally managed configuration and
  credentials.
- Synthetic values and files under `testdata` prove validation only and are never deployment input.
- `perfeng-environment` owns local composition and Argo CD bootstrap; the control plane owns runtime
  interpretation of the registry bundle.

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

- Validate on Linux when path, archive or rendering behavior is portable platform
  surface.
- Prove charts through strict linting, schema validation and rendered-object assertions; do not rely
  on template appearance.
- Validate every deployable bundle with both repository checks and the exact pinned control-plane
  runtime loader.
- Comments SHOULD explain ownership, security, promotion or compatibility constraints and SHOULD
  NOT narrate syntax or silence lint findings.
- Long documents MUST include the TL;DR required by CONTRIBUTING.
- Bundle files, checksums, provenance, charts, fixtures, tests and documentation change together.

## Verification

Run `make verify` and the applicable additional checks documented in
[CONTRIBUTING.md](CONTRIBUTING.md#verification-and-constrained-environments).
Use the [documentation map](docs/README.md) to find affected standards, operational
guides and decisions. Report checks as passed, failed or unavailable.
