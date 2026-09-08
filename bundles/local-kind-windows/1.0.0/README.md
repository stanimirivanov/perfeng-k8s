# Local kind Windows bundle 1.0.0

This is the first reviewed runtime registry bundle for the native kube-burner
pod-startup flow. It is deployable only with the pinned local kind definition on
a Windows AMD64 benchmark host. It is not a production or shared-environment
promotion.

The registry binds contracts 0.13, kube-burner 2.8.5's verified Windows release
archive, the repository-owned pod-startup workload, the pinned pause candidate,
and the verified perfeng-analysis 0.8.0 Linux AMD64 image from source revision
`cc7c84ba3e373aa3245a6091b3c24714fe2c37e8`. Native execution has no Kubernetes
execution Job template; normalization and reporting run through the control
plane's separately reviewed analysis and report templates.

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
