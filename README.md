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

The repository currently establishes the runtime-bundle validation boundary. The
fixture under `testdata` is intentionally synthetic and must never be deployed.
There is not yet a reviewed runtime bundle because the analysis runner has not
been published with a registry digest.

The first owned platform workload is a bounded pod-startup benchmark under
`workloads/pod-startup`. It records Kubernetes scheduling, initialization,
containers-ready, and ready latency through kube-burner's `podLatency`
measurement. This initial definition is not scheduled and does not establish a
performance threshold.

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
uv run --locked python scripts/validate.py
```
