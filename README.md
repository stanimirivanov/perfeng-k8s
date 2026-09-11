# perfeng-k8s

Reviewed Kubernetes deployment configuration for the performance engineering
platform.

This repository owns environment-specific, production-oriented composition:

- immutable runtime registry bundles accepted by `perfeng-control-plane`;
- Kubernetes resources and release overlays for shared environments;
- the exact platform component versions promoted together;
- deployment validation and promotion policy.

It does not own application code, contracts, runner implementations, or the
disposable local kind environment. Those remain in their component repositories
and in `perfeng-environment`.

## Current scope

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

The `charts/control-plane` package defines the reusable service workload and its
least-privilege execution-namespace RBAC. It requires an immutable GHCR digest
and references externally managed runtime configuration, credentials,
authentication and reviewed-registry objects. The chart never creates Secrets
or ConfigMaps. The Pod references a required, externally managed image-pull
Secret in its release namespace; the chart never receives registry credentials.
Its synthetic rendering values under `testdata` are not a deployment selection.
`perfeng-environment` must supply the real image digest, Secret name and
configuration when composing an environment. Startup and liveness probes use
the control plane's `/livez` endpoint; readiness uses `/readyz`.

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

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked ty check
uv run --locked python -m unittest discover -s tests -v
uv run --locked python -m scripts.validate
```

Chart validation also requires Helm. It renders the control-plane package with
non-deployable test values and checks the workload identity, security context,
external mounts, Service and exact cross-namespace permissions.

The pod-startup command defaults to a non-mutating preview. See
[the benchmark guide](docs/pod-startup.md) for its explicit execution and
target-confirmation workflow. After a storage adapter has persisted the frozen
measurement bytes, the [offline manifest assembler](docs/raw-manifests.md)
binds its verified receipts into raw-result/v2 without contacting storage.
