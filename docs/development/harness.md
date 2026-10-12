# Perfeng Kubernetes coding harness

## TL;DR

- Run `make bootstrap` once, `make verify` for repository-local work, and `make validate` before handoff.
- `make definitions` is the meaningful architecture and security gate for charts, workloads, fixtures, and immutable bundles.
- `make runtime-registry` is a specialized consumer-compatibility check using one exact clean control-plane revision.
- Live Kubernetes execution and bundle promotion are never implied by offline validation.

## Verification tiers

| Tier | Command | Purpose and constraints |
|:--|:--|:--|
| Setup | `make bootstrap` | Resolve exact Python dependencies; network may be required. |
| Inner loop | `make verify` | Run documentation, format, lint, type, unit, and repository-definition checks. Helm is required for chart rendering. |
| Supply chain | `make supply-chain` | Verify the lock and query vulnerability data. |
| Complete repository acceptance | `make validate` | Aggregate verification and supply-chain checks. |
| Runtime consumer compatibility | `make runtime-registry` | Validate all fixtures and bundles through the exact pinned clean control-plane loader. |
| Live execution | Explicit benchmark or GitOps command | Requires an authorized target, dedicated kubeconfig/context, and the focused operating guide. |

The root Makefile owns the stable command surface and CI invokes it directly. The repository's domain validator, rather than a generic package-layer rule, enforces the important deployment architecture: immutable identities, least privilege, chart ownership, fixture separation, hashes, and rendered behavior.

## Extending the harness

`make definitions` includes the native search release-record and chart checks.
Its rendering values are synthetic; the published provenance record is not an
environment deployment selection. Helm schema and rendered-object regression
tests run in the ordinary Windows/Linux test matrix without cluster access.

Add checks at the cheapest tier that proves the invariant. Diagnostics identify the file, rule, correction, and canonical guide. Published bundle bytes are never reformatted or repaired in place; corrections create a new reviewed bundle version. Unavailable external prerequisites are reported under the constrained-environment protocol instead of being replaced by weaker checks.
