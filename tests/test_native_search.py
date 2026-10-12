"""Offline acceptance for the candidate chart and publisher-provided provenance."""

from __future__ import annotations

import copy
import unittest
from typing import Any

import yaml

from scripts import contracts, deployment, native_search


class NativeSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.objects = native_search.render()

    def test_chart_is_strictly_linted_and_isolated(self) -> None:
        native_search.validate()

    def test_release_matches_the_supplied_publisher_receipt(self) -> None:
        identity = native_search.validate_identity(
            contracts.parse_json(native_search.IDENTITY.read_bytes())
        )
        self.assertEqual(
            identity,
            {
                "schemaVersion": 1,
                "name": "perfeng-native-search",
                "version": "1.0.0",
                "image": "ghcr.io/stanimirivanov/perfeng-native-search@sha256:"
                "3f6179c9f3784be884761e7c6ceb4229c48631b8290d5cc65d0b488eef3b4386",
                "source": {
                    "repository": "https://github.com/stanimirivanov/perfeng-environment",
                    "gitSha": "753022c24bbf2f30fd3a620e0788f9b53ae16dd7",
                },
                "targetSha256": "ff03e1d7a7544557a3f035218b6b3e3bcce7e434996be5dd3b895af10cbc0fb4",
                "platform": "linux/amd64",
            },
        )

    def test_provenance_rejects_aliases_wrong_platform_and_synthetic_identity(self) -> None:
        identity = contracts.parse_json(native_search.IDENTITY.read_bytes())
        for field, value in (
            ("image", "ghcr.io/stanimirivanov/perfeng-native-search:latest"),
            ("image", "ghcr.io/stanimirivanov/perfeng-native-search:v1@sha256:" + "a" * 64),
            ("image", "ghcr.io/stanimirivanov/perfeng-native-search@sha256:" + "a" * 64),
            ("platform", "windows/amd64"),
            ("schemaVersion", True),
            ("targetSha256", "a" * 64),
            ("extra", "unreviewed"),
        ):
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(identity)
                changed[field] = value
                with self.assertRaises(deployment.DeploymentValidationError):
                    native_search.validate_identity(changed)
        for field, value in (
            ("repository", "https://github.com/other/repository"),
            ("gitSha", "main"),
            ("gitSha", "a" * 40),
            ("extra", "unreviewed"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(identity)
                changed["source"][field] = value
                with self.assertRaises(deployment.DeploymentValidationError):
                    native_search.validate_identity(changed)

    def test_values_reject_mutability_exposure_and_runtime_override(self) -> None:
        for override in (
            "image=",
            "imagePullSecret=",
            "imagePullSecret=other/secret",
            "imagePullSecret=invalid..name",
            "imagePullSecret=" + "a" * 254,
            "image=ghcr.io/stanimirivanov/perfeng-native-search:latest",
            "image=ghcr.io/stanimirivanov/perfeng-native-search:v1@sha256:" + "a" * 64,
            "image=ghcr.io/other/search@sha256:" + "a" * 64,
            "replicas=2",
            "service.type=NodePort",
            "command[0]=sh",
            "securityContext.privileged=true",
            "extraVolumes[0].hostPath.path=/",
        ):
            with self.subTest(override=override):
                native_search.render(override, succeeds=False)

    def test_chart_without_caller_selection_is_not_deployable(self) -> None:
        deployment.helm("template", "native-search", str(native_search.CHART), succeeds=False)

    def test_published_image_can_be_supplied_without_becoming_a_chart_default(self) -> None:
        identity = contracts.parse_json(native_search.IDENTITY.read_bytes())
        objects = native_search.render(f"image={identity['image']}")
        native_search.validate_objects(objects)
        pod = next(obj for obj in objects if obj["kind"] == "Deployment")["spec"]["template"][
            "spec"
        ]
        self.assertEqual(pod["containers"][0]["image"], identity["image"])
        defaults = yaml.safe_load((native_search.CHART / "values.yaml").read_text(encoding="utf-8"))
        self.assertEqual(defaults, {"image": "", "imagePullSecret": ""})

    def test_chart_scopes_all_resources_to_the_callers_release(self) -> None:
        content = deployment.helm(
            "template",
            "other-search",
            str(native_search.CHART),
            "--namespace",
            "other-targets",
            "--values",
            str(native_search.VALUES),
        )
        objects = list(yaml.safe_load_all(content.decode("utf-8")))
        for obj in objects:
            self.assertEqual(obj["metadata"]["name"], "other-search")
            self.assertEqual(obj["metadata"]["namespace"], "other-targets")
        pod = next(obj for obj in objects if obj["kind"] == "Deployment")["spec"]["template"]
        service = next(obj for obj in objects if obj["kind"] == "Service")
        self.assertEqual(service["spec"]["selector"], pod["metadata"]["labels"])
        self.assertEqual(pod["spec"]["serviceAccountName"], "other-search")

    def test_extra_resources_and_public_service_are_rejected(self) -> None:
        objects = copy.deepcopy(self.objects)
        objects.append({"kind": "Secret"})
        with self.assertRaisesRegex(deployment.DeploymentValidationError, "only one"):
            native_search.validate_objects(objects)
        for field, value in (
            ("type", "NodePort"),
            ("externalIPs", ["192.0.2.1"]),
            ("selector", {"app": "other"}),
        ):
            with self.subTest(field=field):
                objects = copy.deepcopy(self.objects)
                service = next(obj for obj in objects if obj["kind"] == "Service")
                service["spec"][field] = value
                with self.assertRaisesRegex(deployment.DeploymentValidationError, "Service must"):
                    native_search.validate_objects(objects)

    def test_numeric_looking_names_remain_strings(self) -> None:
        content = deployment.helm(
            "template",
            "12345",
            str(native_search.CHART),
            "--namespace",
            "67890",
            "--values",
            str(native_search.VALUES),
            "--set-string",
            "imagePullSecret=12345",
        )
        objects = list(yaml.safe_load_all(content.decode("utf-8")))
        for obj in objects:
            self.assertEqual(obj["metadata"]["name"], "12345")
            self.assertEqual(obj["metadata"]["namespace"], "67890")
            self.assertEqual(obj["metadata"]["labels"]["app.kubernetes.io/instance"], "12345")
        pod = next(obj for obj in objects if obj["kind"] == "Deployment")["spec"]["template"][
            "spec"
        ]
        self.assertEqual(pod["serviceAccountName"], "12345")
        self.assertEqual(pod["imagePullSecrets"], [{"name": "12345"}])

    def test_pod_execution_surface_drift_is_rejected(self) -> None:
        cases: list[tuple[str, Any]] = [
            ("automountServiceAccountToken", True),
            ("hostNetwork", True),
            ("initContainers", [{"name": "extra", "image": "other"}]),
            ("nodeSelector", {"kubernetes.io/os": "windows"}),
            ("securityContext", {"runAsUser": 0}),
            ("volumes", [{"name": "temporary", "hostPath": {"path": "/tmp"}}]),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                objects = copy.deepcopy(self.objects)
                pod = next(obj for obj in objects if obj["kind"] == "Deployment")["spec"][
                    "template"
                ]["spec"]
                pod[field] = value
                with self.assertRaises(deployment.DeploymentValidationError):
                    native_search.validate_objects(objects)

    def test_container_cannot_receive_credentials_or_overlay_the_fixture(self) -> None:
        cases: list[tuple[str, Any]] = [
            ("envFrom", [{"secretRef": {"name": "runtime-credentials"}}]),
            ("command", ["sh"]),
            ("resources", {}),
            ("securityContext", {"privileged": True}),
            ("volumeMounts", [{"name": "temporary", "mountPath": "/usr/share/nginx/html"}]),
            ("readinessProbe", {"exec": {"command": ["true"]}}),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                objects = copy.deepcopy(self.objects)
                pod = next(obj for obj in objects if obj["kind"] == "Deployment")["spec"][
                    "template"
                ]["spec"]
                pod["containers"][0][field] = value
                with self.assertRaises(deployment.DeploymentValidationError):
                    native_search.validate_objects(objects)

    def test_multiple_replicas_and_overlapping_rollout_are_rejected(self) -> None:
        for field, value in (("replicas", 2), ("strategy", {"type": "RollingUpdate"})):
            with self.subTest(field=field):
                objects = copy.deepcopy(self.objects)
                spec = next(obj for obj in objects if obj["kind"] == "Deployment")["spec"]
                spec[field] = value
                with self.assertRaisesRegex(deployment.DeploymentValidationError, "lifecycle"):
                    native_search.validate_objects(objects)


if __name__ == "__main__":
    unittest.main()
