"""Validate the image-backed browser fixture without selecting or deploying an environment."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from scripts import contracts, deployment

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/native-search"
VALUES = ROOT / "testdata/native-search-values.yaml"
IDENTITY = ROOT / "releases/native-search/1.0.0/image.json"
IMAGE = re.compile(r"ghcr\.io/stanimirivanov/perfeng-native-search@sha256:[0-9a-f]{64}")
LABELS = {
    "app.kubernetes.io/name": "perfeng-native-search",
    "app.kubernetes.io/instance": "native-search",
}


def require(condition: bool, message: str) -> None:
    """Reject drift from the chart's reviewed isolation and identity boundary."""
    if not condition:
        deployment.fail(f"native-search {message}")


def validate_identity(value: Any) -> Mapping[str, Any]:
    """Check publisher provenance structure; offline validation cannot prove registry existence."""
    identity = deployment.mapping(value, "native-search image identity")
    require(
        set(identity)
        == {"schemaVersion", "name", "version", "image", "source", "targetSha256", "platform"},
        "image identity fields are invalid",
    )
    require(
        type(identity["schemaVersion"]) is int
        and identity["schemaVersion"] == 1
        and identity["name"] == "perfeng-native-search"
        and identity["version"] == "1.0.0"
        and identity["platform"] == "linux/amd64",
        "image identity version or platform is invalid",
    )
    image = identity["image"]
    require(
        isinstance(image, str) and IMAGE.fullmatch(image) is not None, "image must be digest-only"
    )
    if isinstance(image, str):
        require(len(set(image.split(":")[-1])) > 1, "image digest is a synthetic placeholder")
    source = deployment.mapping(identity["source"], "native-search source")
    require(
        set(source) == {"repository", "gitSha"}
        and source["repository"] == "https://github.com/stanimirivanov/perfeng-environment",
        "source repository is invalid",
    )
    for name, value, length in (
        ("source revision", source["gitSha"], 40),
        ("target checksum", identity["targetSha256"], 64),
    ):
        require(
            isinstance(value, str)
            and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None
            and len(set(value)) > 1,
            f"{name} is invalid or synthetic",
        )
    return identity


def render(*overrides: str, succeeds: bool = True) -> list[Mapping[str, Any]]:
    """Render synthetic values with bounded Helm execution, never contacting Kubernetes."""
    arguments = [
        "template",
        "native-search",
        str(CHART),
        "--namespace",
        "perf-targets",
        "--values",
        str(VALUES),
    ]
    for override in overrides:
        arguments.extend(["--set-string", override])
    content = deployment.helm(*arguments, succeeds=succeeds)
    if not succeeds:
        return []
    return [
        deployment.mapping(value, "native-search rendered object")
        for value in yaml.safe_load_all(content.decode("utf-8"))
    ]


def validate_objects(objects: Sequence[Mapping[str, Any]]) -> None:
    """Enforce token-free, bounded image execution and an internal-only Service on rendered objects."""
    require(
        len(objects) == 3
        and {value.get("kind") for value in objects} == {"Deployment", "Service", "ServiceAccount"},
        "chart must render only one Deployment, Service and ServiceAccount",
    )
    by_kind = {value["kind"]: value for value in objects}
    for kind, value in by_kind.items():
        require(
            value.get("apiVersion") == ("apps/v1" if kind == "Deployment" else "v1")
            and value.get("metadata")
            == {"name": "native-search", "namespace": "perf-targets", "labels": LABELS},
            f"{kind} ownership is invalid",
        )
    require(
        by_kind["ServiceAccount"].get("automountServiceAccountToken") is False
        and set(by_kind["ServiceAccount"])
        == {"apiVersion", "kind", "metadata", "automountServiceAccountToken"},
        "ServiceAccount must be token-free",
    )
    require(
        by_kind["Service"].get("spec")
        == {
            "type": "ClusterIP",
            "selector": LABELS,
            "ports": [{"name": "http", "port": 8080, "targetPort": "http"}],
        },
        "Service must expose only internal HTTP port 8080 with the candidate selector",
    )
    _validate_deployment(by_kind["Deployment"])


def _validate_deployment(value: Mapping[str, Any]) -> None:
    """Keep rollout identity stable and avoid concurrent candidate versions."""
    spec = deployment.mapping(value.get("spec"), "native-search Deployment spec")
    require(
        set(spec)
        == {
            "replicas",
            "strategy",
            "progressDeadlineSeconds",
            "minReadySeconds",
            "revisionHistoryLimit",
            "selector",
            "template",
        }
        and spec["replicas"] == 1
        and spec["strategy"] == {"type": "Recreate"}
        and spec["progressDeadlineSeconds"] == 120
        and spec["minReadySeconds"] == 2
        and spec["revisionHistoryLimit"] == 2
        and spec["selector"] == {"matchLabels": LABELS},
        "Deployment lifecycle must bound rollout and avoid mixed candidate replicas",
    )
    template = deployment.mapping(spec["template"], "native-search Pod template")
    require(
        set(template) == {"metadata", "spec"} and template.get("metadata") == {"labels": LABELS},
        "Pod selector or template fields are invalid",
    )
    _validate_pod(deployment.mapping(template.get("spec"), "native-search Pod spec"))


def _validate_pod(pod: Mapping[str, Any]) -> None:
    """Restrict placement, token/pull identities and writable temporary storage."""
    require(
        set(pod)
        == {
            "serviceAccountName",
            "automountServiceAccountToken",
            "imagePullSecrets",
            "nodeSelector",
            "terminationGracePeriodSeconds",
            "securityContext",
            "containers",
            "volumes",
        }
        and pod["serviceAccountName"] == "native-search"
        and pod["automountServiceAccountToken"] is False
        and pod["imagePullSecrets"] == [{"name": "synthetic-native-search-registry"}]
        and pod["nodeSelector"] == {"kubernetes.io/os": "linux", "kubernetes.io/arch": "amd64"}
        and pod["terminationGracePeriodSeconds"] == 15,
        "Pod identity, architecture or execution surface is invalid",
    )
    require(
        pod["securityContext"]
        == {
            "runAsNonRoot": True,
            "runAsUser": 101,
            "runAsGroup": 101,
            "fsGroup": 101,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "Pod must run as unprivileged UID/GID 101 with runtime-default seccomp",
    )
    require(
        pod["volumes"]
        == [
            {
                "name": "temporary",
                "emptyDir": {"medium": "Memory", "sizeLimit": "16Mi"},
            }
        ],
        "volumes must contain only bounded memory-backed temporary storage",
    )
    containers = deployment.sequence(pod["containers"], "native-search containers")
    require(len(containers) == 1, "Pod must run only the candidate container")
    _validate_container(deployment.mapping(containers[0], "native-search container"))


def _validate_container(container: Mapping[str, Any]) -> None:
    """Preserve image-owned content/configuration, resource budgets and health semantics."""
    require(
        set(container)
        == {
            "name",
            "image",
            "imagePullPolicy",
            "ports",
            "startupProbe",
            "readinessProbe",
            "livenessProbe",
            "securityContext",
            "resources",
            "volumeMounts",
        }
        and container["name"] == "search"
        and isinstance(container["image"], str)
        and IMAGE.fullmatch(container["image"]) is not None
        and container["imagePullPolicy"] == "IfNotPresent"
        and container["ports"] == [{"name": "http", "containerPort": 8080}],
        "container must use the candidate image without command, environment or port overrides",
    )
    require(
        container["securityContext"]
        == {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
        },
        "container isolation is invalid",
    )
    require(
        container["resources"]
        == {
            "requests": {"cpu": "50m", "memory": "32Mi", "ephemeral-storage": "16Mi"},
            "limits": {"cpu": "500m", "memory": "64Mi", "ephemeral-storage": "32Mi"},
        },
        "resource requests and limits must remain bounded",
    )
    require(
        container["volumeMounts"] == [{"name": "temporary", "mountPath": "/tmp"}],
        "container must not mount credentials or replace image content",
    )
    for name, period, failures in (
        ("startupProbe", 2, 30),
        ("readinessProbe", 5, 2),
        ("livenessProbe", 10, 3),
    ):
        require(
            container[name]
            == {
                "httpGet": {"path": "/healthz", "port": "http"},
                "periodSeconds": period,
                "timeoutSeconds": 1,
                "failureThreshold": failures,
            },
            f"{name} must check the bounded candidate health endpoint",
        )


def validate() -> None:
    """Validate release provenance and strictly lint/render the unselected candidate chart."""
    try:
        validate_identity(contracts.parse_json(IDENTITY.read_bytes()))
    except (OSError, ValueError) as error:
        raise deployment.DeploymentValidationError(
            f"native-search provenance is invalid: {error}"
        ) from error
    deployment.helm("lint", str(CHART), "--strict", "--values", str(VALUES))
    validate_objects(render())
