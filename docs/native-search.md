# Image-backed native browser target

## TL;DR

- `charts/native-search` packages the controlled search fixture; it does not run Playwright.
- Select an exact `perfeng-native-search@sha256:` image and an externally managed pull Secret.
- The chart provides one non-root Linux AMD64 replica and a ClusterIP Service on port 8080.
- `releases/native-search/1.0.0/image.json` records the supplied publisher provenance, not a deployed runtime selection.
- `make validate` proves chart/schema/security behavior offline; image-backed HTTPS and browser acceptance remain separate gates.

## Ownership and published identity

The fixture source, NGINX configuration, image builder and publisher belong to
`perfeng-environment`. This repository owns the reusable Kubernetes chart.
Environment namespaces, registry credentials, Argo CD Applications, HTTPS gateway
routing, local port forwards and deployment selection belong to `perfeng-environment`.
The native Linux worker remains outside the Linux Kubernetes cluster.

[ADR 0001](decisions/0001-image-backed-native-search-chart.md) records the boundary.
The [release identity](../releases/native-search/1.0.0/image.json) preserves the
publisher summary supplied by the repository owner:

| Field | Published identity |
|:--|:--|
| Image | `ghcr.io/stanimirivanov/perfeng-native-search@sha256:3f6179c9f3784be884761e7c6ceb4229c48631b8290d5cc65d0b488eef3b4386` |
| Source | `perfeng-environment`, revision `753022c24bbf2f30fd3a620e0788f9b53ae16dd7` |
| Target SHA-256 | `ff03e1d7a7544557a3f035218b6b3e3bcce7e434996be5dd3b895af10cbc0fb4` |
| Platform | `linux/amd64` |

This is an append-only release record, not a native runtime-registry bundle,
qualification artifact or assertion that the image is deployed. Corrections or
later publications require a new release directory; preserve these reviewed bytes.
Offline validation checks structure and rejects obvious repeated-character
identity placeholders; it does not
contact GHCR or independently attest to the publisher's registry verification.
Image labels/content and current base/runtime advisories must be verified before
environment promotion using the component owner's image verification workflow.

## Caller inputs and rendered resources

The values schema accepts only two required inputs:

- `image`: a canonical digest-only reference to the controlled candidate repository.
- `imagePullSecret`: a valid, non-empty Kubernetes Secret name in the release namespace.

Defaults are deliberately empty and cannot render a deployable release. Values
under `testdata/native-search-values.yaml` are synthetic, used only for offline
tests and never for an Application or live install. Do not promote that fixture.

The chart creates exactly a Deployment, Service and ServiceAccount, all named
after the caller's release and explicitly scoped to its namespace. It does not
create a Namespace, Secret, ConfigMap, RBAC, ingress, PVC or NetworkPolicy. The
pull Secret is referenced by the Pod for kubelet image pulling, never mounted
into the application. Reuse of an existing pull Secret is an environment-owner
decision: verify its namespace, ownership and access to this package without
printing, copying or implicitly rotating credentials.

The Service exposes only ClusterIP HTTP port 8080, with selectors matching the
candidate Pod. ClusterIP is not network authorization: other cluster workloads
may reach it. This public, credential-free integration fixture needs no Kubernetes
API or S3 access. Network isolation beyond this boundary requires separate
environment composition and an enforcement-capable network plugin; no enforcement
is implied here. TLS termination remains at the reviewed loopback gateway, not NGINX.

## Execution and availability

The image's own entrypoint, command and embedded configuration remain unchanged.
No environment variables or content ConfigMaps are injected. The chart fixes:

- one replica and a Recreate rollout, avoiding overlap between old/new candidate Pods;
- Linux AMD64 placement, matching the published platform;
- UID/GID and filesystem group 101, runtime-default seccomp, no token automount,
  no privilege escalation, all capabilities dropped and a read-only root;
- CPU/memory/ephemeral-storage requests of 50m/32Mi/16Mi and limits of 500m/64Mi/32Mi;
- a memory-backed 16Mi `/tmp` volume for NGINX runtime files;
- startup/readiness/liveness checks of `/healthz` on the named HTTP port, each with
  a one-second timeout; and
- bounded rollout progress (120 seconds), termination (15 seconds) and history (two revisions).

Memory-backed temporary storage counts against the container's memory budget.
The resource bounds are integration defaults, not capacity or latency guarantees.
Recreate deliberately allows brief unavailability; do not change candidate
selection while an attempt is measuring it. Concurrent changes, throttling,
cluster contention and Pod replacement invalidate a claimed stable target.
Neither readiness nor one replica proves an accepted performance baseline.

## Verification

Run the full repository gate:

```sh
make validate
```

`make definitions` and unit tests run strict Helm linting, schema rejection and
rendered-object assertions with synthetic inputs. Tests cover caller-scoped names
and namespace, digest-only selection, token/RBAC/credential boundaries, writable
storage, resources, probes, Service exposure and single-replica rollout. Validation
uses no Kubernetes client and does not build, pull or run the candidate image.

No runtime bundle is changed; the pinned control-plane runtime-loader check is
not needed for this chart-only capability. It remains required when subsequently
promoting the complete native bundle.

## Environment promotion and acceptance

After this chart is reviewed and merged, `perfeng-environment` must select its
immutable repository revision/chart version and the release image digest, supply
the owned pull Secret, then compose and reconcile a dedicated Argo CD Application.
Do not use a competing direct Helm install against GitOps-owned resources.

Before claiming a Run tests this candidate:

1. Confirm the owned Deployment has the exact selected digest and its running
   image identity agrees; verify rollout/readiness in the dedicated cluster.
2. Add an identity-checked loopback-only target forward and route the existing
   HTTPS target to the Service, not checkout files. Stop/restart forwards after
   Pod replacement. Do not use a generic file-serving fallback on proxy failure.
3. Verify exact HTML/JavaScript bytes and target checksum through trusted HTTPS,
   using expected bytes from the pinned source, plus the candidate HTTP/security checks.
4. Select the native bundle and newer control-plane image, provision the distinct
   worker identity and prove signed upload/internal read-back separately.
5. Obtain a fresh accepted Linux qualification and execute the browser decision
   loop, including cancellation and explicit manual recovery.

The available laptop's OS-build and background-CPU failures still block real
qualified acceptance; this chart does not relax them. M03 remains incomplete.

## Diagnosis and rollback

- Missing/invalid values: use real reviewed selection; never deploy the synthetic test file.
- ImagePullBackOff: inspect safe events and pull-Secret ownership/package permissions
  in the release namespace. Do not print Secret contents or rotate credentials implicitly.
- Pending: verify Linux AMD64 capacity and resource availability; do not remove isolation limits.
- Readiness failure: verify exact image, port 8080 and `/tmp` permissions/bounds;
  do not replace probes with unconditional success.
- HTTPS content mismatch: inspect the selected digest, pinned source and gateway
  upstream. Do not rewrite expected checksums or silently fall back to local files.

Rollback restores the previous reviewed GitOps selection and restarts the owned
forward as needed. Stop target use during transition. Retain evidence and CA trust;
no Secret rotation, object/PVC deletion, baseline relabeling or automatic pruning
is part of this chart. Existing runtime bundles remain unchanged.
