"""Promotion regressions for exact identities, closed inputs and isolated execution authority."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

from scripts import contained_inputs as inputs
from scripts import kubernetes_bundle as bundle


class KubernetesBundleTests(unittest.TestCase):
    def test_reviewed_bundle_is_complete_and_keeps_distinct_workload_cohorts(self):
        bundle.validate()
        benchmark, checkout = bundle.document(bundle.BUNDLE, "registry.json")["entries"]
        self.assertEqual(benchmark["workload"]["id"], "pod-startup-contained")
        self.assertEqual(checkout["workload"]["id"], "checkout-smoke")
        self.assertNotEqual(benchmark["environment"], checkout["environment"])
        self.assertEqual(benchmark["benchmark"]["clusterUid"], bundle.CLUSTER_UID)
        self.assertEqual(
            bundle.document(bundle.BUNDLE, "policies/pod-startup.json")["spec"]["rules"][0][
                "regression"
            ]["reference"]["baselineId"],
            bundle.BASELINE_ID,
        )

    def test_rehashed_registry_cannot_change_identity_admission_or_principals(self):
        cases = (
            (("entries", 0, "rawProducer", "artifact", "image"), "example.invalid/runner:latest"),
            (("entries", 0, "benchmark"), None),
            (("entries", 0, "benchmark", "clusterUid"), "11111111-1111-4111-8111-111111111111"),
            (("entries", 0, "environment", "fingerprint"), "a" * 64),
            (("entries", 0, "workload", "id"), "pod-startup-smoke"),
            (("entries", 0, "principals"), ["*"]),
            (("entries", 0, "normalizerProducer", "image"), "example.invalid/analysis:latest"),
            (("entries", 1, "environment", "fingerprint"), bundle.FINGERPRINT),
        )
        for keys, value in cases:
            with self.subTest(keys=keys), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_bundle(Path(temporary))
                registry = bundle.document(root, "registry.json")
                current: Any = registry
                for key in keys[:-1]:
                    current = current[key]
                current[keys[-1]] = value
                self.write_and_rehash(root, "registry.json", inputs.encode(registry))
                with self.assertRaisesRegex(ValueError, "registry identity"):
                    bundle.validate(root)

    def test_template_rehash_cannot_restore_wrong_storage_bindings_or_share_tokens(self):
        for mutation in ("endpoint", "key", "token", "run identity"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_bundle(Path(temporary))
                job = bundle.document(root, "jobs/benchmark.json")
                pod = job["spec"]["template"]["spec"]
                publisher = pod["containers"][0]
                if mutation == "endpoint":
                    publisher["env"][0]["value"] = (
                        "http://seaweedfs-s3.perf-platform.svc.cluster.local:8333"
                    )
                elif mutation == "key":
                    publisher["env"][1]["valueFrom"]["secretKeyRef"]["key"] = "access-key-id"
                elif mutation == "token":
                    publisher["volumeMounts"].append({"name": "api", "mountPath": "/token"})
                else:
                    job["metadata"] = {"name": "perf-20261015-120000-abcdef12"}
                self.write_and_rehash(root, "jobs/benchmark.json", inputs.encode(job))
                with self.assertRaisesRegex(ValueError, "jobs/benchmark.json differs"):
                    bundle.validate(root)

    def test_transfer_credentials_and_publication_cannot_drift_after_rehash(self):
        for name in ("analysis.yaml", "reporting.yaml"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_bundle(Path(temporary))
                job = yaml.safe_load(bundle.read(root, "jobs/" + name))
                pod = job["spec"]["template"]["spec"]
                pod["containers"][0]["env"] = pod["initContainers"][0]["env"]
                self.write_and_rehash(root, "jobs/" + name, yaml.safe_dump(job).encode())
                with self.assertRaisesRegex(ValueError, "transfer or credential boundary"):
                    bundle.validate(root)

    def test_source_bytes_receipt_and_file_inventory_are_not_replaceable(self):
        for mutation in ("environment", "workload", "receipt", "extra file", "checksum"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_bundle(Path(temporary))
                if mutation == "environment":
                    self.write_and_rehash(root, "identities/environment.json", b"{}\n")
                elif mutation == "workload":
                    path = "identities/workloads/pod-startup-contained.json"
                    self.write_and_rehash(root, path, b"{}\n")
                elif mutation == "receipt":
                    document = bundle.document(root, "provenance.json")
                    document["qualification"]["reviewedStatus"] = "UNKNOWN"
                    (root / "provenance.json").write_bytes(inputs.encode(document))
                elif mutation == "extra file":
                    (root / "unreviewed.json").write_bytes(b"{}\n")
                else:
                    with (root / "registry.json").open("ab") as output:
                        output.write(b" ")
                with self.assertRaises(ValueError):
                    bundle.validate(root)

    def test_validator_pin_is_the_same_in_make_ci_and_provenance(self):
        makefile = (bundle.ROOT / "Makefile").read_text()
        workflow = (bundle.ROOT / ".github/workflows/validate.yml").read_text()
        self.assertIn("REGISTRY_VALIDATOR_REVISION := " + bundle.VALIDATOR_REVISION, makefile)
        self.assertIn("ref: " + bundle.VALIDATOR_REVISION, workflow)
        self.assertEqual(
            bundle.document(bundle.BUNDLE, "provenance.json")["controlPlaneValidator"]["gitSha"],
            bundle.VALIDATOR_REVISION,
        )

    def copy_bundle(self, root: Path) -> Path:
        destination = root / "bundle"
        shutil.copytree(bundle.BUNDLE, destination)
        return destination

    def write_and_rehash(self, root: Path, name: str, content: bytes) -> None:
        (root / name).write_bytes(content)
        provenance = bundle.document(root, "provenance.json")
        provenance["files"][name] = inputs.digest(content)
        (root / "provenance.json").write_bytes(inputs.encode(provenance))
