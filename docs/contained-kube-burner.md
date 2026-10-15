# Contained kube-burner packaging

## TL;DR

- This M04 package is an opt-in building block, not a promoted runtime or live deployment.
- It runs the verified upstream kube-burner 2.8.5 executable in Linux AMD64, with a separate publisher.
- Pod writes are limited to a pre-created, empty, restricted, quota-bounded per-Run namespace.
- Warm images must already exist on the SUT node. No preload DaemonSet, namespace creation or garbage collection is enabled.
- Missing initial observations prevent launch; later FAIL/UNKNOWN observations remain diagnostic evidence, never baseline approval.
- Run `make validate`; the image workflow separately proves container execution and optionally publishes from main.

## Ownership and compatibility

The upstream tool remains the benchmark implementation. This repository owns its
container packaging, resolved-input adapter, lifecycle bounds, capture and
publication configuration. It does not implement a second load generator.
See [ADR 0002](decisions/0002-contained-kube-burner-packaging.md).

The existing host/archive path and all published bundles are unchanged. The new
`execution/workload.json` is `pod-startup-contained/1.0.0`; it must not reuse
the host workload identity because its placement, preloading and cleanup differ.
The actual candidate is the digest-pinned pause image, not the runner image.
Measurements are warm-image startup latency for ten iterations at two requests
per second, not cold pulls, cluster capacity or production-performance claims.

The new path uses a separate, byte-preserved contracts 0.22.0 snapshot at
`contracts/contained`, from commit `3b86afa18b468d831c7c2c176618180db18b2764`.
It does not upgrade the historical 0.13 snapshot or relabel archive evidence as OCI.
The integration profile is imported unchanged from perfeng-environment commit
`9dbd7f84872ed03a1caa32c60ce0ebaf791bbd01`; its SHA-256 is checked before use.
Profile changes remain environment-owned and require a reviewed package update.

## Admission and contained resources

Before creating a Job, the future dispatcher must authorize the target and
candidate, verify fresh accepted preflight evidence, hold a durable exclusive
cluster reservation, and persist the exact request/template/image selection.
This package is not that reservation or an authorization API. Do not deploy it
manually to bypass those pending M04 gates.

The dispatcher owns a new namespace named `perfeng-benchmark-<runId>`, its UID,
and labels:

```yaml
perfeng.io/owner: perfeng-control-plane
perfeng.io/run-id: <actual Run ID>
pod-security.kubernetes.io/enforce: restricted
pod-security.kubernetes.io/enforce-version: v1.35
```

It also owns ResourceQuota `benchmark-budget` there with these exact ceilings:

```yaml
pods: "10"
limits.cpu: 100m
limits.memory: 160Mi
limits.ephemeral-storage: 10Mi
```

The adapter verifies ownership, namespace UID, quota and empty Pod inventory
before launch, then rechecks ownership/incarnation while sampling. It refuses
adoption. Pods use explicit namespace, Run labels, restricted security contexts,
bounded resources, SUT node selection and `imagePullPolicy: Never`. Verify the
approved pause image is already present on that node through an independently
reviewed preload procedure. This package neither downloads it at runtime nor
claims that `IfNotPresent` proves a warm image.

The chart defines a per-execution ServiceAccount, ClusterRole/Binding,
target-namespace Role/Binding and Job. The only Kubernetes write permission is
Pod creation in that one namespace. The upstream pod-latency implementation
requires cluster-wide Pod/Event list/watch; node reads and Metrics API reads
support qualification. This is broader **read** access than namespace-only
execution and must be reviewed for the authorized disposable integration cluster.
No Secrets, namespace writes, deletes, exec, DaemonSets or RBAC mutations are
granted to the runner. Default discovery access is explicitly read-only.

The chart creates no Namespace, quota, Secret or ConfigMap. The caller supplies
immutable request configuration and existing image-pull/storage credentials.
The publisher has storage credentials but no mounted Kubernetes token. The runner
has a projected Kubernetes token but no storage credentials. Both use non-root,
read-only root filesystems and bounded private temporary/output volumes.

## Resolver request and input closure

The chart has no deployment defaults. Synthetic rendering values live only at
`testdata/kube-burner-values.yaml`. The source template is Run-independent;
rendered resources are bound to an actual Run by the resolver.

The externally managed immutable ConfigMap supplies `request.json` and
`environment.json`, mounted read-only through file subPaths. The resolver supplies
the SHA-256 of exact request bytes, not an arbitrary mutable configuration name.
Request fields are closed:

- `schemaVersion: 1`, actual `runId`, and `testId: pod-startup-k8s`;
- approved digest-only `runnerImage`, exact `candidateImage` and workload ID/version/SHA-256;
- exact packaged `templateSha256`;
- `namespace`, actual `namespaceUid` and observed `kubeSystemUid`;
- selected environment ID/version/SHA-256/fingerprint; and
- approved storage `bucket`.

The environment descriptor is checked against its exact bytes. Observed stable
nodes must reproduce the qualification fingerprint recipe, including the selected profile,
node image and cluster incarnation. The adapter uses only packaged config and
template bytes. It freezes namespace, Run ID and metrics-directory substitutions
into `resolved-inputs.json`; only kube-burner's iteration variable remains.
No supplied command, arbitrary template, kubeconfig, proxy or ambient AWS
environment is passed to kube-burner. Publisher verification independently
reconstructs this complete input evidence before contacting storage.

## Capture, completion and publication

The upstream executable's SHA-256 is checked at build and startup. Its process
has a four-minute kube-burner timeout and five-minute supervisory budget, plus
bounded API reads; the Job deadline is ten minutes. SIGTERM, interruption and
errors reap only the child process group, never Kubernetes workloads.

Sampling occurs before launch, approximately every five seconds while the process
runs, and after observed process exit. Gaps exceeding 30 seconds cannot establish
interference PASS. Actual provider windows, conservative quantity conversion and
unknown usage are retained. Original provider windows may extend capture start
before execution. The measurement interval conservatively covers the full process,
including orchestration, not an invented ten-iteration subinterval.

Initial missing/failed prerequisites prevent execution and retain
`initial-qualification.json`. During execution, failure dominates unknown, which
dominates pass. A successful tool run may therefore publish UNKNOWN/REJECTED
measurement evidence for diagnosis; this is never comparable-baseline eligibility.
Host-level contention on shared Docker/kind hardware remains an explicit limitation.

Successful capture validates the three original kube-burner payloads and creates
`complete.json` atomically last. Nonzero exits, missing measurements or interrupted
runs do not create it. Initial evidence, resolved inputs and runner logs remain
for failure inspection; a failed process is never synthesized into success.

The publisher verifies the receipt and all frozen bytes before any S3 operation.
Six objects are conditionally created under `runs/<runId>/raw/`: three original
measurements, resolved inputs, Run qualification and bounded runner log. Each is
read back and checked for exact bytes, size, content type and artifact-ID/SHA-256/
format metadata. Retries accept identical objects, never replace conflicting ones.
`runs/<runId>/raw-result.json` is published and verified **last**, using the
control plane's existing discovery convention and OCI producer provenance.
S3 conditional creation follows [AWS conditional-write semantics](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html).

The publisher uses explicit SDK credentials and bounded retries. It does not
discover instance credentials. The reviewed local SeaweedFS service is the only
HTTP exception; other endpoints require TLS. No credential or signed URL appears
in evidence or operational errors.

The exact local endpoint is `http://seaweedfs.perf-platform.svc.cluster.local:8333`,
matching the environment-owned `seaweedfs` Service. The caller's `storageSecret`
must exist in `perf-generators`, with `access-key` and `secret-key` entries for
the restricted uploader (locally `perfeng-s3-uploader-auth`). Only the publisher
maps these keys to `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. No Service
alias, copied credentials or Secret rotation is needed. The former `seaweedfs-s3`
HTTP alias and alternate key names are unsupported.

## Build and verification

Run `make verify` and `make validate` with Helm. They cover strict lint/rendering,
values rejection, exact permission/mount/resource boundaries, request tampering,
unknown observations, failed execution and conditional publication.

The image workflow builds Linux AMD64 with immutable Python/uv bases, validates
non-root/read-only execution without network, verifies the packaged binary, and
runs the offline adapter tests. The archive and executable checksums come from
`toolchain/kube-burner.json`; acquisition is a build-time operation, never a runtime
download. Upstream source review used tag v2.8.5, commit
`69cca726f3487cd134f7ae26d5375dd4f9428807` (namespace selection, preload and watchers).
The upstream Apache-2.0 license is retained in the image.

After merge, run **Build and optionally publish contained kube-burner** with
`publish=true` on main and retain its verified image/source/platform summary.
This is an operator-authorized publication, not automatic environment promotion.
Do not invent a digest before this workflow succeeds. PR 7 will compose the real
digest with compatible dispatch/analysis and a reviewed runtime bundle.
Endpoint or publisher compatibility fixes require a newly published runner image
and matching control-plane template before promotion; an older image digest
does not acquire the correction when source or chart files change. Existing
immutable bundles remain unchanged.

## Rollout, troubleshooting and rollback

No current environment or published bundle changes in this package. Before future
deployment, dispatch/reservations, scoped lifecycle recovery and OCI analysis must
be implemented. A missing Metrics API remains a prerequisite failure; do not
install metrics-server or disable TLS as an automatic repair.

- Initial guard failure: inspect request hashes, actual UIDs, labels, quota,
  empty target, cached candidate and current qualification.
- Runner failure: inspect the retained init-container status and capture volume;
  do not rerun the tool against the non-empty namespace.
- Publisher failure: inspect retained bytes and storage permissions. Exact retries
  are safe; conflicting objects require investigation, never overwrite/delete.
- Cancellation/cleanup: the control plane must verify persisted ownership and
  incarnation before removing its resources, then release the exclusive reservation.
  This is pending PR 6 and is not delegated to kube-burner.

Rollback selects the previous reviewed runtime, disables new dispatch and retains
existing evidence/resources for explicit recovery. Do not rewrite old bundles,
archive captures, object identities or approved baseline history.
