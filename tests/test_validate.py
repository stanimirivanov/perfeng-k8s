from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

from scripts import validate


class BenchmarkValidationTests(unittest.TestCase):
    def test_repository_definitions_are_valid(self) -> None:
        validate.validate()

    def test_mutable_workload_image_is_rejected(self) -> None:
        config = self.load_config()
        config["jobs"][0]["objects"][0]["inputVars"]["containerImage"] = (
            "registry.k8s.io/pause:3.10.1"
        )

        with self.workload(config) as directory:
            with patch.object(validate, "WORKLOAD_ROOT", Path(directory)):
                with self.assertRaisesRegex(validate.ValidationError, "immutable pause image"):
                    validate.validate_workload()

    def test_unbounded_workload_is_rejected(self) -> None:
        config = self.load_config()
        config["jobs"][0]["jobIterations"] = 1000

        with self.workload(config) as directory:
            with patch.object(validate, "WORKLOAD_ROOT", Path(directory)):
                with self.assertRaisesRegex(validate.ValidationError, "1 through 25"):
                    validate.validate_workload()

    def test_template_service_account_access_is_rejected(self) -> None:
        config = self.load_config()

        with self.workload(config) as directory:
            workload_root = Path(directory)
            template_path = workload_root / "templates" / "pod.yml"
            template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
            template["spec"]["automountServiceAccountToken"] = True
            template_path.write_text(yaml.safe_dump(template), encoding="utf-8")
            with patch.object(validate, "WORKLOAD_ROOT", workload_root):
                with self.assertRaisesRegex(validate.ValidationError, "service-account policy"):
                    validate.validate_workload()

    def test_object_template_cannot_escape_workload(self) -> None:
        config = self.load_config()
        config["jobs"][0]["objects"][0]["objectTemplate"] = "../pod.yml"

        with self.workload(config) as directory:
            with patch.object(validate, "WORKLOAD_ROOT", Path(directory)):
                with self.assertRaisesRegex(validate.ValidationError, "inside the workload"):
                    validate.validate_workload()

    def test_runtime_bundle_identities_are_pinned(self) -> None:
        validate.validate_bundle()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(validate.BUNDLE_ROOT, root / "bundle")
            registry_path = root / "bundle" / "registry.json"
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registry["entries"][0]["normalizerProducer"]["image"] = (
                "ghcr.io/stanimirivanov/perfeng-analysis:latest"
            )
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            with patch.object(validate, "BUNDLE_ROOT", root / "bundle"):
                with self.assertRaisesRegex(validate.ValidationError, "verified analysis image"):
                    validate.validate_bundle()

    def test_analysis_job_cannot_predefine_staging_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.copy_bundle(Path(directory))
            job_path = bundle / "jobs" / "analysis.yaml"
            job = yaml.safe_load(job_path.read_text(encoding="utf-8"))
            job["spec"]["template"]["spec"]["initContainers"][0]["env"].append(
                {"name": "PERFENG_SOURCE_URI", "value": "s3://untrusted/source.json"}
            )
            job_path.write_text(yaml.safe_dump(job), encoding="utf-8")

            with patch.object(validate, "BUNDLE_ROOT", bundle):
                with self.assertRaisesRegex(validate.ValidationError, "reserved staging"):
                    validate.validate_analysis_job()

    def test_analysis_job_uses_only_restricted_storage_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.copy_bundle(Path(directory))
            job_path = bundle / "jobs" / "analysis.yaml"
            job = yaml.safe_load(job_path.read_text(encoding="utf-8"))
            credentials = job["spec"]["template"]["spec"]["initContainers"][0]["env"][0]
            credentials["valueFrom"]["secretKeyRef"]["name"] = "perfeng-s3-auth"
            job_path.write_text(yaml.safe_dump(job), encoding="utf-8")

            with patch.object(validate, "BUNDLE_ROOT", bundle):
                with self.assertRaisesRegex(validate.ValidationError, "restricted uploader"):
                    validate.validate_analysis_job()

    def test_analysis_job_requires_download_integrity_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = self.copy_bundle(Path(directory))
            job_path = bundle / "jobs" / "analysis.yaml"
            job = yaml.safe_load(job_path.read_text(encoding="utf-8"))
            initializer = job["spec"]["template"]["spec"]["initContainers"][0]
            initializer["args"][0] = initializer["args"][0].replace("sha256sum -c -", "true")
            job_path.write_text(yaml.safe_dump(job), encoding="utf-8")

            with patch.object(validate, "BUNDLE_ROOT", bundle):
                with self.assertRaisesRegex(validate.ValidationError, "integrity checks"):
                    validate.validate_analysis_job()

    def load_config(self) -> dict[str, Any]:
        return copy.deepcopy(
            yaml.safe_load((validate.WORKLOAD_ROOT / "config.yml").read_text(encoding="utf-8"))
        )

    def workload(self, config: dict[str, Any]) -> tempfile.TemporaryDirectory[str]:
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        (root / "templates").mkdir()
        (root / "config.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
        source = validate.WORKLOAD_ROOT / "templates" / "pod.yml"
        (root / "templates" / "pod.yml").write_bytes(source.read_bytes())
        return directory

    def copy_bundle(self, root: Path) -> Path:
        bundle = root / "bundle"
        shutil.copytree(validate.BUNDLE_ROOT, bundle)
        return bundle


if __name__ == "__main__":
    unittest.main()
