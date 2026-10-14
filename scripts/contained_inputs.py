"""Bind one control-plane-approved request to immutable packaged benchmark inputs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from scripts import contained_contracts as schema
from scripts import contracts

PACKAGE = schema.ROOT / "execution"
PROFILE_SHA256 = "b9fd1c55816ebb73b7b1ead490d53f4d53dae966be5e93b1bc45c9e0fc8489f5"
NODE_IMAGE = (
    "kindest/node:v1.35.0@sha256:452d707d4862f52530247495d180205e029056831160e22870e37e3f6c1ac31f"
)
CANDIDATE = (
    "registry.k8s.io/pause@sha256:278fb9dbcca9518083ad1e11276933a2e96f23de604a3a08cc3c80002767d24c"
)
MAXIMUM_FILE_BYTES = 8 * 1024 * 1024
FILES = {
    "jobSummary.json": ("application/json", "kube-burner-job-summary-json"),
    "podLatencyMeasurement-pod-startup-smoke.json": (
        "application/json",
        "kube-burner-pod-latency-json",
    ),
    "podLatencyQuantilesMeasurement-pod-startup-smoke.json": (
        "application/json",
        "kube-burner-pod-latency-quantiles-json",
    ),
    "resolved-inputs.json": ("application/json", "kubernetes-benchmark-inputs-json"),
    "qualification.json": ("application/json", "kubernetes-benchmark-evidence/v1"),
    "runner.log": ("text/plain", "runner-log"),
}


def digest(content: bytes) -> str:
    """Hash exact stored bytes, never a reconstructed JSON equivalent."""
    return hashlib.sha256(content).hexdigest()


def encode(value: Any) -> bytes:
    """Produce deterministic persisted JSON including its trailing newline."""
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def read(path: Path) -> bytes:
    """Read one bounded ordinary file and refuse redirected capture inputs."""
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise ValueError("Expected an ordinary input file")
    with path.open("rb") as source:
        data = source.read(MAXIMUM_FILE_BYTES + 1)
    if len(data) > MAXIMUM_FILE_BYTES:
        raise ValueError("Input exceeds the capture bound")
    return data


def object_json(data: bytes) -> dict[str, Any]:
    """Reject duplicate fields, non-finite numbers and non-object JSON input."""
    value = contracts.parse_json(data)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def exact(value: Any, fields: set[str]) -> dict[str, Any]:
    """Keep request boundaries closed and prevent unreviewed execution overrides."""
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Unexpected contained request fields")
    return value


@dataclass(frozen=True)
class Request:
    """Validated resolver input, not a reservation, lease or cleanup capability."""

    value: dict[str, Any]
    sha256: str
    environment: dict[str, Any]
    profile: dict[str, Any]

    @property
    def run_id(self) -> str:
        """Return the Run identity used for namespace labels and stable object keys."""
        return self.value["runId"]

    @property
    def namespace(self) -> str:
        """Return the separately owned per-Run namespace, never the executor namespace."""
        return self.value["namespace"]


def load(path: Path, expected_sha256: str) -> Request:
    """Validate the request checksum supplied by the resolver and all selected immutable bytes."""
    content = read(path)
    if digest(content) != expected_sha256:
        raise ValueError("Resolved request checksum differs")
    value = exact(
        object_json(content),
        {
            "schemaVersion",
            "runId",
            "testId",
            "runnerImage",
            "candidateImage",
            "workload",
            "namespace",
            "namespaceUid",
            "kubeSystemUid",
            "environment",
            "bucket",
            "templateSha256",
        },
    )
    if (
        type(value["schemaVersion"]) is not int
        or value["schemaVersion"] != 1
        or not isinstance(value["runId"], str)
        or re.fullmatch(r"perf-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", value["runId"]) is None
        or value["testId"] != "pod-startup-k8s"
        or value["namespace"] != "perfeng-benchmark-" + value["runId"]
        or value["candidateImage"] != CANDIDATE
        or not isinstance(value["runnerImage"], str)
        or re.fullmatch(
            r"ghcr\.io/stanimirivanov/perfeng-kube-burner@sha256:[a-f0-9]{64}", value["runnerImage"]
        )
        is None
        or not isinstance(value["bucket"], str)
        or re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", value["bucket"]) is None
    ):
        raise ValueError("Unsupported contained execution selection")
    for key in ("namespaceUid", "kubeSystemUid"):
        if str(UUID(value[key])) != value[key]:
            raise ValueError("Cluster and namespace UIDs must be canonical")
    workload = read(PACKAGE / "workload.json")
    if value["workload"] != {
        "id": "pod-startup-contained",
        "version": "1.0.0",
        "sha256": digest(workload),
    }:
        raise ValueError("Workload does not match packaged inputs")
    definition = object_json(workload)
    if definition["configuration"]["sha256"] != digest(read(PACKAGE / "config.yml")):
        raise ValueError("Packaged workload configuration differs")
    if value["templateSha256"] != digest(read(PACKAGE / "pod.yml")):
        raise ValueError("Packaged workload template differs")
    profile_bytes = read(PACKAGE / "profile.json")
    if digest(profile_bytes) != PROFILE_SHA256:
        raise ValueError("Reviewed environment profile differs")
    profile = object_json(profile_bytes)
    environment_bytes = read(path.parent / "environment.json")
    environment = object_json(environment_bytes)
    schema.validate("environment", environment)
    selected = exact(value["environment"], {"id", "version", "sha256", "fingerprint"})
    if (
        selected["id"] != profile["metadata"]["id"]
        or selected["version"] != profile["metadata"]["version"]
        or selected["sha256"] != digest(environment_bytes)
        or selected["fingerprint"] != environment.get("fingerprint")
    ):
        raise ValueError("Selected environment bytes or cohort identity differ")
    return Request(value, expected_sha256, environment, profile)


def resolve(request: Request, output: Path) -> dict[str, str]:
    """Freeze all substitutions; only kube-burner's iteration variable remains templated."""
    values = {
        "__TARGET_NAMESPACE__": request.namespace,
        "__RUN_ID__": request.run_id,
        "__METRICS_DIRECTORY__": json.dumps(output.as_posix()),
    }
    files = {}
    for name in ("config.yml", "pod.yml"):
        text = read(PACKAGE / name).decode("utf-8")
        for key, value in values.items():
            text = text.replace(key, value)
        files[name] = text
    return files


def resolved_document(request: Request, output: Path) -> dict[str, Any]:
    """Define the input evidence once so the publisher independently verifies the complete closure."""
    return {
        "schemaVersion": 1,
        "runId": request.run_id,
        "requestSha256": request.sha256,
        "workload": request.value["workload"],
        "templateSha256": request.value["templateSha256"],
        "candidateImage": request.value["candidateImage"],
        "substitutions": {
            "namespace": request.namespace,
            "runId": request.run_id,
            "metricsDirectory": output.as_posix(),
        },
        "files": resolve(request, output),
    }
