# Pod-startup benchmark

## TL;DR

- Creates ten pods at two requests per second to verify the pod-startup evidence path, not to define
  a stable performance baseline.
- Measures warm-image Kubernetes scheduling and readiness; registry/cold-pull performance is out of
  scope.
- Defaults to preview and requires an explicit kubeconfig, context, Run ID, fresh output and matching
  context confirmation before execution.
- Uses a checksum-pinned kube-burner release and keeps measurements local.
- Run only against an explicitly authorized disposable cluster and inspect failed cleanup before
  deleting resources.

This workload is the first bounded Kubernetes platform benchmark. It creates ten
single-container pods at two requests per second and records kube-burner's
`podLatency` measurement. The measurement separates scheduling, initialization,
containers-ready, and pod-ready latency.

The pause image is preloaded before measurement. Results therefore describe
warm-image control-plane, scheduler, kubelet, and runtime behavior; they do not
measure registry throughput or cold image-pull latency. A cold-image benchmark
must be a separate workload.

Measurements are written to the directory supplied through
`METRICS_DIRECTORY`. They are not sent to Prometheus or OpenSearch. Automatic
garbage collection and the cluster health precondition remain enabled. The
workload has no kube-burner latency threshold: ten observations are suitable for
integration and evidence-shape checks, not a stable regression decision.

## Preview and execute

The runner requires an explicit kubeconfig, context, run identity, and fresh
output directory. Its default mode only prints the planned target and command;
it does not download tools or contact Kubernetes.

```sh
$arguments = @(
  "-m", "scripts.benchmark", "pod-startup",
  "--kubeconfig", "../perfeng-environment/.local/perfeng-local.kubeconfig",
  "--context", "kind-perfeng-local",
  "--run-id", "perf-20260908-120000-a1b2c3d4",
  "--output", ".local/results/perf-20260908-120000-a1b2c3d4"
)
uv run --locked python @arguments
uv run --locked python @arguments --execute --confirm-context kind-perfeng-local
```

Execution validates the named context with `kubectl`, downloads the platform's
pinned kube-burner archive when it is not cached, verifies both archive and
executable hashes, streams output to the terminal and `runner.log`, and writes
`execution.json`. The receipt pins contracts 0.13, the release archive and
executable hashes, the exact workload-definition bytes, and all measurement
bytes. Success requires kube-burner exit code zero, at least one
non-empty JSON measurement file, and removal of the benchmark namespace.

If execution fails and the namespace remains, inspect it before deciding whether
to delete it:

```sh
kubectl --kubeconfig ../perfeng-environment/.local/perfeng-local.kubeconfig \
  --context kind-perfeng-local get namespace perfeng-pod-startup
```

The command is intended for disposable local clusters only. It does not install
cluster credentials, schedule recurring runs, upload results, or authorize use
against shared and production clusters. See [raw manifests](raw-manifests.md)
for the separate evidence-assembly boundary.

Tool acquisition is pinned in `toolchain/kube-burner.json`. Verify the downloaded
archive against its recorded SHA-256 before executing it.

Upstream references:

- https://kube-burner.github.io/kube-burner/latest/reference/configuration/
- https://kube-burner.github.io/kube-burner/latest/measurements/
- https://kube-burner.github.io/kube-burner/latest/observability/indexing/
