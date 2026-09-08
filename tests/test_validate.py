from __future__ import annotations

import copy
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


if __name__ == "__main__":
    unittest.main()
