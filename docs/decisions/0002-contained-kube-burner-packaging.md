# ADR-0002: Package contained upstream kube-burner execution separately from promotion

- Status: Proposed
- Date: 2026-10-14
- Milestone: M04 — Kubernetes Benchmark Decision Loop
- Deciders: Repository owner
- Supersedes: None

## TL;DR

- Package the existing upstream executable with small deployment/capture/publication adapters.
- Separate namespace-limited runner writes from storage-only publication.
- Disable kube-burner namespace creation, preloading and garbage collection.
- Preserve historical bundles and host/archive execution; promote only after dispatch and recovery exist.

## Context and decision

The host launcher is not a control-plane execution template. Upstream default
preloading creates a DaemonSet and garbage collection can delete namespaces by
label. Granting those permissions would exceed a bounded startup workload.

This repository owns packaging around the verified upstream binary, not another
benchmark engine. Keep the adapter next to the existing benchmark definitions,
offline validators and chart. Introduce a separate contained workload identity,
an opt-in image build/publication workflow and a reusable chart requiring caller
selection. Do not create a new runner repository for this small upstream wrapper.

The dispatcher must pre-create and exclusively own a restricted, quota-bounded
namespace. The runner may create only Pods there. Explicit Pod namespaces avoid
upstream namespace creation; disabled preloading/cleanup/GC avoid wider writes.
The warm candidate must already be cached and is pulled with policy Never.
Upstream watchers require cluster-wide Pod/Event reads; this disclosed read
scope is restricted to the authorized local integration environment.

Only the runner mounts a Kubernetes token; only the publisher receives S3
credentials. The publisher verifies immutable capture inputs, conditionally
creates objects and reads each back before publishing the raw manifest last.
Stable identity, measurement observations and authorization remain distinct.

## Alternatives and consequences

- Cluster-admin/default kube-burner: easy to run but permits unrelated writes;
  rejected in favor of contained Pod creation.
- Embed storage credentials in the runner: smaller Job but combines mutation
  and publication authority; rejected.
- Extend the host launcher in place: would change existing identities and
  archive semantics; retain it unchanged.
- Promote now: would bypass pending reservation, OCI analysis and recovery;
  retain package-only scope until the later M04 promotion slice.

This adds a maintained Python adapter and S3 SDK dependency. Its boundaries are
explicit request validation, read-only observation, process supervision, and
conditional verified publication. Replacing the SDK does not change object
identity or evidence semantics. Shared-host kind results remain integration-only.

## Compatibility, security and operations

Use contracts 0.22.0 alongside, not over, the historical snapshot. Keep every
published bundle immutable. Copy the reviewed environment profile unchanged and
bind live stable inventory to its fingerprint. Missing observations never become
healthy zeros. No Secrets reads, privilege escalation, namespace writes, runner
deletes or automatic cleanup are granted. The chart creates no credentials or
environment-owned input objects. Publication is explicit, main-only and separate
from environment promotion.

## Rollout, recovery and rollback

Build and verify the package before publishing its final image digest. Later
M04 tasks provide dispatch/reservation, OCI analysis and safe lifecycle recovery
before promotion. Interrupted execution leaves no completion marker. Failed
publication retains objects and permits exact retries, never replacement.
Rollback repins a prior reviewed runtime and retains ownership/evidence records.

## Validation

Repository checks cover input closure, permissions, rendering, unknown/failure
semantics, stable keys, collision refusal and manifest-last publication. CI adds
non-root read-only image/binary tests. Live cluster/storage acceptance is separate
and must not be inferred from mocked API tests or successful image publication.
