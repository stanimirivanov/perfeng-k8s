"""Validate repository-owned Kubernetes benchmark definitions."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Never

import yaml

from scripts import contracts

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ROOT = ROOT / "workloads" / "pod-startup"
WORKLOAD_DEFINITION = WORKLOAD_ROOT / "workload.json"
RELEASE_PATH = ROOT / "toolchain" / "kube-burner.json"
BUNDLE_ROOT = ROOT / "bundles" / "local-kind-windows" / "1.0.0"
IMAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:/-]*@sha256:[a-f0-9]{64}$")
HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
EXPECTED_IMAGE = (
    "registry.k8s.io/pause:3.10.1@sha256:"
    "278fb9dbcca9518083ad1e11276933a2e96f23de604a3a08cc3c80002767d24c"
)
ANALYSIS_IMAGE = (
    "ghcr.io/stanimirivanov/perfeng-analysis@sha256:"
    "eb13b5d8074467fb23a1d10041f0f75606af192cd68385e30e56cd172d97b0ed"
)
ANALYSIS_REVISION = "cc7c84ba3e373aa3245a6091b3c24714fe2c37e8"
ENVIRONMENT_REVISION = "e0b95cb10cdabb9be95543947b6552b51aa81832"
TRANSFER_IMAGE = (
    "amazon/aws-cli:2.36.37@sha256:be6228bd99b4b0b9787543952aebfe93c66b5503121b68a724647c523c957a9d"
)
STAGING_ENVIRONMENT = {
    "PERFENG_RAW_MANIFEST_ARTIFACT_ID",
    "PERFENG_RAW_MANIFEST_URI",
    "PERFENG_RAW_MANIFEST_SHA256",
    "PERFENG_RAW_MANIFEST_SIZE_BYTES",
    "PERFENG_RAW_MANIFEST_PATH",
    "PERFENG_SOURCE_ARTIFACT_ID",
    "PERFENG_SOURCE_URI",
    "PERFENG_SOURCE_SHA256",
    "PERFENG_SOURCE_SIZE_BYTES",
    "PERFENG_SOURCE_PATH",
}


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
    definition = load_json(WORKLOAD_DEFINITION)
    contracts.validate("workload/v1/workload.schema.json", definition)
    if (
        definition["id"] != "pod-startup-smoke"
        or definition["version"] != "1.0.0"
        or definition["tool"] != "kube-burner"
        or definition["profile"] != "smoke"
        or definition["model"] != "open"
        or definition["configuration"]["path"] != "workloads/pod-startup/config.yml"
    ):
        fail("pod-startup workload definition identity is invalid")

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

    config_digest = hashlib.sha256((WORKLOAD_ROOT / "config.yml").read_bytes()).hexdigest()
    if definition["configuration"]["sha256"] != config_digest:
        fail("pod-startup workload configuration checksum does not match")


def file_digest(path: Path) -> str:
    """Return the lowercase SHA-256 of one reviewed file."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ValidationError(f"Could not read {display_path(path)}") from error


def validate_analysis_job() -> None:
    """Validate the reviewed reusable normalization Job template."""
    job = load_yaml(BUNDLE_ROOT / "jobs" / "analysis.yaml")
    exact_keys(job, "analysis Job", {"apiVersion", "kind", "metadata", "spec"})
    if job["apiVersion"] != "batch/v1" or job["kind"] != "Job":
        fail("analysis template must contain one batch/v1 Job")

    labels = {
        "app.kubernetes.io/name": "perfeng-analysis",
        "app.kubernetes.io/component": "normalization",
    }
    metadata = mapping(job["metadata"], "analysis Job metadata")
    if metadata != {"labels": labels}:
        fail("analysis Job must remain reusable and carry only reviewed labels")

    spec = mapping(job["spec"], "analysis Job spec")
    exact_keys(
        spec,
        "analysis Job spec",
        {"backoffLimit", "completions", "parallelism", "activeDeadlineSeconds", "template"},
    )
    if (
        spec["backoffLimit"] != 0
        or spec["completions"] != 1
        or spec["parallelism"] != 1
        or spec["activeDeadlineSeconds"] != 600
    ):
        fail("analysis Job execution bounds are invalid")

    template = mapping(spec["template"], "analysis Pod template")
    exact_keys(template, "analysis Pod template", {"metadata", "spec"})
    if template["metadata"] != {"labels": labels}:
        fail("analysis Pod labels are invalid")
    pod = mapping(template["spec"], "analysis Pod spec")
    exact_keys(
        pod,
        "analysis Pod spec",
        {
            "restartPolicy",
            "automountServiceAccountToken",
            "enableServiceLinks",
            "nodeSelector",
            "tolerations",
            "securityContext",
            "initContainers",
            "containers",
            "volumes",
        },
    )
    if (
        pod["restartPolicy"] != "Never"
        or pod["automountServiceAccountToken"] is not False
        or pod["enableServiceLinks"] is not False
        or pod["nodeSelector"] != {"kubernetes.io/os": "linux", "workload": "control-plane"}
    ):
        fail("analysis Pod scheduling or service-account policy is invalid")
    if pod["tolerations"] != [
        {
            "key": "node-role.kubernetes.io/control-plane",
            "operator": "Exists",
            "effect": "NoSchedule",
        }
    ]:
        fail("analysis Pod tolerations are invalid")
    if pod["securityContext"] != {
        "runAsNonRoot": True,
        "runAsUser": 65532,
        "runAsGroup": 65532,
        "fsGroup": 65532,
        "fsGroupChangePolicy": "OnRootMismatch",
        "seccompProfile": {"type": "RuntimeDefault"},
    }:
        fail("analysis Pod security context is invalid")

    initializers = sequence(pod["initContainers"], "analysis initContainers")
    containers = sequence(pod["containers"], "analysis containers")
    if len(initializers) != 1 or len(containers) != 1:
        fail("analysis Job must contain one input initializer and one normalizer")
    validate_analysis_input_container(mapping(initializers[0], "analysis input container"))
    validate_analysis_normalizer(mapping(containers[0], "analysis normalizer"))

    if pod["volumes"] != [
        {"name": "analysis-input", "emptyDir": {"sizeLimit": "64Mi"}},
        {"name": "analysis-output", "emptyDir": {"sizeLimit": "64Mi"}},
        {"name": "transfer-tmp", "emptyDir": {"sizeLimit": "16Mi"}},
    ]:
        fail("analysis Job volumes are invalid")


def validate_analysis_input_container(container: Mapping[str, Any]) -> None:
    """Validate the input initializer without predefining control-plane metadata."""
    exact_keys(
        container,
        "analysis input container",
        {
            "name",
            "image",
            "imagePullPolicy",
            "command",
            "args",
            "env",
            "securityContext",
            "resources",
            "volumeMounts",
        },
    )
    if (
        container["name"] != "stage-inputs"
        or container["image"] != TRANSFER_IMAGE
        or container["imagePullPolicy"] != "IfNotPresent"
        or container["command"] != ["/bin/sh", "-ec"]
    ):
        fail("analysis input container identity is invalid")

    arguments = sequence(container["args"], "analysis input container args")
    if len(arguments) != 1 or not isinstance(arguments[0], str):
        fail("analysis input container must have one staging program")
    program = arguments[0]
    required_program_fragments = {
        'case "$uri" in',
        "s3://perfeng-artifacts/runs/*",
        's3 cp "$uri" "$partial" --only-show-errors',
        'test "$(wc -c < "$partial" | tr -d \'[:space:]\')" = "$expected_size"',
        'printf \'%s  %s\\n\' "$expected_sha256" "$partial" | sha256sum -c -',
        'mv "$partial" "$destination"',
    }
    required_program_fragments.update(f'"${name}"' for name in STAGING_ENVIRONMENT)
    if any(fragment not in program for fragment in required_program_fragments):
        fail("analysis input staging integrity checks are incomplete")

    environment = sequence(container["env"], "analysis input container env")
    variables = [mapping(item, "analysis input environment variable") for item in environment]
    names = [variable.get("name") for variable in variables]
    if any(name in STAGING_ENVIRONMENT for name in names):
        fail("analysis template must not predefine reserved staging environment")
    expected_names = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "PERFENG_S3_ENDPOINT",
        "HOME",
        "AWS_CONFIG_FILE",
        "AWS_DEFAULT_REGION",
        "AWS_EC2_METADATA_DISABLED",
        "AWS_PAGER",
        "AWS_MAX_ATTEMPTS",
    ]
    if names != expected_names:
        fail("analysis input environment is invalid")
    for variable, key in zip(variables[:2], ("access-key", "secret-key"), strict=True):
        if variable != {
            "name": variable["name"],
            "valueFrom": {"secretKeyRef": {"name": "perfeng-s3-uploader-auth", "key": key}},
        }:
            fail("analysis input credentials are not the restricted uploader Secret")
    values = {variable["name"]: variable.get("value") for variable in variables[2:]}
    if values != {
        "PERFENG_S3_ENDPOINT": "http://seaweedfs.perf-platform.svc.cluster.local:8333",
        "HOME": "/tmp",
        "AWS_CONFIG_FILE": "/tmp/awsconfig",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_PAGER": "",
        "AWS_MAX_ATTEMPTS": "2",
    }:
        fail("analysis input storage configuration is invalid")
    validate_analysis_container_policy(container, "input")
    if container["volumeMounts"] != [
        {"name": "analysis-input", "mountPath": "/workspace/input"},
        {"name": "transfer-tmp", "mountPath": "/tmp"},
    ]:
        fail("analysis input volume mounts are invalid")


def validate_analysis_normalizer(container: Mapping[str, Any]) -> None:
    """Validate the credential-free normalizer placeholder replaced by the control plane."""
    exact_keys(
        container,
        "analysis normalizer",
        {
            "name",
            "image",
            "imagePullPolicy",
            "securityContext",
            "resources",
            "volumeMounts",
        },
    )
    if (
        container["name"] != "normalizer"
        or container["image"] != ANALYSIS_IMAGE
        or container["imagePullPolicy"] != "IfNotPresent"
    ):
        fail("analysis normalizer identity is invalid")
    validate_analysis_container_policy(container, "normalizer")
    if container["volumeMounts"] != [
        {"name": "analysis-input", "mountPath": "/workspace/input", "readOnly": True},
        {"name": "analysis-output", "mountPath": "/workspace/output"},
    ]:
        fail("analysis normalizer volume mounts are invalid")


def validate_analysis_container_policy(container: Mapping[str, Any], name: str) -> None:
    """Validate common non-privileged container and bounded-resource policy."""
    if container["securityContext"] != {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }:
        fail(f"analysis {name} security context is invalid")
    resources = mapping(container["resources"], f"analysis {name} resources")
    expected_resources = {
        "input": {
            "requests": {"cpu": "50m", "memory": "96Mi"},
            "limits": {"cpu": "500m", "memory": "256Mi"},
        },
        "normalizer": {
            "requests": {"cpu": "100m", "memory": "128Mi"},
            "limits": {"cpu": "1", "memory": "512Mi"},
        },
    }
    if resources != expected_resources[name]:
        fail(f"analysis {name} resources are invalid")


def validate_bundle() -> None:
    """Validate the repository-owned identities of the first runtime bundle."""
    registry = load_json(BUNDLE_ROOT / "registry.json")
    entries = sequence(registry.get("entries"), "runtime bundle entries")
    if registry.get("schemaVersion") != 1 or len(entries) != 1:
        fail("runtime bundle must contain exactly one schema version 1 entry")
    entry = mapping(entries[0], "runtime bundle entry")

    catalogue = load_json(BUNDLE_ROOT / "identities" / "catalogue.json")
    environment = load_json(BUNDLE_ROOT / "identities" / "environment.json")
    analysis = load_json(BUNDLE_ROOT / "identities" / "analysis-image.json")
    workload_digest = file_digest(WORKLOAD_DEFINITION)
    windows_asset = mapping(
        mapping(load_json(RELEASE_PATH)["assets"], "kube-burner assets")["windows-amd64"],
        "kube-burner windows asset",
    )

    if entry.get("testId") != "pod-startup-k8s" or entry.get("contractsVersion") != "0.13.0":
        fail("runtime bundle test or contracts identity is invalid")
    if entry.get("profile") != "smoke" or entry.get("dataset") != {"kind": "none"}:
        fail("runtime bundle profile or dataset is invalid")
    if entry.get("candidateImages") != [EXPECTED_IMAGE]:
        fail("runtime bundle candidate image is not the reviewed workload image")
    if entry.get("principals") != ["local-operator"]:
        fail("runtime bundle local authorization is invalid")
    if entry.get("normalization") != {
        "sourceFormat": "kube-burner-pod-latency-json",
        "layout": "",
    }:
        fail("runtime bundle normalization profile is invalid")

    raw_producer = mapping(entry.get("rawProducer"), "runtime raw producer")
    raw_artifact = mapping(raw_producer.get("artifact"), "runtime raw producer artifact")
    if raw_producer.get("name") != "kube-burner" or raw_producer.get("version") != "2.8.5":
        fail("runtime bundle kube-burner identity is invalid")
    if raw_artifact != {
        "kind": "release-archive",
        "url": windows_asset["url"],
        "archiveSha256": windows_asset["sha256"],
        "executableSha256": windows_asset["executableSha256"],
    }:
        fail("runtime bundle does not use the reviewed Windows kube-burner archive")

    for field in ("normalizerProducer", "reportProducer"):
        if entry.get(field) != {
            "name": "perfeng-analysis",
            "version": "0.8.0",
            "image": ANALYSIS_IMAGE,
        }:
            fail(f"runtime bundle {field} is not the verified analysis image")
    if analysis != {
        "schemaVersion": 1,
        "name": "perfeng-analysis",
        "version": "0.8.0",
        "image": ANALYSIS_IMAGE,
        "source": {
            "repository": "https://github.com/stanimirivanov/perfeng-analysis",
            "gitSha": ANALYSIS_REVISION,
        },
        "platform": "linux/amd64",
    }:
        fail("runtime bundle analysis image provenance is invalid")

    catalogue_reference = mapping(entry.get("catalogue"), "runtime catalogue")
    if catalogue_reference != {
        "id": catalogue.get("id"),
        "version": catalogue.get("version"),
        "sha256": file_digest(BUNDLE_ROOT / "identities" / "catalogue.json"),
    }:
        fail("runtime bundle catalogue reference does not match its reviewed bytes")
    workload_reference = mapping(entry.get("workload"), "runtime workload")
    if workload_reference != {
        "id": "pod-startup-smoke",
        "version": "1.0.0",
        "sha256": workload_digest,
    }:
        fail("runtime bundle workload reference does not match its reviewed bytes")

    environment_reference = mapping(entry.get("environment"), "runtime environment")
    source = mapping(environment.get("source"), "runtime environment source")
    cluster = mapping(environment.get("cluster"), "runtime environment cluster")
    if source.get("gitSha") != ENVIRONMENT_REVISION:
        fail("runtime bundle environment source revision is invalid")
    if environment_reference != {
        "id": environment.get("id"),
        "version": environment.get("version"),
        "sha256": file_digest(BUNDLE_ROOT / "identities" / "environment.json"),
        "fingerprint": cluster.get("sha256"),
    }:
        fail("runtime bundle environment reference does not match its reviewed bytes")

    validate_analysis_job()


def validate() -> None:
    """Validate all repository-owned benchmark definitions."""
    validate_release()
    validate_workload()
    validate_bundle()


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
