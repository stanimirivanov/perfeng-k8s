"""Prove the staged, non-secret runtime package preserves the selected bytes."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path
from typing import Any

import yaml

from scripts import deployment

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundles/local-kind-integration/1.0.0"
PACKAGE = ROOT / "packages/runtime-inputs/local-kind-integration-1.0.0"
SOURCE_REVISION = "fa718c2b62f4f10b5e9da8dce7b00a3f51daae0b"
RUNTIME_NAME = "perfeng-control-plane-runtime-315a2eede8ff"
REGISTRY_NAME = "perfeng-runtime-registry-7be1d749994e"


def content_name(prefix: str, data: dict[str, str]) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:12]}"


def render() -> list[dict[str, Any]]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(PACKAGE)],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=60,
    )
    return list(yaml.safe_load_all(result.stdout.decode("utf-8")))


class RuntimeInputsTests(unittest.TestCase):
    def test_package_renders_only_the_two_current_non_secret_configmaps(self) -> None:
        objects = render()
        self.assertEqual(len(objects), 2)
        self.assertEqual(
            {obj["metadata"]["name"] for obj in objects}, {RUNTIME_NAME, REGISTRY_NAME}
        )
        for obj in objects:
            with self.subTest(name=obj["metadata"]["name"]):
                self.assertEqual((obj["apiVersion"], obj["kind"]), ("v1", "ConfigMap"))
                self.assertEqual(obj["metadata"]["namespace"], "perf-platform")
                self.assertEqual(
                    obj["metadata"]["labels"],
                    {"app.kubernetes.io/managed-by": "perfeng-environment"},
                )
                self.assertEqual(
                    obj["metadata"]["annotations"],
                    {"perfeng.io/deployment-revision": SOURCE_REVISION},
                )
                self.assertIs(obj["immutable"], True)
                self.assertEqual(set(obj), {"apiVersion", "kind", "metadata", "immutable", "data"})
                self.assertTrue(all(isinstance(value, str) for value in obj["data"].values()))
                prefix = re.sub(r"-[0-9a-f]{12}$", "", obj["metadata"]["name"])
                self.assertEqual(content_name(prefix, obj["data"]), obj["metadata"]["name"])

    def test_registry_mount_data_matches_reviewed_bundle_bytes(self) -> None:
        objects = {obj["metadata"]["name"]: obj for obj in render()}
        actual = objects[REGISTRY_NAME]["data"]
        registry = json.loads((BUNDLE / "registry.json").read_bytes())
        paths = {"registry.json", "jobs/analysis.yaml", "jobs/reporting.yaml"}
        for entry in registry["entries"]:
            paths.add(entry["policy"])
            if "executionTemplate" in entry:
                paths.add(entry["executionTemplate"])
            if "benchmark" in entry:
                paths.add(entry["benchmark"]["environmentFile"])
        expected = {
            path.replace("/", "--"): (BUNDLE / path).read_text(encoding="utf-8") for path in paths
        }
        self.assertEqual(actual, expected)

    def test_current_chart_references_are_unchanged(self) -> None:
        objects = deployment.render_control_plane(
            f"runtimeConfigMap={RUNTIME_NAME}", f"registryConfigMap={REGISTRY_NAME}"
        )
        workload = deployment.object_by_kind(objects, "Deployment")
        pod = workload["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertIn({"configMapRef": {"name": RUNTIME_NAME}}, container["envFrom"])
        self.assertEqual(
            next(volume for volume in pod["volumes"] if volume["name"] == "registry")["configMap"][
                "name"
            ],
            REGISTRY_NAME,
        )


if __name__ == "__main__":
    unittest.main()
