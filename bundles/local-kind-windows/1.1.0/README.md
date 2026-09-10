# Local kind Windows bundle 1.1.0

This immutable review unit adds a control-plane-runnable k6 checkout smoke flow
to the native kube-burner pod-startup flow from bundle 1.0.0. It is deployable
only with the pinned local kind definition on a Windows AMD64 benchmark host. It
is not a production or shared-environment promotion.

The registry binds contracts 0.13, kube-burner 2.8.5's verified Windows release
archive, the repository-owned pod-startup workload, the pinned pause candidate,
and the verified perfeng-analysis 0.8.1 Linux AMD64 image from source revision
`4a55dbb993335652e56b49a966601420eaa905ba`. Native execution has no Kubernetes
execution Job template.

The k6 entry binds the verified k6 2.2.0 Linux AMD64 image from source revision
`a916ef3bcbfe9337504bdba6ddddcafe46f32b81`, the exact checkout-smoke workload
definition from that source, and the pinned Python image used by the local sample
API. Its reusable `jobs/execution.json` template has no Run identity. The control
plane assigns the deterministic Job name, namespace, ownership labels and
specification fingerprint. The template fixes the checkout/smoke profile and
in-cluster sample API target; it accepts no caller-supplied URL, script or load
shape. A credential-free init container runs k6, while a restricted publisher
conditionally writes and reads back the summary and point artifacts before
publishing their raw-result/v2 manifest as the final completion marker. The
publisher verifies object bytes, sizes, content types and metadata and cannot
overwrite existing Run evidence.

The reviewed `jobs/analysis.yaml` template runs normalization on the Linux
control-plane node. Its init container downloads the selected raw manifest and
source from local SeaweedFS, verifies their declared
size and SHA-256, and exposes them to the credential-free normalizer through a
bounded shared volume. The control plane supplies only reserved artifact
metadata at resolution time; the template owns the restricted uploader Secret,
endpoint, transfer commands, scheduling and resource policy. A separate
credential-bearing publisher waits for the atomic normalized output, writes the
stable `runs/<run-id>/normalized-result.json` object conditionally, then reads it
back and verifies its bytes and complete discovery metadata. The normalizer
remains credential-free. The reviewed `jobs/reporting.yaml` template applies the
same separation to reporting: it stages and verifies the candidate, exact policy
and unique available baseline artifacts, runs the pinned reporter without storage
credentials, and conditionally publishes and verifies `analysis-result/v1` at the
stable Run key. The policy must first be seeded at
`policies/<id>/<version>/performance-policy.json` in the configured artifact bucket.

The environment identity records the exact `perfeng-environment` source revision
and kind configuration checksum. Its fingerprint is the SHA-256 of those exact
cluster-configuration bytes. A live preflight must still prove that the selected
Docker host and cluster match them.

The pod-startup observe-mode policy evaluates p95 pod-ready latency quality and a
relative regression against `approved-local-pod-startup` version 1.0.0. No
absolute pod-startup SLO is claimed. Until that exact baseline is approved, the
regression outcome is inconclusive. The checkout smoke policy observes a 500 ms
p95 HTTP-duration SLO without claiming a calibrated regression baseline.

The only authorized principal is `local-operator`. Deployments must map that
reviewed local identity explicitly; this value is not a production tenant or a
wildcard.
