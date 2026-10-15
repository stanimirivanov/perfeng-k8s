"""Publish exact raw objects conditionally and read them back before the completion manifest."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from scripts import contained_contracts as schema
from scripts import contained_evidence, evidence
from scripts.contained_inputs import (
    FILES,
    Request,
    digest,
    encode,
    exact,
    object_json,
    read,
    resolved_document,
)


def client():
    """Use only explicitly mounted publisher credentials; never discover instance/container credentials."""
    endpoint = os.environ["PERFENG_S3_ENDPOINT"]
    parsed = urlsplit(endpoint)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Invalid reviewed S3 endpoint")
    local = endpoint == "http://seaweedfs.perf-platform.svc.cluster.local:8333"
    if parsed.scheme != "https" and not local:
        raise ValueError("S3 endpoint requires TLS except the reviewed local service")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="us-east-1",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        config=Config(
            connect_timeout=3,
            read_timeout=5,
            retries={"total_max_attempts": 2},
            s3={"addressing_style": "path"},
            proxies={},
        ),
    )


def reference(
    request: Request, name: str, content: bytes, media_type: str, artifact_format: str
) -> dict[str, Any]:
    """Use stable UUIDs and keys so publication retries cannot create alternate evidence identities."""
    return {
        "id": str(uuid5(NAMESPACE_URL, f"perfeng:{request.run_id}:{name}")),
        "runId": request.run_id,
        "kind": "raw",
        "uri": f"s3://{request.value['bucket']}/runs/{request.run_id}/"
        + (name if name == "raw-result.json" else f"raw/{name}"),
        "sha256": digest(content),
        "sizeBytes": len(content),
        "mediaType": media_type,
        "format": artifact_format,
    }


def put_verified(
    s3: Any, request: Request, name: str, content: bytes, artifact: dict[str, Any]
) -> None:
    """Never overwrite: conditional create, then verify content, size, media type and discovery metadata."""
    key = f"runs/{request.run_id}/" + (name if name == "raw-result.json" else f"raw/{name}")
    metadata = {
        "artifact-id": artifact["id"],
        "sha256": artifact["sha256"],
        "format": artifact["format"],
    }
    try:
        s3.put_object(
            Bucket=request.value["bucket"],
            Key=key,
            Body=content,
            ContentType=artifact["mediaType"],
            Metadata=metadata,
            IfNoneMatch="*",
        )
    except (BotoCoreError, ClientError):
        # A timeout or conflict may follow a successful write. Only exact read-back can resolve it.
        pass
    stored = s3.get_object(Bucket=request.value["bucket"], Key=key)
    body = stored["Body"]
    try:
        actual = body.read(len(content) + 1)
    finally:
        body.close()
    if (
        stored.get("ContentLength") != len(content)
        or stored.get("ContentType") != artifact["mediaType"]
        or stored.get("Metadata") != metadata
        or actual != content
    ):
        raise ValueError("Stored object bytes or metadata differ; evidence was not replaced")


def prepare(request: Request, output: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Verify a frozen complete capture before any storage call; never trust supplied object locations."""
    receipt = exact(
        object_json(read(output / "complete.json")),
        {
            "schemaVersion",
            "kind",
            "runId",
            "requestSha256",
            "exitCode",
            "startedAt",
            "completedAt",
            "artifacts",
        },
    )
    if (
        receipt["schemaVersion"] != 1
        or receipt["kind"] != "ContainedKubernetesExecution"
        or receipt["runId"] != request.run_id
        or receipt["requestSha256"] != request.sha256
        or type(receipt["exitCode"]) is not int
        or receipt["exitCode"] != 0
        or set(receipt["artifacts"]) != set(FILES)
    ):
        raise ValueError("Capture is incomplete or belongs to another request")
    start, end = (
        datetime.fromisoformat(receipt[key].replace("Z", "+00:00"))
        for key in ("startedAt", "completedAt")
    )
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Capture window is invalid")
    contents = {}
    artifacts = []
    for name, (media_type, artifact_format) in FILES.items():
        content = read(output / name)
        if not content or receipt["artifacts"][name] != {
            "sha256": digest(content),
            "sizeBytes": len(content),
        }:
            raise ValueError("Frozen capture bytes differ")
        if name in evidence.ARTIFACT_TYPES:
            evidence.validate_payload(name, content, request.run_id)
        if name == "resolved-inputs.json" and content != encode(resolved_document(request, output)):
            raise ValueError(
                "Resolved input closure differs from packaged source and selected substitutions"
            )
        if name == "qualification.json":
            qualification = object_json(content)
            schema.validate("kubernetes-benchmark-evidence", qualification)
            expected_scope = {
                "kind": "measurement",
                "runId": request.run_id,
                "testId": request.value["testId"],
                "workload": request.value["workload"],
            }
            if (
                qualification["scope"] != expected_scope
                or qualification["environment"] != request.value["environment"]
                or qualification["target"]
                != {"clusterId": "perfeng-local", "kubeSystemUid": request.value["kubeSystemUid"]}
            ):
                raise ValueError("Measurement evidence identity differs")
            if (
                datetime.fromisoformat(
                    qualification["captureWindow"]["start"].replace("Z", "+00:00")
                )
                > start
                or datetime.fromisoformat(
                    qualification["captureWindow"]["end"].replace("Z", "+00:00")
                )
                < end
            ):
                raise ValueError("Measurement evidence does not cover execution")
        contents[name] = content
        artifacts.append(reference(request, name, content, media_type, artifact_format))
    manifest = {
        "schemaVersion": 2,
        "kind": "RawResult",
        "contractsVersion": schema.VERSION,
        "runId": request.run_id,
        "testId": request.value["testId"],
        "workload": request.value["workload"],
        "producer": {
            "name": "kube-burner",
            "version": "2.8.5",
            "artifact": {"kind": "oci-image", "image": request.value["runnerImage"]},
        },
        "measurementWindow": {"start": receipt["startedAt"], "end": receipt["completedAt"]},
        "createdAt": receipt["completedAt"],
        "artifacts": artifacts,
    }
    contained_evidence.validate(object_json(contents["qualification.json"]), request, start, end)
    schema.validate("raw-result", manifest)
    return manifest, contents


def publish(s3: Any, request: Request, output: Path) -> dict[str, Any]:
    """Publish prerequisites first; raw-result/v2 becomes discoverable only after verification."""
    manifest, contents = prepare(request, output)
    for name, artifact in zip(FILES, manifest["artifacts"], strict=True):
        print(f"Conditionally publishing and verifying {name}...", flush=True)
        put_verified(s3, request, name, contents[name], artifact)
    content = encode(manifest)
    marker = reference(request, "raw-result.json", content, "application/json", "raw-result/v2")
    print("Publishing verified raw-result/v2 completion marker last...", flush=True)
    put_verified(s3, request, "raw-result.json", content, marker)
    return marker
