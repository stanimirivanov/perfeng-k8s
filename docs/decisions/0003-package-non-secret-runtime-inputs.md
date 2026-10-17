# ADR-0003: Package non-secret runtime inputs separately from the workload chart

- Status: Proposed
- Date: 2026-10-17
- Milestone: M06 — Production Readiness
- Deciders: Project owner and deployment maintainers
- Supersedes: None
- Superseded by: None

## TL;DR

- A versioned Kustomize package carries the current non-secret control-plane runtime and registry ConfigMaps.
- The reusable control-plane chart continues to require external ConfigMap and Secret names.
- The environment repository selects the package and owns the eventual Argo CD adoption; this decision does not activate it.
- Secret values, authentication documents and image-pull credentials stay outside the package.

## Context

The local environment currently creates two immutable, content-addressed
ConfigMaps with `control_plane_runtime.py`. That host-side assembly is part of
the deployment-script retirement target. The same command also creates runtime
and authentication Secrets, which have a different lifecycle and must not be
copied into Git. The workload chart deliberately references externally supplied
resource names and does not create environment-owned ConfigMaps.

The selected runtime bundle is already an immutable review unit. Editing its
published `1.0.0` directory to add deployment machinery would change historical
bytes. A separate package can render the current ConfigMaps without changing
the bundle or the workload chart.

## Decision

Keep the chart's caller-supplied ConfigMap and Secret references. Place one
versioned Kustomize package under `packages/runtime-inputs/` with only the
non-secret runtime process policy and exact mounted registry files. Its two
ConfigMap names retain the existing 12-hex SHA-256 suffix of sorted compact JSON
data, their `perf-platform` namespace, immutable flag and historical source
revision annotation. The package copies the selected bundle's mounted files
because a standalone Argo CD Kustomize source cannot read outside its source
root. Repository checks compare every copy with the selected bundle and render
the package with pinned `kubectl kustomize`.

`perfeng-environment` chooses which reviewed package revision to reconcile.
The package is staged until that repository proves existing-resource ownership,
rendered parity and stateful identity safety. No Git merge in this repository
creates a live Application or changes a cluster.

## Alternatives considered

- Put ConfigMaps in the workload chart: this gives one Helm render but makes the
  reusable chart own environment data and conflicts with its external-input
  contract.
- Add Kustomize files inside the existing bundle: this would edit an immutable
  published review unit.
- Continue host-side generation: it preserves the current path but leaves a
  large deployment wrapper in service.

## Consequences

The package has a small checked-in copy of the eight mounted registry files.
The byte-parity check makes drift a failed build. A future bundle selection
needs a new package version and content-addressed names, reviewed together
with the environment lock; it must not edit this package in place after use.
Kustomize rendering adds a pinned kubectl tool to CI. This packaging does not
replace credential generation, database/bucket preparation, or the M04 manual
activation gate.

## Compatibility and migration

The current `perfeng-control-plane-runtime-315a2eede8ff` and
`perfeng-runtime-registry-7be1d749994e` names and all mounted paths remain
unchanged. PR 6 may select this package only after comparing live owned
resources and an Argo CD diff. The existing host command remains the operating
path until that adoption and recovery are accepted.

## Security and operations

Only ConfigMaps are rendered. The package contains no Secret, authentication
document, pull credential or workload permission. Its local endpoint and
bucket values describe the existing kind integration environment and are not
a production profile.

## Rollout, recovery and rollback

This PR has no live rollout. On a later adoption conflict, leave the old
ConfigMaps and workload untouched, inspect the rendered bytes and owner, and
stop before syncing. Immutable ConfigMaps cannot be repaired in place. A new
reviewed selection must use a new content-addressed name; existing resources
and evidence remain until an explicit retention decision.

## Validation

Run `make verify`, `make validate`, and
`kubectl kustomize packages/runtime-inputs/local-kind-integration-1.0.0`.
The focused tests compare rendered content hashes, bundled file bytes, resource
shape and chart references. Bundle loader validation remains
`make runtime-registry` at the pinned control-plane commit.
