"""Render and validate repository-owned platform deployment charts."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Never

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE_CHART = ROOT / "charts" / "control-plane"
CONTROL_PLANE_VALUES = ROOT / "testdata" / "control-plane-values.yaml"
CONTROL_PLANE_IMAGE = re.compile(
    r"^ghcr\.io/stanimirivanov/perfeng-control-plane@sha256:[0-9a-f]{64}$"
)


class DeploymentValidationError(ValueError):
    """A platform deployment definition violates its reviewed boundary."""


def fail(message: str) -> Never:
    """Raise a consistently classified deployment validation error."""
    raise DeploymentValidationError(message)


def mapping(value: Any, location: str) -> Mapping[str, Any]:
    """Return a string-keyed mapping or reject the value."""
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        fail(f"{location} must be an object")
    return value


def sequence(value: Any, location: str) -> Sequence[Any]:
    """Return a non-string sequence or reject the value."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        fail(f"{location} must be an array")
    return value


def helm(*arguments: str, succeeds: bool = True) -> bytes:
    """Run one bounded Helm command and enforce its expected outcome."""
    try:
        completed = subprocess.run(
            ["helm", *arguments],
            cwd=ROOT,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DeploymentValidationError("Helm could not validate deployment charts") from error
    if (completed.returncode == 0) != succeeds:
        fail("Helm accepted an invalid chart input" if not succeeds else "Helm rejected the chart")
    return completed.stdout


def render_control_plane(*overrides: str) -> list[Mapping[str, Any]]:
    """Render the control-plane chart with validation values and optional overrides."""
    arguments = [
        "template",
        "control-plane",
        str(CONTROL_PLANE_CHART),
        "--namespace",
        "perf-platform",
        "--values",
        str(CONTROL_PLANE_VALUES),
    ]
    for override in overrides:
        arguments.extend(["--set-string", override])
    documents = yaml.safe_load_all(helm(*arguments).decode("utf-8"))
    return [mapping(document, "rendered chart object") for document in documents]


def object_by_kind(objects: Sequence[Mapping[str, Any]], kind: str) -> Mapping[str, Any]:
    """Return the unique rendered object with the requested kind."""
    matches = [value for value in objects if value.get("kind") == kind]
    if len(matches) != 1:
        fail(f"control-plane chart must render exactly one {kind}")
    return matches[0]


def validate_control_plane_chart() -> None:
    """Validate control-plane workload isolation, mounts, service and RBAC."""
    helm(
        "lint",
        str(CONTROL_PLANE_CHART),
        "--strict",
        "--values",
        str(CONTROL_PLANE_VALUES),
    )
    objects = render_control_plane()
    kinds: list[str] = []
    for value in objects:
        kind = value.get("kind")
        if not isinstance(kind, str):
            fail("rendered control-plane resources require a kind")
        kinds.append(kind)
    if sorted(kinds) != ["Deployment", "Role", "RoleBinding", "Service", "ServiceAccount"]:
        fail("control-plane chart renders unexpected resources")

    deployment = object_by_kind(objects, "Deployment")
    service = object_by_kind(objects, "Service")
    service_account = object_by_kind(objects, "ServiceAccount")
    role = object_by_kind(objects, "Role")
    role_binding = object_by_kind(objects, "RoleBinding")
    if deployment["metadata"]["namespace"] != "perf-platform":
        fail("control-plane Deployment namespace is invalid")
    pod = mapping(mapping(deployment["spec"], "Deployment spec")["template"], "Pod template")
    pod_metadata = mapping(pod["metadata"], "Pod metadata")
    pod_spec = mapping(pod["spec"], "Pod spec")
    if service["spec"]["selector"] != pod_metadata["labels"]:
        fail("control-plane Service selector is invalid")
    if service["spec"]["type"] != "ClusterIP" or service["spec"]["ports"] != [
        {"name": "http", "port": 8080, "targetPort": "http"}
    ]:
        fail("control-plane Service boundary is invalid")
    if (
        pod_spec.get("serviceAccountName") != "control-plane"
        or pod_spec.get("automountServiceAccountToken") is not True
        or pod_spec.get("nodeSelector") != {"workload": "control-plane"}
    ):
        fail("control-plane Pod identity is invalid")
    if service_account.get("automountServiceAccountToken") is not True:
        fail("control-plane ServiceAccount token policy is invalid")
    if pod_spec.get("securityContext") != {
        "runAsNonRoot": True,
        "runAsUser": 65532,
        "runAsGroup": 65532,
        "fsGroup": 65532,
        "seccompProfile": {"type": "RuntimeDefault"},
    }:
        fail("control-plane Pod security context is invalid")

    containers = sequence(pod_spec.get("containers"), "control-plane containers")
    if len(containers) != 1:
        fail("control-plane chart must render exactly one container")
    container = mapping(containers[0], "control-plane container")
    image = container.get("image")
    if not isinstance(image, str) or CONTROL_PLANE_IMAGE.fullmatch(image) is None:
        fail("control-plane image must be an immutable GHCR digest")
    if container.get("imagePullPolicy") != "IfNotPresent":
        fail("control-plane image pull policy is invalid")
    if container.get("securityContext") != {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }:
        fail("control-plane container security context is invalid")
    if container.get("resources") != {
        "requests": {"cpu": "100m", "memory": "128Mi"},
        "limits": {"cpu": "1", "memory": "512Mi"},
    }:
        fail("control-plane container resources are invalid")

    environment = {
        item["name"]: item
        for item in (
            mapping(value, "control-plane environment")
            for value in sequence(container.get("env"), "control-plane environment")
        )
    }
    expected_values = {
        "PERFENG_HTTP_ADDRESS": ":8080",
        "PERFENG_KUBERNETES_NAMESPACE": "perf-generators",
        "PERFENG_AUTHENTICATION_FILE": "/etc/perfeng/auth/credentials.json",
        "PERFENG_REGISTRY_ROOT": "/etc/perfeng/registry",
        "PERFENG_REGISTRY_MANIFEST": "registry.json",
        "PERFENG_ANALYSIS_JOB_FILE": "/etc/perfeng/registry/jobs/analysis.yaml",
        "PERFENG_REPORT_JOB_FILE": "/etc/perfeng/registry/jobs/reporting.yaml",
    }
    if set(environment) != {*expected_values, "PERFENG_WORKER_ID"}:
        fail("control-plane fixed environment is incomplete")
    if any(environment[name].get("value") != value for name, value in expected_values.items()):
        fail("control-plane fixed environment is invalid")
    if environment["PERFENG_WORKER_ID"].get("valueFrom") != {
        "fieldRef": {"apiVersion": "v1", "fieldPath": "metadata.name"}
    }:
        fail("control-plane worker identity is not Pod-specific")
    if container.get("envFrom") != [
        {"configMapRef": {"name": "perfeng-control-plane-runtime"}},
        {"secretRef": {"name": "perfeng-control-plane-runtime"}},
    ]:
        fail("control-plane external runtime configuration is invalid")

    volumes = {
        value["name"]: value
        for value in (
            mapping(item, "control-plane volume")
            for item in sequence(pod_spec.get("volumes"), "control-plane volumes")
        )
    }
    if set(volumes) != {"authentication", "registry"}:
        fail("control-plane volumes are invalid")
    if volumes["authentication"].get("secret") != {
        "secretName": "perfeng-control-plane-authentication",
        "items": [{"key": "credentials.json", "path": "credentials.json"}],
    }:
        fail("control-plane authentication mount is invalid")
    registry = mapping(volumes["registry"].get("configMap"), "registry ConfigMap volume")
    if registry.get("name") != "perfeng-runtime-registry":
        fail("control-plane registry mount is invalid")
    paths = {item["path"] for item in sequence(registry.get("items"), "registry items")}
    if paths != {"registry.json", "jobs/analysis.yaml", "jobs/reporting.yaml"}:
        fail("control-plane registry paths are invalid")

    if role.get("metadata", {}).get("namespace") != "perf-generators" or role.get("rules") != [
        {"apiGroups": ["batch"], "resources": ["jobs"], "verbs": ["create", "get", "delete"]},
        {"apiGroups": [""], "resources": ["pods"], "verbs": ["list"]},
    ]:
        fail("control-plane Role is not least privilege")
    if (
        role_binding.get("metadata", {}).get("namespace") != "perf-generators"
        or role_binding.get("roleRef")
        != {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": "control-plane-job-controller",
        }
        or role_binding.get("subjects")
        != [{"kind": "ServiceAccount", "name": "control-plane", "namespace": "perf-platform"}]
    ):
        fail("control-plane RoleBinding is invalid")
