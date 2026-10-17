# Perfeng Kubernetes documentation map

## TL;DR

- Start with [CONTRIBUTING.md](../CONTRIBUTING.md), then follow the route for the changed deployment boundary.
- Reusable charts, immutable runtime-registry bundles, synthetic fixtures, and live benchmark execution have distinct owners and verification paths.
- Bundle bytes and exact runtime-loader revisions are immutable; harness work must not rewrite them.
- Update this map when a canonical guide moves or a recurring task lacks a route.

## Route by task

| Task or changed area | Read first | Verify or consult as needed |
|:--|:--|:--|
| Contributor workflow or issue preparation | [Contributor guide](../CONTRIBUTING.md) | [Working agreement](../AGENTS.md) |
| Build, CI, policy, dependencies, or setup | [Harness guide](development/harness.md), [dependency policy](development/dependency-policy.md) | [Engineering standards](development/engineering-standards.md), `make verify` |
| Runtime-registry bundle or promotion | [Repository README](../README.md), the selected bundle README | Exact hashes, contract lock, `make runtime-registry` |
| M04 contained runtime promotion | [Integration bundle 1.0.0](../bundles/local-kind-integration/1.0.0/README.md), [contained package](contained-kube-burner.md) | `scripts/kubernetes_bundle.py`, regression tests and the pinned runtime loader |
| Control-plane chart or Kubernetes security | Chart values and schema under `charts/control-plane` | `make definitions`, rendered-object tests |
| Declarative non-secret runtime input package | [Runtime input package](runtime-input-package.md), [ADR 0003](decisions/0003-package-non-secret-runtime-inputs.md) | `kubectl kustomize`, rendered byte and identity checks |
| Image-backed native browser target | [Native search guide](native-search.md), chart under `charts/native-search` | [ADR 0001](decisions/0001-image-backed-native-search-chart.md), `make definitions`, synthetic render/rejection tests |
| Pod-startup benchmark or kube-burner | [Pod-startup guide](pod-startup.md) | Workload definition, toolchain lock, focused tests |
| Contained kube-burner package, publication or chart | [Contained execution guide](contained-kube-burner.md), [ADR 0002](decisions/0002-contained-kube-burner-packaging.md) | `make validate`, image workflow, `tests/test_contained.py` |
| Raw-result manifest assembly | [Raw-manifest guide](raw-manifests.md) | Contract snapshot and receipt fixtures |
| Durable architecture or ownership decision | [ADR index](decisions/README.md) | Engineering standards and affected consumer documentation |

## Keeping this map useful

This page routes to canonical sources and does not replace them. `make docs-check` validates repository-local links and policy structure. Published bundle documentation remains part of its immutable review unit and is not rewritten to satisfy later stylistic preferences.
