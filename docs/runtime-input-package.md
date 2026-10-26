# Staged non-secret control-plane runtime input package

## TL;DR

- `packages/runtime-inputs/local-kind-integration-1.0.0` renders the two existing immutable non-secret ConfigMaps.
- The new 1.0.1 package is prepared for the rebuilt cluster; downstream environment selection requires a separate review.
- It retains the current content-addressed names and exact registry mount bytes; Secrets remain external.
- Run the offline render and repository gates before reviewing a future environment selection.

## Requalified package 1.0.1

[local-kind-integration-1.0.1](../packages/runtime-inputs/local-kind-integration-1.0.1/kustomization.yaml)
contains the exact mounted files from [bundle 1.0.1](../bundles/local-kind-integration/1.0.1/README.md).
It retains the 34 process-policy values and runtime ConfigMap name
`perfeng-control-plane-runtime-315a2eede8ff`. The new registry name is
`perfeng-runtime-registry-37bfeb2a30f6`, derived from its complete data map.
Both immutable ConfigMaps record source snapshot `04e4de13c72f3bc5d61f8ecb4aff7eb22b57183b`,
which contains the complete new bundle and its verified qualification provenance.
The package is prepared in the following source commit; its source annotation is not a
self-reference to its own commit. All historical package/bundle files remain unchanged.

The consumer must separately select the final package-bearing Git commit, source snapshot,
bundle checksum and both ConfigMap names. No active environment selection or live ConfigMap
is changed by this PR. Retained resources with conflicting provenance must be inspected,
not force-adopted or overwritten. No Secret or runtime grant is included.

```sh
kubectl kustomize packages/runtime-inputs/local-kind-integration-1.0.1
```

The same shape, exact mounted-byte parity, content-hash and chart-reference tests apply to
both package versions. Runtime policy bytes are also compared across versions.

## Original package bytes and ownership

The [Kustomize package](../packages/runtime-inputs/local-kind-integration-1.0.0/kustomization.yaml)
contains the 34 existing non-secret process-policy values and eight mounted
files from [bundle 1.0.0](../bundles/local-kind-integration/1.0.0/README.md).
It renders only:

| Resource | Current name | Purpose |
|:--|:--|:--|
| Runtime policy ConfigMap | `perfeng-control-plane-runtime-315a2eede8ff` | `envFrom` values |
| Registry ConfigMap | `perfeng-runtime-registry-7be1d749994e` | Exact files under `/etc/perfeng/registry` |

Both resources are immutable in `perf-platform` and keep the original selected
`perfeng-k8s` revision `fa718c2b62f4f10b5e9da8dce7b00a3f51daae0b`
as historical provenance. Their suffix is the first 12 hexadecimal characters
of SHA-256 over sorted compact JSON of the complete `data` map. The copied
registry files are compared byte for byte with the selected bundle by
`tests/test_runtime_inputs.py`. [ADR 0003](decisions/0003-package-non-secret-runtime-inputs.md)
records why the package is separate from the workload chart.

The control-plane chart still accepts these names as values and requires
separately managed runtime, authentication and image-pull Secrets. The package
contains no credential values and grants no Kubernetes permissions.

## Offline inspection

```sh
kubectl kustomize packages/runtime-inputs/local-kind-integration-1.0.0
make verify
make validate
```

The render must contain exactly the two ConfigMaps above, with the expected
namespace, owner label, source revision annotation, immutable flag and data
hashes. The repository test also renders the existing chart with those names
and confirms its runtime and registry references. `make runtime-registry`
checks that the pinned control-plane loader accepts the unchanged bundle.

## Adoption boundary and recovery

The new 1.0.1 package does not alter `perfeng-environment`'s deployment lock.
A downstream selection must separately select the package in Argo CD, prove that each
live resource has matching immutable bytes and the expected owner, inspect the diff, and retain manual control-plane
activation. The current `control_plane_runtime.py` path remains operational
until that adoption is accepted.

If the live ConfigMap differs, do not force adoption or overwrite it. Preserve
the running workload and its Secrets, inspect the selected bundle and lock,
then prepare a new reviewed content-addressed resource or an explicit recovery
decision. An old package revision remains available for diagnosis; pruning and
credential rotation are outside this slice.
