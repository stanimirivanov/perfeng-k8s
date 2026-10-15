"""Validate the promoted contained integration cohort without changing historical bundles."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from scripts import contained_contracts as contracts
from scripts import contained_definition
from scripts import contained_inputs as inputs

ROOT = contracts.ROOT
BUNDLE = ROOT / "bundles/local-kind-integration/1.0.0"
LEGACY = ROOT / "bundles/local-kind-windows/1.1.3"
VALIDATOR_REVISION = "703d9d11fda3f94e52b4cf4fad749d73cf52247f"
RUNNER_IMAGE = (
    "ghcr.io/stanimirivanov/perfeng-kube-burner@sha256:"
    "b4f6a90225e14f67c5c2fa0bc2657eb871e92f7543b6b1027eb618cff633d612"
)
RUNNER_REVISION = "0e026fa33e4d7e1573e081786266efd17e9a7460"
ANALYSIS_IMAGE = (
    "ghcr.io/stanimirivanov/perfeng-analysis@sha256:"
    "450de3e28fe4b61627d49e053549c94e7f0a6bb4dc3df8d53bbabe5474f02ed9"
)
ANALYSIS_REVISION = "4eba58456f9b8dd3e75e2e986da60db51b13fb99"
ENVIRONMENT_SHA256 = "59bfaacb94f7c2f889d33225934ebcc7b4475938f46b938907016119016dac0c"
FINGERPRINT = "7c9084e8759ec35def31f69f99d37c757abb43ec6a3d14f93f676287bf85342b"
CLUSTER_UID = "9703e7d3-95b6-4981-b817-014e96402767"
PULL_SECRET = "perfeng-execution-registry"
BASELINE_ID = "approved-local-pod-startup-contained"
FILES = {
    "registry.json",
    "identities/analysis-image.json",
    "identities/kube-burner-image.json",
    "identities/catalogue.json",
    "identities/environment.json",
    "identities/checkout-environment.json",
    "identities/k6-image.json",
    "identities/workloads/checkout-smoke.json",
    "identities/workloads/pod-startup-contained.json",
    "jobs/benchmark.json",
    "jobs/checkout.json",
    "jobs/analysis.yaml",
    "jobs/reporting.yaml",
    "policies/pod-startup.json",
    "policies/checkout-smoke.json",
}


def require(condition: bool, message: str) -> None:
    """Reject promotion drift with a non-sensitive packaging diagnostic."""
    contained_definition.require(condition, "runtime bundle: " + message)


def read(root: Path, name: str) -> bytes:
    """Read known bundle members without following redirected files or directories."""
    path = root / name
    for part in (path, *path.parents):
        if part == root.parent:
            break
        require(not part.is_symlink() and not part.is_junction(), "redirected bundle member")
    return inputs.read(path)


def document(root: Path, name: str) -> dict[str, Any]:
    """Load finite, unique-key JSON from a known member of the bundle."""
    return inputs.object_json(read(root, name))


def image_record(name: str, image: str, revision: str) -> dict[str, Any]:
    """Bind publisher-supplied image, source and platform without inventing a release identity."""
    return {
        "schemaVersion": 1,
        "name": name,
        "version": "1.0.0" if name == "perfeng-kube-burner" else "0.8.1",
        "image": image,
        "source": {
            "repository": "https://github.com/stanimirivanov/"
            + ("perfeng-k8s" if name == "perfeng-kube-burner" else name),
            "gitSha": revision,
        },
        "platform": "linux/amd64",
    }


def benchmark_template() -> dict[str, Any]:
    """Adapt the contained chart to the control plane's reusable, unbound Job recipe.

    The zero request hash is a binding slot, not an artifact claim. The pinned Go
    loader independently checks this entire template against BenchmarkJobTemplate.
    """
    objects = contained_definition.render(
        "image=" + RUNNER_IMAGE,
        "imagePullSecret=" + PULL_SECRET,
        "storageSecret=perfeng-s3-uploader-auth",
        "s3Endpoint=http://seaweedfs.perf-platform.svc.cluster.local:8333",
    )
    spec = copy.deepcopy(next(value for value in objects if value["kind"] == "Job")["spec"])
    spec["template"].pop("metadata")
    pod = spec["template"]["spec"]
    pod["serviceAccountName"] = "benchmark-executor"
    pod["volumes"][0]["configMap"] = {"name": "benchmark-inputs", "defaultMode": 0o644}
    pod["volumes"][1]["projected"]["defaultMode"] = 0o644
    pod["initContainers"][0]["env"][0]["valueFrom"]["fieldRef"]["apiVersion"] = "v1"
    for container in (pod["initContainers"][0], pod["containers"][0]):
        container["args"][4] = "0" * 64
    return {"spec": spec}


def transfer_template(name: str) -> dict[str, Any]:
    """Retain reviewed transfer mechanics while selecting the OCI-aware reader and pull Secret."""
    job = yaml.safe_load(inputs.read(LEGACY / "jobs" / name))
    pod = job["spec"]["template"]["spec"]
    pod["imagePullSecrets"] = [{"name": PULL_SECRET}]
    for container in pod["containers"]:
        if container["name"] in {"normalizer", "reporter"}:
            container["image"] = ANALYSIS_IMAGE
    return job


def checkout_template() -> dict[str, Any]:
    """Preserve the existing k6 command, image and publication semantics."""
    job = inputs.object_json(inputs.read(LEGACY / "jobs/execution.json"))
    job["spec"]["template"]["spec"]["imagePullSecrets"] = [{"name": PULL_SECRET}]
    return job


def policy() -> dict[str, Any]:
    """Give the contained cohort a new policy version and a distinct approved baseline key."""
    value = inputs.object_json(inputs.read(LEGACY / "policies/pod-startup.json"))
    value["metadata"]["version"] = "1.1.0"
    value["spec"]["rules"][0]["regression"]["reference"]["baselineId"] = BASELINE_ID
    return value


def registry(root: Path) -> dict[str, Any]:
    """Construct the closed selection; k6 retains its historical environment and workload cohort."""
    previous = inputs.object_json(inputs.read(LEGACY / "registry.json"))
    benchmark, checkout = copy.deepcopy(previous["entries"])
    catalogue = {
        "id": "platform-tests",
        "version": "1.2.0",
        "sha256": inputs.digest(read(root, "identities/catalogue.json")),
    }
    for entry in (benchmark, checkout):
        entry["catalogue"] = catalogue
        for field in ("normalizerProducer", "reportProducer"):
            entry[field]["image"] = ANALYSIS_IMAGE
    checkout["executionTemplate"] = "jobs/checkout.json"
    benchmark.update(
        contractsVersion=contracts.VERSION,
        rawProducer={
            "name": "kube-burner",
            "version": "2.8.5",
            "artifact": {"kind": "oci-image", "image": RUNNER_IMAGE},
        },
        executionTemplate="jobs/benchmark.json",
        workload={
            "id": "pod-startup-contained",
            "version": "1.0.0",
            "sha256": inputs.digest(read(root, "identities/workloads/pod-startup-contained.json")),
        },
        environment={
            "id": "local-kind-integration",
            "version": "1.0.0",
            "sha256": ENVIRONMENT_SHA256,
            "fingerprint": FINGERPRINT,
        },
        benchmark={
            "clusterId": "perfeng-local",
            "clusterUid": CLUSTER_UID,
            "environmentFile": "identities/environment.json",
            "templateSha256": inputs.digest(inputs.read(inputs.PACKAGE / "pod.yml")),
            "bucket": "perfeng-artifacts",
        },
    )
    return {"schemaVersion": 1, "entries": [benchmark, checkout]}


def provenance(root: Path) -> dict[str, Any]:
    """Retain reviewed receipt provenance, not a reusable authorization or a fabricated live receipt."""
    return {
        "schemaVersion": 1,
        "controlPlaneValidator": {
            "repository": "https://github.com/stanimirivanov/perfeng-control-plane",
            "gitSha": VALIDATOR_REVISION,
        },
        "qualification": {
            "sha256": "6e3779991cdaace896a1a00a4d7fd7f118a071080bed4d0c6d561653d6251217",
            "sizeBytes": 4285,
            "reviewedStatus": "ACCEPTED",
            "purpose": "integration",
            "captureWindow": {
                "start": "2026-10-15T10:46:03.756000Z",
                "end": "2026-10-15T10:46:31.524271Z",
            },
            "profileSha256": inputs.PROFILE_SHA256,
            "environmentSource": {
                "repository": "https://github.com/stanimirivanov/perfeng-environment",
                "gitSha": "3924b55a6c3119609491f45447a09541e219f353",
            },
        },
        "files": {name: inputs.digest(read(root, name)) for name in sorted(FILES)},
    }


def validate(root: Path = BUNDLE) -> None:
    """Verify the complete promoted closure offline; live admission and deployment remain separate."""
    inventory = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    require(inventory == FILES | {"README.md", "provenance.json"}, "unexpected file inventory")
    require(
        document(root, "provenance.json") == provenance(root), "provenance or file checksum differs"
    )
    for name, expected in (
        (
            "identities/kube-burner-image.json",
            image_record("perfeng-kube-burner", RUNNER_IMAGE, RUNNER_REVISION),
        ),
        (
            "identities/analysis-image.json",
            image_record("perfeng-analysis", ANALYSIS_IMAGE, ANALYSIS_REVISION),
        ),
        ("jobs/benchmark.json", benchmark_template()),
        ("jobs/checkout.json", checkout_template()),
        ("policies/pod-startup.json", policy()),
    ):
        require(document(root, name) == expected, name + " differs from the reviewed selection")
    for name in ("analysis.yaml", "reporting.yaml"):
        require(
            yaml.safe_load(read(root, "jobs/" + name)) == transfer_template(name),
            name + " transfer or credential boundary differs",
        )
    for name, source in (
        ("identities/checkout-environment.json", LEGACY / "identities/environment.json"),
        ("identities/k6-image.json", LEGACY / "identities/k6-image.json"),
        (
            "identities/workloads/checkout-smoke.json",
            LEGACY / "identities/workloads/checkout-smoke.json",
        ),
        ("identities/workloads/pod-startup-contained.json", inputs.PACKAGE / "workload.json"),
        ("policies/checkout-smoke.json", LEGACY / "policies/checkout-smoke.json"),
    ):
        require(read(root, name) == inputs.read(source), name + " source bytes differ")
    require(
        inputs.digest(read(root, "identities/environment.json")) == ENVIRONMENT_SHA256,
        "accepted environment bytes differ",
    )
    contracts.validate("environment", document(root, "identities/environment.json"))
    catalogue = inputs.object_json(inputs.read(LEGACY / "identities/catalogue.json"))
    catalogue["version"] = "1.2.0"
    catalogue["tests"][0]["workload"] = "pod-startup-contained"
    require(document(root, "identities/catalogue.json") == catalogue, "catalogue cohort differs")
    require(
        document(root, "registry.json") == registry(root),
        "registry identity, admission or authorization differs",
    )
