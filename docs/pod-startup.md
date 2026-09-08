# Pod-startup benchmark

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

The definition currently has offline validation only. Do not run it against a
shared or production cluster until a later change adds reviewed execution,
permissions, result capture, cleanup verification, and an explicit target-cluster
approval procedure.

Tool acquisition is pinned in `toolchain/kube-burner.json`. Verify the downloaded
archive against its recorded SHA-256 before executing it.

Upstream references:

- https://kube-burner.github.io/kube-burner/latest/reference/configuration/
- https://kube-burner.github.io/kube-burner/latest/measurements/
- https://kube-burner.github.io/kube-burner/latest/observability/indexing/
