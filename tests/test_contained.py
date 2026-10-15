"""Offline behavioral tests for containment, Run capture and completion-marker publication."""

from __future__ import annotations

import copy
import io
import itertools
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import yaml
from botocore.exceptions import ClientError

from scripts import contained_contracts as schema
from scripts import contained_definition as definition
from scripts import contained_inputs as inputs
from scripts import contained_observation as observation
from scripts import contained_publish as publisher
from scripts import contained_run as runner
from tests.test_manifest import payloads

RUN_ID = "perf-20260908-120000-a1b2c3d4"
UID = "11111111-1111-4111-8111-111111111111"
START = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def node_documents():
    profile = inputs.object_json(inputs.read(inputs.PACKAGE / "profile.json"))["spec"]
    return [
        {
            "metadata": {
                "name": name,
                "uid": f"{index:08d}-1111-4111-8111-111111111111",
                "labels": {"workload": role},
            },
            "spec": {},
            "status": {
                "nodeInfo": {
                    "kubeletVersion": "v1.35.0",
                    "containerRuntimeVersion": "containerd://2.2.0",
                    "architecture": "amd64",
                    "operatingSystem": "linux",
                },
                "allocatable": {"cpu": "4", "memory": "8Gi"},
                "images": [{"names": [inputs.CANDIDATE]}],
                "conditions": [
                    {"type": key, "status": "True" if key == "Ready" else "False"}
                    for key in ("Ready", "MemoryPressure", "DiskPressure", "PIDPressure")
                ],
            },
        }
        for index, (name, role) in enumerate(profile["nodes"].items(), 1)
    ]


def request_files(root: Path):
    profile = inputs.object_json(inputs.read(inputs.PACKAGE / "profile.json"))
    nodes: list[dict[str, Any]] = [
        {
            "name": node["metadata"]["name"],
            "uid": node["metadata"]["uid"],
            "kubernetesVersion": "v1.35.0",
            "containerRuntimeVersion": "containerd://2.2.0",
            "architecture": "amd64",
            "allocatable": {"cpuMilliCores": 4000, "memoryBytes": 8 * 1024**3},
        }
        for node in node_documents()
    ]
    basis = {
        "profileSha256": inputs.PROFILE_SHA256,
        "nodeImage": inputs.NODE_IMAGE,
        "kubeSystemUid": UID,
        "observedNodes": sorted(nodes, key=lambda node: node["name"]),
    }
    fingerprint = inputs.digest(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode())
    environment = {
        "cluster": "perfeng-local",
        "fingerprint": fingerprint,
        "kubernetes": {
            "version": "v1.35.0",
            "nodeCount": 3,
            "nodePools": [
                {"name": name, "cpuArchitecture": "amd64"}
                for name in profile["spec"]["nodes"].values()
            ],
        },
        "application": {"configurationHash": inputs.PROFILE_SHA256},
    }
    environment_bytes = inputs.encode(environment)
    value = {
        "schemaVersion": 1,
        "runId": RUN_ID,
        "testId": "pod-startup-k8s",
        "runnerImage": "ghcr.io/stanimirivanov/perfeng-kube-burner@sha256:" + "a" * 64,
        "candidateImage": inputs.CANDIDATE,
        "workload": {
            "id": "pod-startup-contained",
            "version": "1.0.0",
            "sha256": inputs.digest(inputs.read(inputs.PACKAGE / "workload.json")),
        },
        "templateSha256": inputs.digest(inputs.read(inputs.PACKAGE / "pod.yml")),
        "namespace": "perfeng-benchmark-" + RUN_ID,
        "namespaceUid": UID,
        "kubeSystemUid": UID,
        "environment": {
            "id": "local-kind-integration",
            "version": "1.0.0",
            "sha256": inputs.digest(environment_bytes),
            "fingerprint": fingerprint,
        },
        "bucket": "perfeng-artifacts",
    }
    (root / "environment.json").write_bytes(environment_bytes)
    content = inputs.encode(value)
    (root / "request.json").write_bytes(content)
    return inputs.load(root / "request.json", inputs.digest(content)), nodes


class API:
    def __init__(self, request):
        self.request = request
        self.nodes = node_documents()
        self.pods = []
        self.missing_metrics = False
        self.namespace_uid = UID
        self.quota = {
            "pods": "10",
            "limits.cpu": "100m",
            "limits.memory": "160Mi",
            "limits.ephemeral-storage": "10Mi",
        }
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        if path == "/api/v1/nodes":
            return {"items": copy.deepcopy(self.nodes)}
        if path.endswith("resourcequotas/benchmark-budget"):
            return {"spec": {"hard": self.quota}}
        if path == "/api/v1/namespaces/kube-system":
            return {"metadata": {"uid": UID}}
        if path.endswith("/pods"):
            return {"items": self.pods}
        if path == "/api/v1/namespaces/" + self.request.namespace:
            return {
                "metadata": {
                    "uid": self.namespace_uid,
                    "labels": {
                        "perfeng.io/run-id": RUN_ID,
                        "perfeng.io/owner": "perfeng-control-plane",
                        "pod-security.kubernetes.io/enforce": "restricted",
                        "pod-security.kubernetes.io/enforce-version": "v1.35",
                    },
                }
            }
        if "metrics.k8s.io" in path:
            if self.missing_metrics:
                raise ValueError("metrics unavailable")
            return {
                "items": [
                    {
                        "metadata": {"name": node["metadata"]["name"]},
                        "timestamp": observation.stamp(observation.now()),
                        "window": "30s",
                        "usage": {"cpu": "200m", "memory": "1Gi"},
                    }
                    for node in self.nodes
                ]
            }
        raise AssertionError("Unreviewed API access: " + path)


class Storage:
    def __init__(self):
        self.objects = {}
        self.writes = []
        self.corrupt = None

    def put_object(self, **args):
        assert args["IfNoneMatch"] == "*"
        self.writes.append(args["Key"])
        if args["Key"] in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[args["Key"]] = args

    def get_object(self, **args):
        value = self.objects[args["Key"]]
        body = value["Body"] if self.corrupt != args["Key"] else b"changed"
        return {
            "Body": io.BytesIO(body),
            "ContentLength": len(value["Body"]),
            "ContentType": value["ContentType"],
            "Metadata": value["Metadata"],
        }


class PublisherClientTests(unittest.TestCase):
    def test_reviewed_endpoints_use_only_explicit_publisher_credentials(self):
        for endpoint in (
            "http://seaweedfs.perf-platform.svc.cluster.local:8333",
            "https://storage.example.test",
            "https://storage.example.test:9443/",
        ):
            with (
                self.subTest(endpoint=endpoint),
                patch.dict(
                    os.environ,
                    {
                        "PERFENG_S3_ENDPOINT": endpoint,
                        "AWS_ACCESS_KEY_ID": "synthetic-access",
                        "AWS_SECRET_ACCESS_KEY": "synthetic-secret",
                    },
                    clear=True,
                ),
                patch.object(publisher.boto3, "client") as sdk,
            ):
                self.assertIs(publisher.client(), sdk.return_value)
                sdk.assert_called_once()
                self.assertEqual(sdk.call_args.args, ("s3",))
                options = sdk.call_args.kwargs
                self.assertEqual(options["endpoint_url"], endpoint)
                self.assertEqual(options["aws_access_key_id"], "synthetic-access")
                self.assertEqual(options["aws_secret_access_key"], "synthetic-secret")
                self.assertEqual(options["config"].proxies, {})
                self.assertEqual(options["config"].retries, {"total_max_attempts": 2})

    def test_unreviewed_http_and_decorated_endpoints_never_create_a_client(self):
        for endpoint in (
            "http://seaweedfs-s3.perf-platform.svc.cluster.local:8333",
            "http://storage.example.test:8333",
            "http://seaweedfs.perf-platform.svc.cluster.local.evil.test:8333",
            "http://seaweedfs.perf-platform.svc.cluster.local:8334",
            "http://seaweedfs.perf-platform.svc.cluster.local:8333/",
            "http://seaweedfs.perf-platform.svc.cluster.local:8333?token=value",
            "http://seaweedfs.perf-platform.svc.cluster.local:8333#fragment",
            "https://user:password@storage.example.test",
            "https://storage.example.test/bucket",
            "https://storage.example.test?token=value",
            "https://storage.example.test#fragment",
        ):
            with (
                self.subTest(endpoint=endpoint),
                patch.dict(os.environ, {"PERFENG_S3_ENDPOINT": endpoint}, clear=True),
                patch.object(publisher.boto3, "client") as sdk,
            ):
                with self.assertRaises(ValueError):
                    publisher.client()
                sdk.assert_not_called()

    def test_missing_credentials_never_fall_back_to_sdk_discovery(self):
        for missing in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
            environment = {
                "PERFENG_S3_ENDPOINT": "http://seaweedfs.perf-platform.svc.cluster.local:8333",
                "AWS_ACCESS_KEY_ID": "synthetic-access",
                "AWS_SECRET_ACCESS_KEY": "synthetic-secret",
            }
            del environment[missing]
            with (
                self.subTest(missing=missing),
                patch.dict(os.environ, environment, clear=True),
                patch.object(publisher.boto3, "client") as sdk,
            ):
                with self.assertRaises(KeyError):
                    publisher.client()
                sdk.assert_not_called()


class ContainedTests(unittest.TestCase):
    def setUp(self):
        clock = patch.object(observation, "now", return_value=START + timedelta(seconds=60))
        clock.start()
        self.addCleanup(clock.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.request, self.nodes = request_files(self.root)
        self.api = API(self.request)

    def tearDown(self):
        self.temporary.cleanup()

    def capture(self):
        output = self.root / "results"
        output.mkdir()
        for name, content in payloads().items():
            (output / name).write_bytes(content)
        samples = []
        for seconds in (0, 20, 40, 60):
            with patch.object(observation, "now", return_value=START + timedelta(seconds=seconds)):
                nodes, current, checks = observation.sample(self.api, self.request, "executor-uid")
            samples.extend(current)
        qualification = observation.evidence(
            self.request, nodes, samples, checks, START - timedelta(seconds=1), observation.now()
        )
        (output / "qualification.json").write_bytes(inputs.encode(qualification))
        (output / "resolved-inputs.json").write_bytes(
            inputs.encode(inputs.resolved_document(self.request, output))
        )
        (output / "runner.log").write_bytes(b"completed\n")
        receipt = {
            "schemaVersion": 1,
            "kind": "ContainedKubernetesExecution",
            "runId": RUN_ID,
            "requestSha256": self.request.sha256,
            "exitCode": 0,
            "startedAt": observation.stamp(START),
            "completedAt": observation.stamp(observation.now()),
            "artifacts": {
                name: {
                    "sha256": inputs.digest(inputs.read(output / name)),
                    "sizeBytes": len(inputs.read(output / name)),
                }
                for name in inputs.FILES
            },
        }
        (output / "complete.json").write_bytes(inputs.encode(receipt))
        return output

    def test_request_is_bound_to_source_candidate_profile_and_exact_environment(self):
        path = self.root / "request.json"
        with self.assertRaises(ValueError):
            inputs.load(path, "f" * 64)
        for key, value in (
            ("candidateImage", "wrong"),
            ("namespace", "perf-platform"),
            ("runnerImage", "tag:latest"),
            ("workload", {}),
            ("templateSha256", "f" * 64),
            ("command", ["bad"]),
        ):
            changed = copy.deepcopy(self.request.value)
            changed[key] = value
            content = inputs.encode(changed)
            path.write_bytes(content)
            with self.subTest(key=key), self.assertRaises(ValueError):
                inputs.load(path, inputs.digest(content))

    def test_contained_configuration_has_no_preloading_namespace_creation_or_gc(self):
        resolved = inputs.resolve(self.request, self.root)
        config = yaml.safe_load(resolved["config.yml"])
        self.assertFalse(config["global"]["gc"])
        for key in ("gc", "cleanup", "preLoadImages"):
            self.assertFalse(config["jobs"][0][key])
        pod = yaml.safe_load(resolved["pod.yml"].replace("{{.Iteration}}", "0"))
        self.assertEqual(pod["metadata"]["namespace"], self.request.namespace)
        self.assertEqual(pod["spec"]["containers"][0]["imagePullPolicy"], "Never")
        self.assertFalse(pod["spec"]["automountServiceAccountToken"])
        unusual_path = self.root / "output\ninjected: value"
        safe_config = yaml.safe_load(inputs.resolve(self.request, unusual_path)["config.yml"])
        self.assertEqual(
            safe_config["metricsEndpoints"][0]["indexer"]["metricsDirectory"],
            unusual_path.as_posix(),
        )

    def test_guard_refuses_namespace_replacement_bad_quota_and_nonempty_targets(self):
        observation.guard(self.api, self.request, empty=True)
        self.api.namespace_uid = "replacement"
        with self.assertRaises(ValueError):
            observation.guard(self.api, self.request)
        self.api.namespace_uid = UID
        self.api.quota["pods"] = "11"
        with self.assertRaises(ValueError):
            observation.guard(self.api, self.request)
        self.api.quota["pods"] = "10"
        self.api.pods = [{"unexpected": "pod"}]
        with self.assertRaises(ValueError):
            observation.guard(self.api, self.request, empty=True)

    def test_actual_nodes_and_unavailable_metrics_do_not_fabricate_acceptance(self):
        nodes, samples, checks = observation.sample(self.api, self.request, "executor-uid")
        self.assertTrue(all(value == "PASS" for value in checks.values()))
        self.api.missing_metrics = True
        nodes, samples, checks = observation.sample(self.api, self.request, "executor-uid")
        self.assertEqual(checks["interference"], "UNKNOWN")
        self.assertEqual(samples[0]["usage"]["source"], "unavailable")
        self.api.nodes[0]["status"]["conditions"][0]["status"] = "False"
        nodes, samples, checks = observation.sample(self.api, self.request, "executor-uid")
        result = observation.evidence(
            self.request, nodes, samples, checks, START, observation.now()
        )
        self.assertEqual(result["status"], "REJECTED")
        self.api.nodes[0]["metadata"]["uid"] = "replacement"
        with self.assertRaises(ValueError):
            observation.sample(self.api, self.request, "executor-uid")

    def test_foreign_generator_or_missing_warm_image_prevents_acceptance(self):
        self.api.pods = [
            {
                "metadata": {"uid": "other", "namespace": "perf-generators"},
                "status": {"phase": "Running"},
            }
        ]
        self.assertEqual(
            observation.sample(self.api, self.request, "executor-uid")[2]["interference"], "FAIL"
        )
        self.api.pods = []
        for node in self.api.nodes:
            node["status"]["images"] = []
        self.assertEqual(
            observation.sample(self.api, self.request, "executor-uid")[2]["capacity"], "FAIL"
        )

    def test_manifest_last_conditional_publication_and_exact_retry(self):
        with patch.object(observation, "now", return_value=START + timedelta(seconds=60)):
            output = self.capture()
        storage = Storage()
        marker = publisher.publish(storage, self.request, output)
        key = f"runs/{RUN_ID}/raw-result.json"
        self.assertEqual(storage.writes[-1], key)
        self.assertEqual(marker["uri"], "s3://perfeng-artifacts/" + key)
        self.assertEqual(len(storage.objects), 7)
        self.assertEqual(publisher.publish(storage, self.request, output), marker)
        raw = json.loads(storage.objects[key]["Body"])
        self.assertEqual(raw["producer"]["artifact"]["kind"], "oci-image")
        schema.validate("raw-result", raw)

    def test_partial_changed_or_corrupt_prerequisites_never_publish_marker(self):
        with patch.object(observation, "now", return_value=START + timedelta(seconds=60)):
            output = self.capture()
        storage = Storage()
        storage.corrupt = f"runs/{RUN_ID}/raw/jobSummary.json"
        with self.assertRaises(ValueError):
            publisher.publish(storage, self.request, output)
        self.assertNotIn(f"runs/{RUN_ID}/raw-result.json", storage.objects)
        (output / "runner.log").write_bytes(b"changed")
        storage = Storage()
        with self.assertRaises(ValueError):
            publisher.publish(storage, self.request, output)
        self.assertFalse(storage.writes)

    def test_no_success_receipt_is_written_when_tool_fails(self):
        binary = self.root / "binary"
        binary.write_bytes(b"binary")
        process = MagicMock()
        process.poll.return_value = 2
        process.returncode = 2
        with (
            patch.object(runner, "EXECUTABLE", binary),
            patch.object(runner, "EXECUTABLE_SHA256", inputs.digest(b"binary")),
            patch.object(runner.subprocess, "Popen", return_value=process),
            self.assertRaises(ValueError),
        ):
            runner.run(self.request, self.root / "results", self.api, "executor-uid")
        self.assertFalse((self.root / "results/complete.json").exists())

    def test_rendering_and_rejection_gates_cover_permissions_and_credential_separation(self):
        definition.validate()
        objects = definition.render()
        role = next(value for value in objects if value["kind"] == "Role")
        role["rules"][0]["verbs"].append("delete")
        with self.assertRaises(ValueError):
            definition.validate_objects(objects)

    def test_chart_uses_existing_uploader_secret_keys_and_rejects_key_drift(self):
        objects = definition.render(
            "s3Endpoint=http://seaweedfs.perf-platform.svc.cluster.local:8333"
        )
        job = next(value for value in objects if value["kind"] == "Job")
        environment = job["spec"]["template"]["spec"]["containers"][0]["env"]
        self.assertEqual(
            environment,
            [
                {
                    "name": "PERFENG_S3_ENDPOINT",
                    "value": "http://seaweedfs.perf-platform.svc.cluster.local:8333",
                },
                {
                    "name": "AWS_ACCESS_KEY_ID",
                    "valueFrom": {
                        "secretKeyRef": {"name": "synthetic-storage", "key": "access-key"}
                    },
                },
                {
                    "name": "AWS_SECRET_ACCESS_KEY",
                    "valueFrom": {
                        "secretKeyRef": {"name": "synthetic-storage", "key": "secret-key"}
                    },
                },
            ],
        )
        definition.validate_objects(objects)
        for index, key in ((1, "access-key-id"), (2, "secret-access-key")):
            with self.subTest(key=key):
                altered = copy.deepcopy(objects)
                job = next(value for value in altered if value["kind"] == "Job")
                job["spec"]["template"]["spec"]["containers"][0]["env"][index]["valueFrom"][
                    "secretKeyRef"
                ]["key"] = key
                with self.assertRaisesRegex(ValueError, "publisher credentials"):
                    definition.validate_objects(altered)

    def test_chart_accepts_https_and_rejects_obsolete_or_unreviewed_http_endpoints(self):
        definition.validate_objects(definition.render("s3Endpoint=https://storage.example.test"))
        for endpoint in (
            "http://seaweedfs-s3.perf-platform.svc.cluster.local:8333",
            "http://storage.example.test:8333",
            "http://seaweedfs.perf-platform.svc.cluster.local.evil.test:8333",
            "http://seaweedfs.perf-platform.svc.cluster.local:8334",
            "http://seaweedfs.perf-platform.svc.cluster.local:8333/",
        ):
            with self.subTest(endpoint=endpoint):
                definition.render("s3Endpoint=" + endpoint, succeeds=False)

    def test_supervised_success_freezes_complete_inputs_before_publication(self):
        binary = self.root / "binary"
        binary.write_bytes(b"binary")
        output = self.root / "results"
        clock = itertools.count()

        def process_for(command, **kwargs):
            self.assertNotIn("AWS_ACCESS_KEY_ID", kwargs["env"])
            self.assertNotIn("KUBECONFIG", kwargs["env"])
            self.assertEqual(command[1], "init")
            for name, content in payloads().items():
                (output / name).write_bytes(content)
            process = MagicMock()
            process.poll.return_value = 0
            process.returncode = 0
            return process

        with (
            patch.object(runner, "EXECUTABLE", binary),
            patch.object(runner, "EXECUTABLE_SHA256", inputs.digest(b"binary")),
            patch.object(runner.subprocess, "Popen", side_effect=process_for),
            patch.object(
                observation, "now", side_effect=lambda: START + timedelta(seconds=next(clock))
            ),
        ):
            runner.run(self.request, output, self.api, "executor-uid")
        manifest, contents = publisher.prepare(self.request, output)
        self.assertEqual(set(contents), set(inputs.FILES))
        self.assertEqual(json.loads(contents["qualification.json"])["status"], "ACCEPTED")
        self.assertEqual(manifest["runId"], RUN_ID)

    def test_publisher_refuses_semantically_contradictory_or_sparse_node_samples(self):
        output = self.capture()
        path = output / "qualification.json"
        value = inputs.object_json(inputs.read(path))
        value["samples"][0]["conditions"]["ready"] = "FALSE"
        content = inputs.encode(value)
        path.write_bytes(content)
        receipt = inputs.object_json(inputs.read(output / "complete.json"))
        receipt["artifacts"]["qualification.json"] = {
            "sha256": inputs.digest(content),
            "sizeBytes": len(content),
        }
        (output / "complete.json").write_bytes(inputs.encode(receipt))
        storage = Storage()
        with self.assertRaises(ValueError):
            publisher.publish(storage, self.request, output)
        self.assertFalse(storage.writes)


if __name__ == "__main__":
    unittest.main()
