"""Validation primitives for frozen kube-burner evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from scripts import benchmark, contracts, validate

TEST_ID = "pod-startup-k8s"
ARTIFACT_TYPES = {
    "jobSummary.json": ("application/json", "kube-burner-job-summary-json"),
    "podLatencyMeasurement-pod-startup-smoke.json": (
        "application/json",
        "kube-burner-pod-latency-json",
    ),
    "podLatencyQuantilesMeasurement-pod-startup-smoke.json": (
        "application/json",
        "kube-burner-pod-latency-quantiles-json",
    ),
}


class ManifestError(ValueError):
    """Kubernetes benchmark evidence is incomplete or inconsistent."""


def object_value(value: Any, location: str) -> Mapping[str, Any]:
    """Return a JSON object or reject the value."""
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ManifestError(f"{location} must be an object")
    return value


def exact_fields(value: Mapping[str, Any], location: str, fields: set[str]) -> None:
    """Require exactly the reviewed object fields."""
    if set(value) != fields:
        raise ManifestError(f"{location} fields are invalid")


def read_object(path: Path, location: str) -> Mapping[str, Any]:
    """Read one strict JSON object."""
    try:
        return object_value(contracts.parse_json(path.read_bytes()), location)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"Could not read {location}") from error


def contained_file(root: Path, name: Any) -> Path:
    """Resolve a regular capture file without permitting directory escape."""
    if not isinstance(name, str) or not name or "\\" in name:
        raise ManifestError("Receipt file must be a relative POSIX path")
    relative = PurePosixPath(name)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ManifestError("Receipt file must remain inside the capture directory")
    try:
        root = root.resolve(strict=True)
        path = root.joinpath(*relative.parts).resolve(strict=True)
    except OSError as error:
        raise ManifestError("Receipt file is unavailable") from error
    if not path.is_relative_to(root) or not path.is_file():
        raise ManifestError("Receipt file must remain inside the capture directory")
    return path


def valid_location(value: Any) -> bool:
    """Report whether a URI is stable, remote, and credential-free."""
    if not isinstance(value, str) or any(character in value for character in "?#\\"):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme in {"s3", "https"}
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def validate_execution(execution: Mapping[str, Any]) -> None:
    """Validate a successful receipt produced by this reviewed benchmark."""
    exact_fields(
        execution,
        "execution receipt",
        {
            "schemaVersion",
            "kind",
            "contractsVersion",
            "runId",
            "benchmark",
            "context",
            "startedAt",
            "completedAt",
            "exitCode",
            "namespaceRemoved",
            "tool",
            "workload",
            "inputs",
            "log",
            "measurements",
        },
    )
    if (
        execution["schemaVersion"] != 1
        or execution["kind"] != "KubernetesBenchmarkExecution"
        or execution["contractsVersion"] != contracts.VERSION
        or execution["benchmark"] != "pod-startup"
        or execution["exitCode"] != 0
        or execution["namespaceRemoved"] is not True
        or not isinstance(execution["runId"], str)
        or benchmark.RUN_ID_PATTERN.fullmatch(execution["runId"]) is None
    ):
        raise ManifestError("Execution receipt is not a successful reviewed benchmark")

    tool = object_value(execution["tool"], "execution tool")
    exact_fields(tool, "execution tool", {"name", "version", "artifact"})
    artifact = object_value(tool["artifact"], "execution tool artifact")
    release = validate.load_json(validate.RELEASE_PATH)
    assets = object_value(release["assets"], "pinned release assets")
    accepted = {
        (value["url"], value["sha256"], value["executableSha256"])
        for value in (object_value(item, "pinned release asset") for item in assets.values())
    }
    identity = (
        artifact.get("url"),
        artifact.get("archiveSha256"),
        artifact.get("executableSha256"),
    )
    if (
        tool["name"] != "kube-burner"
        or tool["version"] != release["version"]
        or identity not in accepted
    ):
        raise ManifestError("Execution tool does not match a pinned release asset")

    workload = object_value(execution["workload"], "execution workload")
    exact_fields(workload, "execution workload", {"file", "id", "version", "sha256"})
    expected_workload = read_object(validate.WORKLOAD_DEFINITION, "workload definition")
    if workload != {
        "file": validate.WORKLOAD_DEFINITION.relative_to(validate.ROOT).as_posix(),
        "id": expected_workload["id"],
        "version": expected_workload["version"],
        "sha256": benchmark.sha256_file(validate.WORKLOAD_DEFINITION),
    }:
        raise ManifestError("Execution workload identity does not match reviewed bytes")

    inputs = object_value(execution["inputs"], "execution inputs")
    exact_fields(inputs, "execution inputs", {"configSha256", "templateSha256", "containerImage"})
    if inputs != {
        "configSha256": benchmark.sha256_file(validate.WORKLOAD_ROOT / "config.yml"),
        "templateSha256": benchmark.sha256_file(validate.WORKLOAD_ROOT / "templates" / "pod.yml"),
        "containerImage": validate.EXPECTED_IMAGE,
    }:
        raise ManifestError("Execution inputs do not match reviewed benchmark bytes")

    try:
        started = datetime.fromisoformat(execution["startedAt"])
        completed = datetime.fromisoformat(execution["completedAt"])
    except (TypeError, ValueError) as error:
        raise ManifestError("Execution timestamps are invalid") from error
    if started.tzinfo is None or completed.tzinfo is None or started >= completed:
        raise ManifestError("Execution timestamps are not ordered")


def measurement_descriptors(execution: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Return the exact non-empty measurement set declared by execution."""
    measurements = execution["measurements"]
    if not isinstance(measurements, list) or len(measurements) != len(ARTIFACT_TYPES):
        raise ManifestError("Execution must declare the complete measurement set")
    result: dict[str, Mapping[str, Any]] = {}
    for item in measurements:
        descriptor = object_value(item, "execution measurement")
        exact_fields(descriptor, "execution measurement", {"path", "sha256", "sizeBytes"})
        path = descriptor["path"]
        if not isinstance(path, str) or path not in ARTIFACT_TYPES or path in result:
            raise ManifestError("Execution measurement path is unsupported or duplicated")
        result[path] = descriptor
    if set(result) != set(ARTIFACT_TYPES):
        raise ManifestError("Execution measurement set is incomplete")
    return result


def validate_payload(name: str, data: bytes, run_id: str) -> None:
    """Check the owned kube-burner JSON subset before accepting its bytes."""
    value = contracts.parse_json(data)
    if not isinstance(value, list) or not value:
        raise ManifestError("Measurement payload must be a non-empty JSON array")
    records = [object_value(item, "measurement record") for item in value]
    if any(record.get("uuid") != run_id for record in records):
        raise ManifestError("Measurement payload belongs to another run")
    if name == "jobSummary.json":
        if (
            len(records) != 1
            or records[0].get("metricName") != "jobSummary"
            or records[0].get("passed") is not True
        ):
            raise ManifestError("Job summary does not describe a successful run")
    elif name.startswith("podLatencyMeasurement-"):
        iterations = {record.get("jobIteration") for record in records}
        if (
            len(records) != 10
            or iterations != set(range(10))
            or any(record.get("metricName") != "podLatencyMeasurement" for record in records)
        ):
            raise ManifestError("Pod latency measurements are incomplete")
    elif any(record.get("metricName") != "podLatencyQuantilesMeasurement" for record in records):
        raise ManifestError("Pod latency quantiles are invalid")
