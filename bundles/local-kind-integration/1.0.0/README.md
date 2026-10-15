# Local kind integration bundle 1.0.0

## TL;DR

- Promote contained kube-burner startup alongside the retained k6 checkout path.
- Bind the corrected runner, OCI-aware analysis image and exact accepted local environment.
- Require the pinned reservation/cleanup-aware control plane and explicit deployment prerequisites.
- Keep the contained baseline separate from historical archive/host results; this is integration-only.
- Run `make validate` and `make runtime-registry`; this bundle does not deploy itself or complete M04.

## Selected runtime

`registry.json` selects catalogue `platform-tests/1.2.0` and the sole authorized
principal `local-operator`. It admits two `smoke` entries:

| Entry | Execution and evidence | Environment |
|:--|:--|:--|
| `pod-startup-k8s` | Contained OCI kube-burner 2.8.5, workload `pod-startup-contained/1.0.0`, contracts 0.22.0 | Accepted `local-kind-integration/1.0.0` descriptor |
| `checkout-api` | Existing k6 2.2.0 checkout/smoke recipe, contracts 0.13.0 | Unchanged historical checkout environment |

The runner image and source are recorded in
[kube-burner-image.json](identities/kube-burner-image.json); its source includes
the corrected SeaweedFS endpoint. The analysis reader/reporter selection is in
[analysis-image.json](identities/analysis-image.json). Both are verified
Linux AMD64 releases, not tags, local image IDs or the earlier incompatible
runner digest. k6 retains its verified image and workload bytes.

The pinned control-plane validator is commit
`703d9d11fda3f94e52b4cf4fad749d73cf52247f`. It includes durable target
reservations, owned cleanup/restart recovery and the corrected publisher Secret
keys. The older validator cannot consume this benchmark entry. Deployment must
use compatible control-plane code; a validator revision is not an executable
control-plane image selection.

## Identity and evidence

[environment.json](identities/environment.json) preserves the exact 580 bytes
from the operator-supplied all-PASS qualification. Its SHA-256 is
`59bfaacb94f7c2f889d33225934ebcc7b4475938f46b938907016119016dac0c`.
Its fingerprint binds the reviewed profile, node image, actual cluster UID and
node inventory; it is not a hash of a generic kind configuration.

[provenance.json](provenance.json) records the accepted receipt's hash, size,
capture interval, environment source and the checksum closure of this bundle.
The transient receipt remains in the environment operator's retained results,
not in this bundle. These are reviewed selection records, not a new live
qualification or reusable admission token. Dispatch and measurement still need
their own current observations. Cluster recreation requires a new reviewed
selection; never substitute a new UID behind this immutable version.

The benchmark request hash of all zeroes in `jobs/benchmark.json` is an unbound
template slot, not an artifact checksum. The control plane fills the actual
sealed request hash, ConfigMap and service account after durable reservation and
namespace-UID binding. No Run ID, namespace UID or caller command is embedded in
this reusable template. The pinned Go loader checks the complete recipe.

## Execution and storage boundaries

The runner alone receives its explicit Kubernetes token; only its publisher
receives storage credentials. It creates the bounded warm pause workload in the
owned Run namespace, not namespaces, preload resources or cleanup workloads.
The publisher verifies raw prerequisites and publishes the completion marker last.

The normalizer and reporter remain credential-free. Their separate transfer
containers retain the reviewed conditional publication and exact read-back
checks. The analysis image changes to the OCI-aware release; transfer commands,
storage scope, resource limits and security contexts remain unchanged.

All four Job templates explicitly reference `perfeng-execution-registry` in
`perf-generators`. The environment owner must provision and verify this
image-pull Secret for the selected runner, analysis and k6 images. This bundle
contains no registry credentials and creates no Secret or default-service-account
patch. Storage uses `perfeng-s3-uploader-auth` keys `access-key` and `secret-key`,
and exactly `http://seaweedfs.perf-platform.svc.cluster.local:8333`.

## Policy and baseline isolation

The observe-mode policy is `pod-startup-k8s/1.1.0`: p95 ready latency, at least
ten samples and a 10% practical relative regression threshold, without an
absolute startup SLO. It selects baseline
`approved-local-pod-startup-contained/1.0.0`, never the historical archive
baseline. Until an eligible reference is explicitly approved, regression remains
inconclusive. Do not relabel historical captures into this cohort.

Ten warm-image observations on shared Docker/kind hardware are integration
evidence, not calibrated production performance or statistical significance.
Analysis quality PASS does not establish environmental eligibility. Verify
measurement-scoped qualification, integrity, coverage, workload and environment
before approving any baseline; UNKNOWN/REJECTED evidence is diagnostic only.

## Deployment prerequisites and rollback

The subsequent environment-selection change must explicitly provide:

1. A published compatible control-plane image, migrations 0017/0018 and a
   coordinated worker rollout; do not mix pre-cleanup workers with active holds.
2. The exact dedicated cluster, verified-TLS Metrics API, ready reviewed nodes,
   available capacity and independently reviewed warm candidate cache.
3. Reviewed controller dispatch/cleanup RBAC, per-Run namespace/quota ownership
   and external input/configuration materialization. The existing service chart
   alone does not grant this benchmark authority. Namespace/Pod creation cannot
   be constrained by labels through ordinary RBAC; this is not a shared-cluster
   authorization profile.
4. The external pull/uploader Secrets, retained bucket and compatible registry,
   analysis and report mounts. Do not copy credential values into bundle files.
5. The exact policies seeded before reporting, including the new key
   `policies/pod-startup-k8s/1.1.0/performance-policy.json`.
6. Reviewed GitOps selection followed by decision-loop, cancellation and restart
   acceptance. Never launch the recipe manually to bypass the controller.

This source promotion changes no deployed selection, controller permission,
Secret, database or baseline approval. Before rollback, stop new benchmark
admission and resolve retained holds through compatible cleanup-aware code.
Repin an older bundle only after that review; retain schema, tombstones and
evidence. Do not downgrade workers with active holds, force-release targets or
rewrite earlier bundle bytes.

## Verification

`make validate` checks the complete checksum/identity closure, source-preserved
members, chart-derived benchmark template, transfer isolation and rejection
regressions. `make runtime-registry` checks this bundle and every historical
bundle through the exact clean pinned control-plane loader. Synthetic fixtures
remain under `testdata`; neither mocked tests nor image publication substitute
for subsequent live milestone acceptance.
