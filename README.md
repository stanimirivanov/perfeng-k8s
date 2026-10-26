# perfeng-k8s

## TL;DR

- Owns reusable Kubernetes charts and reviewed, immutable runtime-registry bundles for promoted
  platform composition.
- Every deployable bundle binds exact component digests, configuration hashes, environment identity,
  policy and authorized principals.
- Charts require externally managed environment configuration and credentials and preserve
  least-privilege workload boundaries.
- Synthetic fixtures are never deployable; local kind/Argo CD composition belongs to
  `perfeng-environment`.
- Run `make validate`; bundle changes also require `make runtime-registry` with the exact pinned
  clean control-plane checkout.

Reviewed Kubernetes deployment configuration for the performance engineering
platform.

Use the [documentation map](docs/README.md) to route implementation work. The
[coding harness](docs/development/harness.md) defines verification tiers and the
[dependency policy](docs/development/dependency-policy.md) defines admission and update rules.

This repository owns environment-specific, production-oriented composition:

- immutable runtime registry bundles accepted by `perfeng-control-plane`;
- Kubernetes resources and release overlays for shared environments;
- the exact platform component versions promoted together;
- deployment validation and promotion policy.

It does not own application code, contracts, runner implementations, or the
disposable local kind environment. Those remain in their component repositories
and in `perfeng-environment`.

## Current scope

The [requalified local kind integration bundle 1.0.1](bundles/local-kind-integration/1.0.1/README.md)
binds the rebuilt cluster using fresh accepted evidence and preserves all execution and
authorization identities. Its downstream environment selection is a separate review.

The [local kind integration bundle 1.0.0](bundles/local-kind-integration/1.0.0/README.md)
promotes the corrected contained kube-burner image and OCI-aware analysis reader
for the accepted M04 environment, alongside k6 checkout. It pins reservation and
cleanup-aware runtime validation, keeps baseline cohorts separate and leaves all
historical bundle bytes unchanged. Environment selection, deployment permissions
and live decision-loop acceptance remain separate follow-up gates.

The [contained kube-burner package](docs/contained-kube-burner.md) adds an opt-in
Linux AMD64 image and chart for bounded, Run-scoped pod startup. It separates
scoped Kubernetes execution from verified storage publication. No runtime bundle,
environment selection or live workload is promoted by this package.

The [native search chart](docs/native-search.md) packages the published controlled
browser fixture as a bounded, token-free Linux AMD64 workload. Its caller must
supply the candidate digest and external image-pull Secret. The publisher-provided
identity is recorded under `releases/native-search/1.0.0`, separate from defaults
and synthetic rendering values. No native runtime bundle or environment selection
is promoted by this chart; GitOps deployment, HTTPS route cutover and accepted
Windows qualification remain environment-owned M03 gates.

The fixture under `testdata` is intentionally synthetic and must never be
deployed. The first reviewed bundle under
`bundles/local-kind-windows/1.0.0` binds the native Windows pod-startup flow to
the verified perfeng-analysis 0.8.1 image. It is a local integration bundle, not
a production or shared-environment promotion.

The first owned platform workload is a bounded pod-startup benchmark under
`workloads/pod-startup`. It records Kubernetes scheduling, initialization,
containers-ready, and ready latency through kube-burner's `podLatency`
measurement. This initial definition is not scheduled and does not establish a
performance threshold.

The local bundle also owns a reusable analysis Job template. A restricted
init container materializes and verifies the control-plane-selected raw inputs;
the approved normalizer never receives object-storage credentials. A separate
publisher waits for the atomically completed output, creates the deterministic
normalized object without overwriting prior evidence, and verifies its stored
bytes and discovery metadata. The template is composition input for the control
plane and has no reusable Run identity of its own.

The bundle also owns a reusable reporting Job template. Its initializer stages
and verifies the selected normalized candidate, exact reviewed policy and unique
available baseline artifacts from SeaweedFS. The credential-free reporter uses
the pinned perfeng-analysis image, while a separate publisher conditionally
creates and verifies the stable `analysis-result/v1` object. The reporter command,
arguments and trusted staging metadata are supplied by the control plane at
resolution time; the template owns transfer and publication commands.

Bundle `local-kind-windows/1.1.0` adds the first control-plane-runnable k6
execution template without modifying the immutable native-only 1.0.0 bundle.
The reviewed Job fixes checkout/smoke and the local sample API target, separates
the credential-free runner from the restricted publisher, and publishes a
checksum-verified raw-result/v2 completion marker for collection by the control
plane.

Bundle `local-kind-windows/1.1.1` preserves those workloads while correcting
candidate images to the canonical digest-only identities accepted by the Run
API. Tags remain useful for human release discovery but are excluded from Run
identity so one image digest has one authorization value.

Bundle `local-kind-windows/1.1.2` corrects the quoted JMESPath lookup used to
verify hyphenated S3 metadata keys after normalized and report publication.
This keeps the live verification compatible with the bundle's pinned AWS CLI.

Bundle `local-kind-windows/1.1.3` aligns each performance policy name with its
registry test identity, as required by the report evaluator. Repository
validation rejects future bundles whose policy and test identities diverge.

The `charts/control-plane` package defines the reusable service workload and its
least-privilege execution-namespace RBAC. It requires an immutable GHCR digest
and references externally managed runtime configuration, credentials,
authentication and reviewed-registry objects. The chart never creates Secrets
or ConfigMaps. The Pod references a required, externally managed image-pull
Secret in its release namespace; the chart never receives registry credentials.
Its synthetic rendering values under `testdata` are not a deployment selection.
`packages/runtime-inputs/local-kind-integration-1.0.0` stages the current
non-secret ConfigMaps as a separate [Kustomize package](docs/runtime-input-package.md).
The active environment has not selected it; Secrets and the chart's external
references retain their existing owners.
`perfeng-environment` must supply the real image digest, Secret name and
configuration when composing an environment. The runtime ConfigMap owns the
complete non-secret process policy, including `PERFENG_HTTP_ADDRESS`; its
listener port must match the chart's `httpPort` service and probe boundary.
Startup and liveness probes use the control plane's `/livez` endpoint;
readiness uses `/readyz`.

Deployable bundles will live under:

```text
bundles/<environment>/<version>/
  registry.json
  jobs/
  policies/
```

Each bundle is an immutable review unit. Its manifest binds a test, catalogue,
profile, policy, workload, environment, dataset, principals, candidate images,
and runner images. Referenced files are resolved relative to the bundle root.
Images must use registry digests; digest-shaped placeholders and mutable tags are
not release configuration.

The control plane's offline validator is the executable definition of the bundle
format. CI checks out the exact reviewed control-plane revision recorded in the
workflow and validates every repository-owned fixture or bundle with that
implementation.

See [CONTRIBUTING.md](CONTRIBUTING.md) for local validation and change rules.

## Validate the repository

Detailed contributor policy is in [CONTRIBUTING.md](CONTRIBUTING.md), Kubernetes and promotion
standards are in [docs/development/engineering-standards.md](docs/development/engineering-standards.md),
and durable decisions are recorded in [ADRs](docs/decisions/README.md).

```sh
uv sync --locked
make validate
```

The equivalent individual commands remain documented in CONTRIBUTING. Runtime-bundle changes also
require the exact pinned control-plane loader through `make runtime-registry`; that check is kept
separate because it requires a clean adjacent repository at the recorded revision.

Chart validation also requires Helm. It renders the control-plane package with
non-deployable test values and checks the workload identity, security context,
external mounts, Service and exact cross-namespace permissions.
It also strictly lints and renders the native search chart, rejects unsupported
inputs and asserts candidate isolation, bounded resources and internal Service
exposure without accessing a cluster.

The pod-startup command defaults to a non-mutating preview. See
[the benchmark guide](docs/pod-startup.md) for its explicit execution and
target-confirmation workflow. After a storage adapter has persisted the frozen
measurement bytes, the [offline manifest assembler](docs/raw-manifests.md)
binds its verified receipts into raw-result/v2 without contacting storage.
