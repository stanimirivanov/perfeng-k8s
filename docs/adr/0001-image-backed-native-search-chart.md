# ADR-0001: Package the image-backed native search target

- Status: Proposed
- Date: 2026-10-12
- Milestone: M03 — Native Browser Decision Loop
- Deciders: Repository owner (image-backed direction approved; packaging review pending)

## TL;DR

- Package the already published environment-owned fixture with a reusable Kubernetes chart.
- Require caller-selected digest and external registry credentials; embed neither in chart defaults.
- Use one bounded, token-free non-root Linux AMD64 replica and internal HTTP Service.
- Keep GitOps selection, HTTPS routing and Windows qualification in `perfeng-environment`.
- Record candidate provenance without creating or promoting a native runtime bundle.

## Context

The controlled browser target has a published image identity. Continuing to serve
checkout files while assigning that candidate digest would misrepresent what was
tested. Kubernetes workload packaging belongs here, while source publication,
local HTTPS access and environment selection belong to `perfeng-environment`.
The available Windows host still fails independent qualification conditions.

## Decision

Introduce `charts/native-search` version 1.0.0 with only caller-selected immutable
candidate image and an external pull-Secret reference. Render a Deployment,
ClusterIP Service and token-free ServiceAccount scoped to the caller's release.
Keep application bytes/configuration inside the image with no content overlays,
command or environment overrides. Fix Linux AMD64 placement, non-root identity,
read-only root, bounded temporary storage/resources and HTTP health probes.

Use one replica and Recreate so a rollout does not intentionally overlap candidate
versions. This accepts temporary downtime; it does not authorize changing the
target during measurement. Record the supplied publisher identity in an append-only
release directory, separate from chart defaults, synthetic values and runtime bundles.

## Alternatives considered

- Keep checkout-file serving: useful for pre-promotion connectivity, but not
  honest image-backed candidate evidence.
- Run a custom fixture server or duplicate source here: unnecessary runtime and
  ownership maintenance; the published image already provides the server.
- Put deployment, credentials and gateway selection in the chart: couples the
  reusable workload to a particular host and violates environment ownership.
- Rolling updates or multiple replicas: improve availability, but complicate
  this single-target integration identity without helping milestone acceptance.

## Consequences

Candidate bytes and runtime can be deployed under an honest image identity while
keeping secrets/configuration ownership narrow. Fixed integration resource bounds
and temporary rollout downtime are deliberate limits. ClusterIP is not a network
authorization policy; this credential-free fixture is reachable inside the cluster.
No Kubernetes network enforcement or production performance guarantees are claimed.

## Compatibility and migration

Existing charts, source fixtures, runtime bundles and deployment selections remain
unchanged. No public contract or schema changes. The environment repository must
later pin this chart revision, deploy the exact candidate and replace file-serving
with an identity-checked HTTPS route before claiming the candidate was tested.

## Security and operations

The application receives neither API tokens nor S3/registry credentials. Registry
credentials stay in a caller-owned pull Secret used by kubelet. No RBAC, ingress,
NodePort, host mounts, credentials or content configuration are created. Run as
UID/GID 101 with dropped capabilities, runtime-default seccomp and bounded `/tmp`.
Validation remains offline; image publication and cluster mutation are separate.

## Rollout, recovery and rollback

Argo CD composition belongs to the environment repository. Promotion requires
owned identities, exact running image/content verification through trusted HTTPS,
and separate native acquisition/qualification gates. Restore the earlier reviewed
selection to roll back; retain evidence and credentials, with no automatic pruning.
Do not claim M03 completion from chart rendering or readiness.

## Validation

Run strict Helm linting, schema rejection tests and rendered-object security and
identity assertions through `make validate`. Require real image-backed HTTPS and
qualified browser acceptance separately in the environment selection task.
