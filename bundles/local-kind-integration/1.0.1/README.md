# Local kind integration bundle 1.0.1

## TL;DR

- Bind the recreated local cluster to its exact fresh, accepted environment descriptor.
- Preserve all execution images, Job bytes, workloads, policies, principals and checkout identities from bundle 1.0.0.
- Keep the qualification profile/environment version at 1.0.0, as required by the pinned runtime; 1.0.1 is the new bundle version.
- Validate both immutable versions and the pinned runtime loader before downstream environment selection.
- This reviewed source package does not activate workloads, restore deleted data or complete M04.

## Requalified environment

The previous cluster was removed with its Docker volumes. The recreated cluster has
kube-system UID `257a288d-9e0f-4956-a0e3-9c4104de6476`.
Verified-TLS metrics health passed before fresh qualification; all six qualification
checks passed and the retained receipt is ACCEPTED for integration use.

[environment.json](identities/environment.json) copies the exact 580-byte descriptor,
SHA-256 `9aca1ceb38d881656850b2866c6f53301cc520cfa0aca30fd33dd90aefbeb036`.
Its fingerprint is `017ef80efa09fef2817922182248fc280212acaaf5308ada8b9358a2824daeef`.
The unchanged profile is `local-kind-integration/1.0.0`; that version is also part of
the receipt and the pinned runtime contract. The new fingerprint and descriptor hash
bind this incarnation without changing the evidence's profile version.

[provenance.json](provenance.json) records the actual receipt hash, size and capture
interval, the exact environment source commit and every bundle member checksum.
The original receipt stays in ignored operator results; no synthetic receipt or edited
old observation is promoted. Current dispatch still requires fresh, measurement-scoped
evidence and compatible admission. One accepted observation on shared Docker hardware
is not sustained or calibrated production-performance qualification.

## Retained execution and authorization

The [1.0.0 execution and security boundaries](../1.0.0/README.md) remain unchanged.
The runner/analysis/k6 images, source identities, catalogue, workloads, four Job recipes,
both policies, baseline reference and sole local-operator principal are byte-identical.
The checkout entry and its historical environment are unchanged. The pinned loader is
still `703d9d11fda3f94e52b4cf4fad749d73cf52247f`.

Bundle 1.0.0 and all previous bundles remain immutable. Only the pod-startup entry's
environment hash/fingerprint and benchmark cluster UID change in this new registry.
No credentials, controller permissions, host trust or baseline approval are added.
An unchanged baseline key is not permission to reuse old-cluster evidence: reporting
and explicit approval must independently verify environment eligibility.

## Deployment and recovery boundary

Use the matching new standalone Kustomize runtime-input package only after a reviewed
perfeng-environment selection binds its source commit, bundle hash and rendered names.
Argo CD remains the workload owner; the chart still references external credentials.
Do not switch the active environment lock or sync the runtime from this source PR.
Fresh-cluster preparation must establish the database schema, secrets, registry mounts
and policies before a separately authorized manual runtime activation.

Deleting Docker volumes removed database and object-store data. This bundle does not
restore them or recreate approved baselines. Retain old evidence and packages. A rollback
must respect the existing compatible-worker/migration and retained-hold boundaries;
the previous cluster-bound bundle cannot qualify this recreated cluster.

## Verification

Run `make validate` and `make runtime-registry` using the exact clean pinned loader.
Both versions receive the same identity/provenance/transfer rejection checks, including
self-consistently rehashed registry and descriptor mutations. Historical byte preservation
and the new package's exact mount parity are checked separately from live acceptance.
