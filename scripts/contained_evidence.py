"""Semantic checks over frozen measurement observations before they become published evidence."""

import json
from datetime import datetime
from itertools import pairwise
from typing import Any

from scripts import contained_contracts as schema
from scripts import contained_inputs as inputs


def timestamp(value: str) -> datetime:
    """Require offset-qualified timestamps even when called outside schema validation."""
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Observation timestamp has no timezone")
    return result


def validate(
    value: dict[str, Any], request: inputs.Request, start: datetime, end: datetime
) -> None:
    """Check actual node/time coverage, conservative eligibility and the selected Run/environment."""
    schema.validate("kubernetes-benchmark-evidence", value)
    if (
        value["scope"]
        != {
            "kind": "measurement",
            "runId": request.run_id,
            "testId": request.value["testId"],
            "workload": request.value["workload"],
        }
        or value["environment"] != request.value["environment"]
        or value["target"]
        != {"clusterId": "perfeng-local", "kubeSystemUid": request.value["kubeSystemUid"]}
        or value["profile"]
        != {
            **request.profile["metadata"],
            "sha256": inputs.PROFILE_SHA256,
            "purpose": "integration",
        }
    ):
        raise ValueError("Measurement evidence identity differs")
    capture_start, capture_end = (
        timestamp(value["captureWindow"][key]) for key in ("start", "end")
    )
    if capture_start > start or capture_end < end or start >= end:
        raise ValueError("Measurement evidence does not cover execution")
    nodes = {node["uid"]: node for node in value["nodes"]}
    if len(nodes) != 3 or len({node["name"] for node in nodes.values()}) != 3:
        raise ValueError("Measurement node inventory is incomplete or duplicated")
    basis = {
        "profileSha256": inputs.PROFILE_SHA256,
        "nodeImage": inputs.NODE_IMAGE,
        "kubeSystemUid": request.value["kubeSystemUid"],
        "observedNodes": sorted(nodes.values(), key=lambda node: node["name"]),
    }
    if (
        inputs.digest(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode())
        != request.value["environment"]["fingerprint"]
    ):
        raise ValueError("Measurement stable environment differs")
    checks = {check["id"]: check["status"] for check in value["checks"]}
    observed: dict[str, list[datetime]] = {uid: [] for uid in nodes}
    readiness, pressure = [], []
    missing_usage, high_usage = False, False
    for sample in value["samples"]:
        uid = sample["nodeUid"]
        if uid not in nodes:
            raise ValueError("Sample refers to an undeclared node")
        at = timestamp(sample["observedAt"])
        if not capture_start <= at <= capture_end or (observed[uid] and at <= observed[uid][-1]):
            raise ValueError("Samples are out of order or outside capture")
        observed[uid].append(at)
        conditions = sample["conditions"]
        readiness.append(conditions["ready"])
        pressure.extend(
            conditions[key] for key in ("memoryPressure", "diskPressure", "pidPressure")
        )
        usage = sample["usage"]
        if usage["source"] == "unavailable":
            missing_usage = True
        else:
            first, last = timestamp(usage["windowStart"]), timestamp(usage["windowEnd"])
            if (
                not capture_start <= first < last <= at
                or (at - last).total_seconds() > request.profile["spec"]["maximumMetricAgeSeconds"]
                or (last - first).total_seconds()
                > request.profile["spec"]["maximumMetricWindowSeconds"]
            ):
                raise ValueError("Invalid provider measurement window")
            allocation = nodes[uid]["allocatable"]
            high_usage |= (
                usage["cpuMilliCores"]
                > allocation["cpuMilliCores"] * request.profile["spec"]["maximumCpuUsageRatio"]
                or usage["memoryBytes"]
                > allocation["memoryBytes"] * request.profile["spec"]["maximumMemoryUsageRatio"]
            )
    for times in observed.values():
        if len(times) < 2:
            raise ValueError("Measurement must sample every node before and after execution")
        gaps = [(right - left).total_seconds() for left, right in pairwise(times)]
        gaps.extend(((times[0] - start).total_seconds(), (end - times[-1]).total_seconds()))
        if max(gaps) > 30 and checks["interference"] == "PASS":
            raise ValueError("Sampling gap cannot establish interference PASS")
    ready = "FAIL" if "FALSE" in readiness else "UNKNOWN" if "UNKNOWN" in readiness else "PASS"
    pressured = "FAIL" if "TRUE" in pressure else "UNKNOWN" if "UNKNOWN" in pressure else "PASS"
    if checks["node-readiness"] != ready or checks["resource-pressure"] != pressured:
        raise ValueError("Node condition claims contradict observations")
    if (high_usage and checks["interference"] != "FAIL") or (
        missing_usage and checks["interference"] == "PASS"
    ):
        raise ValueError("Missing or over-budget usage cannot establish interference PASS")
