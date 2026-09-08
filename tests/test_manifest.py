from __future__ import annotations

import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from scripts import benchmark, contracts, manifest, validate

RUN_ID = "perf-20260908-120000-a1b2c3d4"


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def payloads() -> dict[str, bytes]:
    common = {"uuid": RUN_ID, "jobName": "pod-startup-smoke"}
    return {
        "jobSummary.json": json_bytes([{**common, "metricName": "jobSummary", "passed": True}]),
        "podLatencyMeasurement-pod-startup-smoke.json": json_bytes(
            [
                {
                    **common,
                    "metricName": "podLatencyMeasurement",
                    "jobIteration": iteration,
                    "podReadyLatency": 10 + iteration,
                }
                for iteration in range(10)
            ]
        ),
        "podLatencyQuantilesMeasurement-pod-startup-smoke.json": json_bytes(
            [
                {
                    **common,
                    "metricName": "podLatencyQuantilesMeasurement",
                    "quantileName": "Ready",
                    "P95": 19,
                }
            ]
        ),
    }


def file_claim(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "sizeBytes": len(data),
    }


def execution(root: Path) -> dict[str, Any]:
    asset = benchmark.host_asset()
    measurements = [file_claim(root / name) for name in manifest.ARTIFACT_TYPES]
    return {
        "schemaVersion": 1,
        "kind": "KubernetesBenchmarkExecution",
        "contractsVersion": contracts.VERSION,
        "runId": RUN_ID,
        "benchmark": "pod-startup",
        "context": "kind-perfeng-local",
        "startedAt": "2026-09-08T12:00:00Z",
        "completedAt": "2026-09-08T12:01:00Z",
        "exitCode": 0,
        "namespaceRemoved": True,
        "tool": {
            "name": "kube-burner",
            "version": asset.version,
            "artifact": {
                "kind": "release-archive",
                "url": asset.url,
                "archiveSha256": asset.archive_sha256,
                "executableSha256": asset.executable_sha256,
            },
        },
        "workload": {
            "file": validate.WORKLOAD_DEFINITION.relative_to(validate.ROOT).as_posix(),
            "id": "pod-startup-smoke",
            "version": "1.0.0",
            "sha256": benchmark.sha256_file(validate.WORKLOAD_DEFINITION),
        },
        "inputs": {
            "configSha256": benchmark.sha256_file(validate.WORKLOAD_ROOT / "config.yml"),
            "templateSha256": benchmark.sha256_file(
                validate.WORKLOAD_ROOT / "templates" / "pod.yml"
            ),
            "containerImage": validate.EXPECTED_IMAGE,
        },
        "log": {"path": "runner.log", "sha256": "a" * 64, "sizeBytes": 1},
        "measurements": measurements,
    }


def request(root: Path) -> dict[str, Any]:
    receipts = []
    for index, (name, (media_type, artifact_format)) in enumerate(
        manifest.ARTIFACT_TYPES.items(), start=1
    ):
        claim = file_claim(root / name)
        receipts.append(
            {
                "file": name,
                "artifact": {
                    "id": f"{index:08d}-1111-4111-8111-111111111111",
                    "runId": RUN_ID,
                    "kind": "raw",
                    "uri": f"s3://perfeng-artifacts/runs/{RUN_ID}/raw/{name}",
                    "sha256": claim["sha256"],
                    "sizeBytes": claim["sizeBytes"],
                    "mediaType": media_type,
                    "format": artifact_format,
                },
            }
        )
    return {"testId": manifest.TEST_ID, "receipts": receipts}


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for name, data in payloads().items():
            (self.root / name).write_bytes(data)
        (self.root / "execution.json").write_text(
            json.dumps(execution(self.root)), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_builds_contract_valid_release_archive_manifest(self) -> None:
        value = manifest.build_manifest(
            self.root,
            request(self.root),
            "2026-09-08T12:01:01Z",
        )

        contracts.validate("raw-result/v2/raw-result.schema.json", value)
        self.assertEqual(value["producer"]["artifact"]["kind"], "release-archive")
        self.assertEqual(len(value["artifacts"]), 3)
        self.assertEqual(value["measurementWindow"]["start"], "2026-09-08T12:00:00Z")

    def test_canonicalizes_capture_root_before_computing_relative_paths(self) -> None:
        aliased_root = MagicMock(spec=Path)
        aliased_root.resolve.return_value = self.root.resolve(strict=True)

        value = manifest.build_manifest(
            aliased_root,
            request(self.root),
            "2026-09-08T12:01:01Z",
        )

        aliased_root.resolve.assert_called_once_with(strict=True)
        self.assertEqual(len(value["artifacts"]), 3)

    def test_rejects_changed_bytes_and_storage_claims(self) -> None:
        mutations = {
            "changed bytes": lambda value: (self.root / value["receipts"][0]["file"]).write_bytes(
                b"[]"
            ),
            "credentials": lambda value: value["receipts"][0]["artifact"].update(
                uri="https://user@example.com/result.json"
            ),
            "wrong run": lambda value: value["receipts"][0]["artifact"].update(
                runId="perf-20260908-120000-deadbeef"
            ),
            "duplicate receipt": lambda value: value["receipts"].__setitem__(
                1, copy.deepcopy(value["receipts"][0])
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                current = request(self.root)
                original = (self.root / next(iter(manifest.ARTIFACT_TYPES))).read_bytes()
                mutate(current)
                with self.assertRaises((manifest.ManifestError, ValueError)):
                    manifest.build_manifest(self.root, current, "2026-09-08T12:01:01Z")
                (self.root / next(iter(manifest.ARTIFACT_TYPES))).write_bytes(original)

    def test_rejects_incomplete_native_measurements(self) -> None:
        path = self.root / "podLatencyMeasurement-pod-startup-smoke.json"
        path.write_bytes(json_bytes(contracts.parse_json(path.read_bytes())[:-1]))
        changed_execution = execution(self.root)
        (self.root / "execution.json").write_text(json.dumps(changed_execution), encoding="utf-8")
        with self.assertRaisesRegex(manifest.ManifestError, "incomplete"):
            manifest.build_manifest(
                self.root,
                request(self.root),
                "2026-09-08T12:01:01Z",
            )

    def test_cli_never_overwrites_existing_output(self) -> None:
        request_path = self.root / "request.json"
        request_path.write_text(json.dumps(request(self.root)), encoding="utf-8")
        output = self.root / "raw-result.json"
        output.write_text("keep", encoding="utf-8")
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            result = manifest.main([str(self.root), str(request_path), str(output)])

        self.assertEqual(result, 1)
        self.assertEqual(output.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
