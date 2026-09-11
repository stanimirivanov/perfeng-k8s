from __future__ import annotations

import unittest

from scripts import deployment


class DeploymentValidationTests(unittest.TestCase):
    def test_control_plane_chart_is_restricted_and_requires_external_configuration(self) -> None:
        deployment.validate_control_plane_chart()

    def test_mutable_control_plane_image_is_rejected(self) -> None:
        deployment.helm(
            "template",
            "control-plane",
            str(deployment.CONTROL_PLANE_CHART),
            "--values",
            str(deployment.CONTROL_PLANE_VALUES),
            "--set-string",
            "image=ghcr.io/stanimirivanov/perfeng-control-plane:latest",
            succeeds=False,
        )

    def test_invalid_image_pull_secret_name_is_rejected(self) -> None:
        deployment.helm(
            "template",
            "control-plane",
            str(deployment.CONTROL_PLANE_CHART),
            "--values",
            str(deployment.CONTROL_PLANE_VALUES),
            "--set-string",
            "imagePullSecret=other/secret",
            succeeds=False,
        )

    def test_registry_mount_cannot_escape_its_volume(self) -> None:
        deployment.helm(
            "template",
            "control-plane",
            str(deployment.CONTROL_PLANE_CHART),
            "--values",
            str(deployment.CONTROL_PLANE_VALUES),
            "--set-string",
            "registryItems[0].path=../escape",
            succeeds=False,
        )


if __name__ == "__main__":
    unittest.main()
