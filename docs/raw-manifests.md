# Kubernetes raw manifests

## TL;DR

- Assemble raw-result/v2 only from a completed frozen pod-startup capture and three verified storage
  receipts.
- The assembler verifies local identities, paths, hashes, sizes and payload shape without contacting
  storage.
- Storage must upload and verify immutable objects before issuing receipts.
- Existing output is never overwritten, and original kube-burner evidence is never modified.
- The execution interval is intentionally conservative; downstream analysis must not invent a more
  precise measurement window.

The offline assembler converts one completed pod-startup capture and three
verified storage receipts into a contracts 0.13 raw-result/v2 document. It does
not upload, download, register, normalize, or evaluate evidence. A valid
manifest is not proof that the referenced remote bytes exist; the storage
adapter must complete and verify each upload before issuing its receipt.

## Frozen capture

Use the fresh output directory produced by `scripts.benchmark`. Do not modify
`execution.json` or these three kube-burner files after upload:

- `jobSummary.json`;
- `podLatencyMeasurement-pod-startup-smoke.json`; and
- `podLatencyQuantilesMeasurement-pod-startup-smoke.json`.

The assembler verifies their hashes and sizes against both `execution.json` and
the storage receipts. It also checks the successful execution state, cleanup,
contracts version, release archive and executable identity, workload and input
checksums, run identity, ten distinct pod iterations, and basic kube-burner
payload identity. Paths cannot escape the capture directory, including through
symlinks.

Each receipt has a relative `file` and a complete artifact/v1 `artifact`:

```json
{
  "file": "jobSummary.json",
  "artifact": {
    "id": "11111111-1111-4111-8111-111111111111",
    "runId": "perf-20260908-120000-a1b2c3d4",
    "kind": "raw",
    "uri": "s3://perfeng-artifacts/runs/perf-20260908-120000-a1b2c3d4/raw/jobSummary.json",
    "sha256": "<64 lowercase hexadecimal characters>",
    "sizeBytes": 678,
    "mediaType": "application/json",
    "format": "kube-burner-job-summary-json"
  }
}
```

Use these formats for the three files, respectively:

| File | Format |
| --- | --- |
| `jobSummary.json` | `kube-burner-job-summary-json` |
| `podLatencyMeasurement-pod-startup-smoke.json` | `kube-burner-pod-latency-json` |
| `podLatencyQuantilesMeasurement-pod-startup-smoke.json` | `kube-burner-pod-latency-quantiles-json` |

All references use `application/json`, the execution run ID, and distinct
canonical UUIDs and stable S3 or HTTPS URIs. Credentials, signed URLs, queries,
fragments, local paths, duplicate identities, and duplicate locations are
rejected.

## Assemble

Create a request containing exactly `testId` and the three receipts:

```json
{
  "testId": "pod-startup-k8s",
  "receipts": [
    {"file": "jobSummary.json", "artifact": {}},
    {"file": "podLatencyMeasurement-pod-startup-smoke.json", "artifact": {}},
    {"file": "podLatencyQuantilesMeasurement-pod-startup-smoke.json", "artifact": {}}
  ]
}
```

Replace each empty artifact with the storage adapter's complete verified
reference, then run:

```sh
uv run --locked python -m scripts.manifest \
  .local/results/perf-20260908-120000-a1b2c3d4 \
  .local/manifest-request.json \
  .local/raw-result.json
```

The output parent must already exist. Existing output is never overwritten.
The execution start and completion timestamps form the conservative measurement
window; they include kube-burner orchestration overhead rather than claiming a
narrower interval that the current adapter cannot prove. Downstream
normalization must interpret the individual measurement records rather than
fabricating more precise phase boundaries.

The snapshot under `contracts/` contains only the five schemas reachable from
raw-result/v2 and is pinned byte-for-byte to perfeng-contracts 0.13.0. Validation
never resolves schemas over the network.
