"""Assemble verified kube-burner output into a raw-result/v2 manifest."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError as SchemaValidationError

from scripts import benchmark, contracts
from scripts.evidence import (
    ARTIFACT_TYPES,
    TEST_ID,
    ManifestError,
    contained_file,
    exact_fields,
    measurement_descriptors,
    object_value,
    read_object,
    valid_location,
    validate_execution,
    validate_payload,
)


def build_manifest(
    capture_root: Path,
    request: Mapping[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    """Verify frozen bytes and storage receipts, then build raw-result/v2."""
    exact_fields(request, "manifest request", {"testId", "receipts"})
    if request["testId"] != TEST_ID:
        raise ManifestError("Manifest test identity is unsupported")
    execution = read_object(capture_root / "execution.json", "execution receipt")
    validate_execution(execution)
    descriptors = measurement_descriptors(execution)
    receipts = request["receipts"]
    if not isinstance(receipts, list) or len(receipts) != len(ARTIFACT_TYPES):
        raise ManifestError("Manifest request must contain three storage receipts")

    artifacts: list[dict[str, Any]] = []
    ids: set[str] = set()
    locations: set[str] = set()
    files: set[str] = set()
    for item in receipts:
        receipt = object_value(item, "storage receipt")
        exact_fields(receipt, "storage receipt", {"file", "artifact"})
        name = receipt["file"]
        if not isinstance(name, str):
            raise ManifestError("Receipt file must be a relative POSIX path")
        path = contained_file(capture_root, name)
        artifact = dict(object_value(receipt["artifact"], "artifact reference"))
        contracts.validate("artifact/v1/artifact-reference.schema.json", artifact)
        expected_type = ARTIFACT_TYPES.get(name)
        if (
            expected_type is None
            or artifact["runId"] != execution["runId"]
            or artifact["kind"] != "raw"
            or (artifact["mediaType"], artifact["format"]) != expected_type
            or not valid_location(artifact["uri"])
        ):
            raise ManifestError("Storage receipt does not describe supported run evidence")
        identity = artifact["id"].lower()
        if identity in ids or artifact["uri"] in locations or name in files:
            raise ManifestError("Storage receipt identity, URI, or file is duplicated")
        actual = benchmark.artifact(path, capture_root)
        descriptor = descriptors[name]
        if (
            actual["sha256"] != artifact["sha256"]
            or actual["sizeBytes"] != artifact["sizeBytes"]
            or actual != descriptor
            or actual["sizeBytes"] == 0
        ):
            raise ManifestError("Storage receipt does not match frozen measurement bytes")
        validate_payload(name, path.read_bytes(), execution["runId"])
        ids.add(identity)
        locations.add(artifact["uri"])
        files.add(name)
        artifacts.append(artifact)

    now = created_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    manifest = {
        "schemaVersion": 2,
        "kind": "RawResult",
        "contractsVersion": contracts.VERSION,
        "runId": execution["runId"],
        "testId": request["testId"],
        "workload": {field: execution["workload"][field] for field in ("id", "version", "sha256")},
        "producer": execution["tool"],
        "measurementWindow": {
            "start": execution["startedAt"],
            "end": execution["completedAt"],
        },
        "createdAt": now,
        "artifacts": artifacts,
    }
    contracts.validate("raw-result/v2/raw-result.schema.json", manifest)
    if datetime.fromisoformat(now) < datetime.fromisoformat(execution["completedAt"]):
        raise ManifestError("Manifest creation cannot precede benchmark completion")
    return manifest


def parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("capture_root")
    value.add_argument("request")
    value.add_argument("output")
    return value


def main(arguments: Sequence[str] | None = None) -> int:
    """Build a manifest without modifying capture files or contacting storage."""
    args = parser().parse_args(arguments)
    try:
        capture_root = Path(args.capture_root).expanduser().resolve(strict=True)
        request = read_object(Path(args.request).expanduser(), "manifest request")
        manifest = build_manifest(capture_root, request)
        output = Path(args.output).expanduser()
        with output.open("x", encoding="utf-8", newline="\n") as target:
            json.dump(manifest, target, indent=2)
            target.write("\n")
    except (ManifestError, SchemaValidationError, OSError, ValueError) as error:
        print(f"Kubernetes manifest error: {error}", file=sys.stderr)
        return 1
    print(f"Raw-result manifest written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
