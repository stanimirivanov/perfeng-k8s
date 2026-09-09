# Local kind Windows bundle 1.0.0

This is the first reviewed runtime registry bundle for the native kube-burner
pod-startup flow. It is deployable only with the pinned local kind definition on
a Windows AMD64 benchmark host. It is not a production or shared-environment
promotion.

The registry binds contracts 0.13, kube-burner 2.8.5's verified Windows release
archive, the repository-owned pod-startup workload, the pinned pause candidate,
and the verified perfeng-analysis 0.8.1 Linux AMD64 image from source revision
`4a55dbb993335652e56b49a966601420eaa905ba`. Native execution has no Kubernetes
execution Job template. The reviewed `jobs/analysis.yaml` template runs
normalization on the Linux control-plane node. Its init container downloads the
selected raw manifest and source from local SeaweedFS, verifies their declared
size and SHA-256, and exposes them to the credential-free normalizer through a
bounded shared volume. The control plane supplies only reserved artifact
metadata at resolution time; the template owns the restricted uploader Secret,
endpoint, transfer commands, scheduling and resource policy. A separate
credential-bearing publisher waits for the atomic normalized output, writes the
stable `runs/<run-id>/normalized-result.json` object conditionally, then reads it
back and verifies its bytes and complete discovery metadata. The normalizer
remains credential-free. The reporting template remains a separate rollout step.

The environment identity records the exact `perfeng-environment` source revision
and kind configuration checksum. Its fingerprint is the SHA-256 of those exact
cluster-configuration bytes. A live preflight must still prove that the selected
Docker host and cluster match them.

The observe-mode policy evaluates p95 pod-ready latency quality and a relative
regression against `approved-local-pod-startup` version 1.0.0. No absolute SLO is
claimed. Until that exact baseline is approved, the regression outcome is
inconclusive.

The only authorized principal is `local-operator`. Deployments must map that
reviewed local identity explicitly; this value is not a production tenant or a
wildcard.
