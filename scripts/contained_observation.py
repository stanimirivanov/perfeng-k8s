"""Collect bounded Run-scoped observations without installing services or obtaining write authority."""

from __future__ import annotations

import json
import re
import ssl
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from scripts import contained_contracts as schema
from scripts.contained_inputs import NODE_IMAGE, PROFILE_SHA256, digest, object_json
from scripts.contained_inputs import Request as RunRequest

TOKEN_ROOT = Path("/var/run/secrets/kubernetes.io/serviceaccount")
REASONS = {
    "cluster-identity": "Observed cluster and owned namespace UIDs match the resolved request.",
    "node-readiness": "Reviewed nodes remained Ready.",
    "placement": "Reviewed node placement and schedulability match.",
    "capacity": "Reviewed versions, architecture and capacity match.",
    "resource-pressure": "No observed node pressure.",
    "interference": "Fresh provider usage and active workloads match the integration profile.",
}


def now() -> datetime:
    """Read a timezone-aware observation clock, separately from deadline accounting."""
    return datetime.now(UTC)


def stamp(value: datetime) -> str:
    """Preserve the contract's six-decimal timestamp precision."""
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def quantity(value: str, *, cpu: bool = False, usage: bool = False) -> int:
    """Use exact decimal quantities; conservatively floor capacity and ceil usage."""
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("Invalid quantity")
    match = re.fullmatch(
        r"([+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)(n|u|m|Ki|Mi|Gi|Ti|Pi|Ei|k|M|G|T|P|E)?",
        value,
    )
    if match is None:
        raise ValueError("Invalid quantity")
    units = {
        "": Decimal(1),
        "n": Decimal("1e-9"),
        "u": Decimal("1e-6"),
        "m": Decimal("1e-3"),
        "k": Decimal(1000),
    }
    units.update(
        {name: Decimal(1000) ** index for index, name in enumerate(("M", "G", "T", "P", "E"), 2)}
    )
    units.update(
        {
            name: Decimal(1024) ** index
            for index, name in enumerate(("Ki", "Mi", "Gi", "Ti", "Pi", "Ei"), 1)
        }
    )
    result = Decimal(match[1]) * units[match[2] or ""] * (1000 if cpu else 1)
    if not result.is_finite() or not 0 <= result <= 2**53 - 1:
        raise ValueError("Quantity outside supported range")
    return int(result.to_integral_value(rounding=ROUND_CEILING if usage else ROUND_FLOOR))


class NoRedirect(HTTPRedirectHandler):
    """Never forward a Kubernetes bearer token to a redirected endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Kubernetes API redirects are forbidden")


class ObservationAPI(Protocol):
    """Read-only API seam; implementations must bound reads and never expose credential values."""

    def get(self, path: str) -> dict[str, Any]:
        """Return one bounded JSON resource/list or fail without fabricating an empty observation."""
        ...


class Kubernetes:
    """Read-only TLS client using the runner-only projected service-account credentials."""

    def __init__(self) -> None:
        context = ssl.create_default_context(cafile=str(TOKEN_ROOT / "ca.crt"))
        self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))

    def get(self, path: str) -> dict[str, Any]:
        """Bound each authenticated response; refresh the projected token before every request."""
        token = (TOKEN_ROOT / "token").read_text().strip()
        request = Request(
            "https://kubernetes.default.svc" + path, headers={"Authorization": "Bearer " + token}
        )
        with self.opener.open(request, timeout=3) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Kubernetes observation exceeds bound")
        return object_json(data)


def items(value: dict[str, Any], maximum: int) -> list[dict[str, Any]]:
    """Reject oversized or malformed API lists rather than silently truncating coverage."""
    result = value["items"]
    if (
        not isinstance(result, list)
        or len(result) > maximum
        or any(not isinstance(item, dict) for item in result)
    ):
        raise ValueError("Invalid bounded API inventory")
    return result


def guard(api: ObservationAPI, request: RunRequest, *, empty: bool = False) -> None:
    """Verify namespace incarnation, ownership and quota; never create, adopt or delete a target."""
    value = request.value
    namespace = api.get("/api/v1/namespaces/" + request.namespace)
    metadata = namespace["metadata"]
    labels = metadata.get("labels", {})
    if (
        metadata["uid"] != value["namespaceUid"]
        or metadata.get("deletionTimestamp")
        or labels.get("perfeng.io/run-id") != request.run_id
        or labels.get("perfeng.io/owner") != "perfeng-control-plane"
        or labels.get("pod-security.kubernetes.io/enforce") != "restricted"
        or labels.get("pod-security.kubernetes.io/enforce-version") != "v1.35"
        or api.get("/api/v1/namespaces/kube-system")["metadata"]["uid"] != value["kubeSystemUid"]
    ):
        raise ValueError("Target incarnation or ownership differs")
    quota = api.get(f"/api/v1/namespaces/{request.namespace}/resourcequotas/benchmark-budget")
    hard = quota["spec"]["hard"]
    expected = {
        "pods": "10",
        "limits.cpu": "100m",
        "limits.memory": "160Mi",
        "limits.ephemeral-storage": "10Mi",
    }
    if any(
        quantity(hard[key], cpu=key.endswith("cpu")) != quantity(wanted, cpu=key.endswith("cpu"))
        for key, wanted in expected.items()
    ):
        raise ValueError("Owned namespace quota differs")
    if empty and items(api.get(f"/api/v1/namespaces/{request.namespace}/pods"), 10):
        raise ValueError("Benchmark namespace is not empty; no adoption or automatic cleanup")


def inventory(
    api: ObservationAPI, request: RunRequest
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Bind observed stable nodes to the selected PR-2 environment fingerprint before execution."""
    profile = request.profile["spec"]
    checks = dict.fromkeys(REASONS, "PASS")
    result: list[dict[str, Any]] = []
    warm = False
    for item in items(api.get("/api/v1/nodes"), 256):
        metadata, status = item["metadata"], item["status"]
        info = status["nodeInfo"]
        node = {
            "name": metadata["name"],
            "uid": metadata["uid"],
            "kubernetesVersion": info["kubeletVersion"],
            "containerRuntimeVersion": info["containerRuntimeVersion"],
            "architecture": info["architecture"],
            "allocatable": {
                "cpuMilliCores": quantity(status["allocatable"]["cpu"], cpu=True),
                "memoryBytes": quantity(status["allocatable"]["memory"]),
            },
        }
        result.append(node)
        if metadata.get("labels", {}).get("workload") != profile["nodes"].get(
            node["name"]
        ) or item.get("spec", {}).get("unschedulable", False):
            checks["placement"] = "FAIL"
        if (
            info["kubeletVersion"] != profile["kubernetesVersion"]
            or info["architecture"] != "amd64"
            or info.get("operatingSystem") != "linux"
            or node["allocatable"]["cpuMilliCores"] < profile["minimumAllocatableCpuMilliCores"]
            or node["allocatable"]["memoryBytes"] < profile["minimumAllocatableMemoryBytes"]
        ):
            checks["capacity"] = "FAIL"
        if profile["nodes"].get(node["name"]) == "sut":
            warm = any(
                request.value["candidateImage"] in image.get("names", [])
                for image in status.get("images", [])
            )
    basis = {
        "profileSha256": PROFILE_SHA256,
        "nodeImage": NODE_IMAGE,
        "kubeSystemUid": request.value["kubeSystemUid"],
        "observedNodes": sorted(result, key=lambda item: item["name"]),
    }
    fingerprint = digest(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode())
    if fingerprint != request.value["environment"]["fingerprint"] or len(result) != 3:
        raise ValueError("Observed stable environment differs; requalification is required")
    if not warm:
        checks["capacity"] = "FAIL"
    return sorted(result, key=lambda node: node["name"]), checks


def sample(
    api: ObservationAPI, request: RunRequest, executor_uid: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    """Keep unknown usage explicit and classify namespace interference without retaining Pod secrets."""
    guard(api, request)
    nodes, checks = inventory(api, request)
    raw_nodes = {node["metadata"]["uid"]: node for node in items(api.get("/api/v1/nodes"), 256)}
    if set(raw_nodes) != {node["uid"] for node in nodes}:
        raise ValueError("Node identities changed while sampling")
    usages = {}
    try:
        metric_items = items(api.get("/apis/metrics.k8s.io/v1beta1/nodes"), 256)
        for item in metric_items:
            name = item["metadata"]["name"]
            end = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
            window = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)s", item["window"])
            if (
                name in usages
                or window is None
                or not 0 < float(window[1]) <= request.profile["spec"]["maximumMetricWindowSeconds"]
                or not 0
                <= (now() - end).total_seconds()
                <= request.profile["spec"]["maximumMetricAgeSeconds"]
            ):
                raise ValueError("Stale, duplicate or invalid provider usage")
            usages[name] = {
                "source": "metrics-api",
                "windowStart": stamp(end - timedelta(seconds=float(window[1]))),
                "windowEnd": stamp(end),
                "cpuMilliCores": quantity(item["usage"]["cpu"], cpu=True, usage=True),
                "memoryBytes": quantity(item["usage"]["memory"], usage=True),
            }
    except (OSError, ValueError, KeyError, TypeError, HTTPError):
        usages = {}
    observed_at = stamp(now())
    samples = []
    for node in nodes:
        raw_conditions = items(
            {"items": raw_nodes[node["uid"]]["status"].get("conditions", [])}, 64
        )
        conditions = {}
        for key, name in (
            ("ready", "Ready"),
            ("memoryPressure", "MemoryPressure"),
            ("diskPressure", "DiskPressure"),
            ("pidPressure", "PIDPressure"),
        ):
            values = [item.get("status") for item in raw_conditions if item.get("type") == name]
            conditions[key] = (
                values[0].upper()
                if len(values) == 1 and values[0] in {"True", "False", "Unknown"}
                else "UNKNOWN"
            )
        ready = conditions["ready"]
        if ready != "TRUE":
            checks["node-readiness"] = (
                "FAIL"
                if ready == "FALSE"
                else "UNKNOWN"
                if checks["node-readiness"] != "FAIL"
                else "FAIL"
            )
        pressure = [conditions[key] for key in ("memoryPressure", "diskPressure", "pidPressure")]
        if "TRUE" in pressure:
            checks["resource-pressure"] = "FAIL"
        elif "UNKNOWN" in pressure and checks["resource-pressure"] != "FAIL":
            checks["resource-pressure"] = "UNKNOWN"
        usage = usages.get(
            node["name"],
            {
                "source": "unavailable",
                "reason": "Metrics API observations unavailable, invalid or stale.",
            },
        )
        if usage["source"] == "unavailable" and checks["interference"] != "FAIL":
            checks["interference"] = "UNKNOWN"
        elif usage["source"] == "metrics-api" and (
            usage["cpuMilliCores"]
            > node["allocatable"]["cpuMilliCores"] * request.profile["spec"]["maximumCpuUsageRatio"]
            or usage["memoryBytes"]
            > node["allocatable"]["memoryBytes"]
            * request.profile["spec"]["maximumMemoryUsageRatio"]
        ):
            checks["interference"] = "FAIL"
        samples.append(
            {
                "nodeUid": node["uid"],
                "observedAt": observed_at,
                "conditions": conditions,
                "usage": usage,
            }
        )
    try:
        for pod in items(api.get("/api/v1/pods"), 4096):
            meta = pod["metadata"]
            if meta["uid"] == executor_uid or pod.get("status", {}).get("phase") in {
                "Succeeded",
                "Failed",
            }:
                continue
            namespace = meta["namespace"]
            owned = (
                namespace == request.namespace
                and meta.get("labels", {}).get("perfeng.io/run-id") == request.run_id
                and not pod["spec"].get("initContainers")
                and not pod["spec"].get("ephemeralContainers")
                and not pod["spec"].get("volumes")
                and len(pod["spec"]["containers"]) == 1
                and all(
                    container["image"] == request.value["candidateImage"]
                    for container in pod["spec"]["containers"]
                )
            )
            if namespace not in request.profile["spec"]["allowedActiveNamespaces"] and not owned:
                checks["interference"] = "FAIL"
    except (OSError, ValueError, KeyError, TypeError):
        if checks["interference"] != "FAIL":
            checks["interference"] = "UNKNOWN"
    return nodes, samples, checks


def evidence(
    request: RunRequest,
    nodes: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    checks: dict[str, str],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Emit measurement scope and conservative full-process coverage, never relabel preflight."""
    for sample in samples:
        if sample["usage"]["source"] == "metrics-api":
            start = min(
                start, datetime.fromisoformat(sample["usage"]["windowStart"].replace("Z", "+00:00"))
            )
    result = {
        "schemaVersion": 1,
        "kind": "KubernetesBenchmarkEvidence",
        "scope": {
            "kind": "measurement",
            "runId": request.run_id,
            "testId": request.value["testId"],
            "workload": request.value["workload"],
        },
        "profile": {
            **request.profile["metadata"],
            "sha256": PROFILE_SHA256,
            "purpose": "integration",
        },
        "environment": request.value["environment"],
        "target": {"clusterId": "perfeng-local", "kubeSystemUid": request.value["kubeSystemUid"]},
        "captureWindow": {"start": stamp(start), "end": stamp(end)},
        "status": "REJECTED"
        if "FAIL" in checks.values()
        else "UNKNOWN"
        if "UNKNOWN" in checks.values()
        else "ACCEPTED",
        "checks": [
            {
                "id": key,
                "status": status,
                "reason": REASONS[key]
                if status == "PASS"
                else f"Observed {key} {status}; inspect capture prerequisites and retained Run evidence.",
            }
            for key, status in checks.items()
        ],
        "nodes": nodes,
        "samples": samples,
    }
    schema.validate("kubernetes-benchmark-evidence", result)
    return result
