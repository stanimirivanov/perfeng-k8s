"""Validate repository-owned Kubernetes benchmark definitions."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Never

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ROOT = ROOT / "workloads" / "pod-startup"
RELEASE_PATH = ROOT / "toolchain" / "kube-burner.json"
IMAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:/-]*@sha256:[a-f0-9]{64}$")
HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
EXPECTED_IMAGE = (
    "registry.k8s.io/pause:3.10.1@sha256:"
    "278fb9dbcca9518083ad1e11276933a2e96f23de604a3a08cc3c80002767d24c"
)


class ValidationError(ValueError):
    """A repository definition violates its reviewed contract."""


def fail(message: str) -> Never:
    """Raise a consistently classified validation error."""
    raise ValidationError(message)


def mapping(value: Any, location: str) -> Mapping[str, Any]:
    """Return a string-keyed mapping or reject the value."""
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        fail(f"{location} must be an object")
    return value


def sequence(value: Any, location: str) -> list[Any]:
    """Return a list or reject the value."""
    if not isinstance(value, list):
        fail(f"{location} must be an array")
    return value


def exact_keys(value: Mapping[str, Any], location: str, expected: set[str]) -> None:
    """Reject missing and unknown fields."""
    if set(value) != expected:
        fail(f"{location} fields must be exactly {sorted(expected)}")


def positive_integer(value: Any, location: str, maximum: int) -> int:
    """Return a bounded positive integer or reject the value."""
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        fail(f"{location} must be an integer from 1 through {maximum}")
    return value


def display_path(path: Path) -> str:
    """Return a stable repository-relative path when available."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def load_yaml(path: Path) -> Mapping[str, Any]:
    """Load exactly one YAML object."""
    try:
        documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValidationError(f"Could not read {display_path(path)}") from error
    if len(documents) != 1:
        fail(f"{display_path(path)} must contain exactly one YAML document")
    return mapping(documents[0], display_path(path))


def load_json(path: Path) -> Mapping[str, Any]:
    """Load one JSON object while rejecting duplicate fields."""

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                fail(f"{display_path(path)} contains duplicate field {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"Could not read {display_path(path)}") from error
    return mapping(value, display_path(path))


def validate_release() -> None:
    """Validate the pinned kube-burner release and acquisition metadata."""
    release = load_json(RELEASE_PATH)
    exact_keys(
        release,
        "kube-burner release",
        {"schemaVersion", "name", "version", "source", "assets"},
    )
    if release["schemaVersion"] != 1 or release["name"] != "kube-burner":
        fail("kube-burner release identity is invalid")
    version = release["version"]
    if not isinstance(version, str) or VERSION_PATTERN.fullmatch(version) is None:
        fail("kube-burner version must be semantic")
    expected_source = f"https://github.com/kube-burner/kube-burner/releases/tag/v{version}"
    if release["source"] != expected_source:
        fail("kube-burner source must identify the exact upstream release")

    assets = mapping(release["assets"], "kube-burner assets")
    exact_keys(assets, "kube-burner assets", {"linux-amd64", "windows-amd64"})
    filenames = {
        "linux-amd64": f"kube-burner-V{version}-linux-x86_64.tar.gz",
        "windows-amd64": f"kube-burner-V{version}-windows-x86_64.zip",
    }
    for platform, filename in filenames.items():
        asset = mapping(assets[platform], f"kube-burner asset {platform}")
        exact_keys(
            asset,
            f"kube-burner asset {platform}",
            {"url", "sha256", "executableSha256"},
        )
        expected_url = (
            f"https://github.com/kube-burner/kube-burner/releases/download/v{version}/{filename}"
        )
        if asset["url"] != expected_url:
            fail(f"kube-burner asset {platform} has an unexpected URL")
        for field in ("sha256", "executableSha256"):
            digest = asset[field]
            if not isinstance(digest, str) or HASH_PATTERN.fullmatch(digest) is None:
                fail(f"kube-burner asset {platform} has an invalid {field}")


def validate_metrics(config: Mapping[str, Any]) -> None:
    """Require one local indexer and the pod-latency measurement."""
    endpoints = sequence(config["metricsEndpoints"], "metricsEndpoints")
    if len(endpoints) != 1:
        fail("metricsEndpoints must contain one local output")
    endpoint = mapping(endpoints[0], "metricsEndpoints[0]")
    exact_keys(endpoint, "metricsEndpoints[0]", {"alias", "indexer"})
    if endpoint["alias"] != "local-results":
        fail("the local indexer alias must be local-results")
    indexer = mapping(endpoint["indexer"], "metricsEndpoints[0].indexer")
    exact_keys(indexer, "metricsEndpoints[0].indexer", {"type", "metricsDirectory"})
    if indexer["type"] != "local" or indexer["metricsDirectory"] != "{{.METRICS_DIRECTORY}}":
        fail("benchmark measurements must use the caller-selected local directory")

    global_config = mapping(config["global"], "global")
    exact_keys(global_config, "global", {"gc", "clusterHealth", "measurements"})
    if global_config["gc"] is not True or global_config["clusterHealth"] is not True:
        fail("benchmark cleanup and cluster health checks must remain enabled")
    measurements = sequence(global_config["measurements"], "global.measurements")
    if len(measurements) != 1:
        fail("global.measurements must contain only podLatency")
    measurement = mapping(measurements[0], "global.measurements[0]")
    exact_keys(
        measurement,
        "global.measurements[0]",
        {"name", "timeseriesIndexer", "quantilesIndexer"},
    )
    if measurement != {
        "name": "podLatency",
        "timeseriesIndexer": "local-results",
        "quantilesIndexer": "local-results",
    }:
        fail("podLatency must write timeseries and quantiles to local-results")


def validate_template(path: Path) -> None:
    """Validate the bounded pod template and its security posture."""
    pod = load_yaml(path)
    exact_keys(pod, "pod template", {"apiVersion", "kind", "metadata", "spec"})
    if pod["apiVersion"] != "v1" or pod["kind"] != "Pod":
        fail("object template must contain a v1 Pod")
    metadata = mapping(pod["metadata"], "pod template metadata")
    exact_keys(metadata, "pod template metadata", {"name", "labels"})
    if metadata["name"] != "perfeng-pod-startup-{{.Iteration}}":
        fail("pod template name must include the kube-burner iteration")
    if metadata["labels"] != {"perfeng.io/benchmark": "pod-startup"}:
        fail("pod template must retain its benchmark label")

    spec = mapping(pod["spec"], "pod template spec")
    exact_keys(
        spec,
        "pod template spec",
        {
            "automountServiceAccountToken",
            "enableServiceLinks",
            "restartPolicy",
            "terminationGracePeriodSeconds",
            "securityContext",
            "containers",
        },
    )
    if (
        spec["automountServiceAccountToken"] is not False
        or spec["enableServiceLinks"] is not False
        or spec["restartPolicy"] != "Never"
        or spec["terminationGracePeriodSeconds"] != 0
    ):
        fail("pod template lifecycle or service-account policy is invalid")
    if spec["securityContext"] != {
        "runAsNonRoot": True,
        "runAsUser": 65532,
        "runAsGroup": 65532,
        "seccompProfile": {"type": "RuntimeDefault"},
    }:
        fail("pod template security context is invalid")

    containers = sequence(spec["containers"], "pod template containers")
    if len(containers) != 1:
        fail("pod template must contain one container")
    container = mapping(containers[0], "pod template container")
    exact_keys(
        container,
        "pod template container",
        {"name", "image", "imagePullPolicy", "resources", "securityContext"},
    )
    if (
        container["name"] != "pause"
        or container["image"] != "{{.containerImage}}"
        or container["imagePullPolicy"] != "IfNotPresent"
    ):
        fail("pod template container identity is invalid")
    if container["resources"] != {
        "requests": {"cpu": "1m", "memory": "1Mi"},
        "limits": {"cpu": "10m", "memory": "16Mi"},
    }:
        fail("pod template resources are invalid")
    if container["securityContext"] != {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }:
        fail("pod template container security context is invalid")


def validate_workload() -> None:
    """Validate the bounded pod-startup workload and referenced template."""
    config = load_yaml(WORKLOAD_ROOT / "config.yml")
    exact_keys(config, "benchmark config", {"metricsEndpoints", "global", "jobs"})
    validate_metrics(config)

    jobs = sequence(config["jobs"], "jobs")
    if len(jobs) != 1:
        fail("jobs must contain one pod-startup workload")
    job = mapping(jobs[0], "jobs[0]")
    exact_keys(
        job,
        "jobs[0]",
        {
            "name",
            "jobIterations",
            "qps",
            "burst",
            "preLoadImages",
            "namespacedIterations",
            "namespace",
            "waitWhenFinished",
            "podWait",
            "objects",
        },
    )
    if job["name"] != "pod-startup-smoke" or job["namespace"] != "perfeng-pod-startup":
        fail("pod-startup job identity is invalid")
    if positive_integer(job["jobIterations"], "jobs[0].jobIterations", 25) != 10:
        fail("pod-startup smoke must create exactly ten pods")
    if positive_integer(job["qps"], "jobs[0].qps", 5) != 2 or job["burst"] != 2:
        fail("pod-startup smoke must remain a low-rate workload")
    if (
        job["preLoadImages"] is not True
        or job["namespacedIterations"] is not False
        or job["waitWhenFinished"] is not True
        or job["podWait"] is not False
    ):
        fail("pod-startup execution controls are invalid")

    objects = sequence(job["objects"], "jobs[0].objects")
    if len(objects) != 1:
        fail("pod-startup job must reference one object template")
    object_config = mapping(objects[0], "jobs[0].objects[0]")
    exact_keys(object_config, "jobs[0].objects[0]", {"objectTemplate", "replicas", "inputVars"})
    if object_config["replicas"] != 1:
        fail("each pod-startup iteration must create one pod")
    relative_name = object_config["objectTemplate"]
    if not isinstance(relative_name, str):
        fail("objectTemplate must be a relative POSIX path")
    relative_path = PurePosixPath(relative_name)
    if relative_path.is_absolute() or ".." in relative_path.parts or "\\" in relative_name:
        fail("objectTemplate must remain inside the workload directory")
    inputs = mapping(object_config["inputVars"], "jobs[0].objects[0].inputVars")
    exact_keys(inputs, "jobs[0].objects[0].inputVars", {"containerImage"})
    image = inputs["containerImage"]
    if (
        not isinstance(image, str)
        or IMAGE_PATTERN.fullmatch(image) is None
        or image != EXPECTED_IMAGE
    ):
        fail("pod-startup image must match the reviewed immutable pause image")

    validate_template(WORKLOAD_ROOT / Path(*relative_path.parts))


def validate() -> None:
    """Validate all repository-owned benchmark definitions."""
    validate_release()
    validate_workload()


def main() -> int:
    """Run validation with stable, non-sensitive diagnostics."""
    try:
        validate()
    except ValidationError as error:
        print(f"Kubernetes benchmark validation failed: {error}", file=sys.stderr)
        return 1
    print("Kubernetes benchmark definitions are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
