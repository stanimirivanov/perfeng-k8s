"""Offline packaging gates for the contained chart and immutable benchmark input closure."""

from collections.abc import Mapping, Sequence
from typing import Any

import yaml

from scripts import contained_inputs as inputs
from scripts import contracts, deployment

CHART = inputs.schema.ROOT / "charts/kube-burner-execution"
VALUES = inputs.schema.ROOT / "testdata/kube-burner-values.yaml"


def require(condition: bool, message: str) -> None:
    """Fail packaging on privilege expansion, incomplete ownership or credential-boundary drift."""
    if not condition:
        raise deployment.DeploymentValidationError("contained benchmark: " + message)


def render(*overrides: str, succeeds: bool = True) -> list[Mapping[str, Any]]:
    """Render synthetic, explicitly non-deployable values without accessing a cluster."""
    command = [
        "template",
        "synthetic-benchmark",
        str(CHART),
        "--namespace",
        "perf-generators",
        "--values",
        str(VALUES),
    ]
    for value in overrides:
        command.extend(["--set-string", value])
    content = deployment.helm(*command, succeeds=succeeds)
    return list(yaml.safe_load_all(content)) if succeeds else []


def validate_objects(objects: Sequence[Mapping[str, Any]]) -> None:
    """Prove exact write permissions, token isolation, resource bounds and externally owned inputs."""
    expected = {"ServiceAccount", "ClusterRole", "ClusterRoleBinding", "Role", "RoleBinding", "Job"}
    require(
        len(objects) == len(expected) and {value["kind"] for value in objects} == expected,
        "unexpected resource inventory",
    )
    by_kind = {value["kind"]: value for value in objects}
    job = by_kind["Job"]
    namespace = "perfeng-benchmark-" + job["metadata"]["labels"]["perfeng.io/run-id"]
    role = by_kind["Role"]
    require(role["metadata"]["namespace"] == namespace, "write role must be per-Run")
    require(
        role["rules"]
        == [
            {"apiGroups": [""], "resources": ["pods"], "verbs": ["create"]},
            {
                "apiGroups": [""],
                "resources": ["resourcequotas"],
                "resourceNames": ["benchmark-budget"],
                "verbs": ["get"],
            },
        ],
        "runner may only create Pods inside its owned namespace",
    )
    require(
        by_kind["ClusterRole"]["rules"]
        == [
            {"apiGroups": [""], "resources": ["pods", "events"], "verbs": ["get", "list", "watch"]},
            {"apiGroups": [""], "resources": ["nodes"], "verbs": ["get", "list"]},
            {"apiGroups": ["metrics.k8s.io"], "resources": ["nodes"], "verbs": ["get", "list"]},
            {
                "apiGroups": [""],
                "resources": ["namespaces"],
                "resourceNames": ["kube-system", namespace],
                "verbs": ["get"],
            },
            {
                "nonResourceURLs": ["/api", "/api/*", "/apis", "/apis/*", "/version"],
                "verbs": ["get"],
            },
        ],
        "cluster privileges must be read-only and exclude Secrets",
    )
    for kind in ("RoleBinding", "ClusterRoleBinding"):
        binding = by_kind[kind]
        require(
            binding["subjects"]
            == [
                {
                    "kind": "ServiceAccount",
                    "name": job["metadata"]["name"],
                    "namespace": "perf-generators",
                }
            ],
            "binding must select only this executor",
        )
        require(
            binding["roleRef"]
            == {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role" if kind == "RoleBinding" else "ClusterRole",
                "name": job["metadata"]["name"],
            },
            "binding role must be exact",
        )
    spec = job["spec"]
    require(
        all(
            spec[key] == expected
            for key, expected in {
                "backoffLimit": 0,
                "completions": 1,
                "parallelism": 1,
                "activeDeadlineSeconds": 600,
            }.items()
        ),
        "Job retries or deadlines differ",
    )
    pod = spec["template"]["spec"]
    require(
        pod["restartPolicy"] == "Never"
        and pod["automountServiceAccountToken"] is False
        and pod["enableServiceLinks"] is False,
        "implicit credentials or restart behavior",
    )
    require(
        pod["nodeSelector"]
        == {
            "workload": "performance-generator",
            "kubernetes.io/os": "linux",
            "kubernetes.io/arch": "amd64",
        },
        "generator placement differs",
    )
    require(
        pod["securityContext"]
        == {
            "runAsNonRoot": True,
            "runAsUser": 65532,
            "runAsGroup": 65532,
            "fsGroup": 65532,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "Pod isolation differs",
    )
    require(
        by_kind["ServiceAccount"]["automountServiceAccountToken"] is False,
        "ServiceAccount must not automount",
    )
    require(
        len(pod["initContainers"]) == 1 and len(pod["containers"]) == 1,
        "unexpected executable containers",
    )
    runner, publisher = pod["initContainers"][0], pod["containers"][0]
    for container in (runner, publisher):
        require(
            container["image"] == runner["image"]
            and container["securityContext"]
            == {
                "allowPrivilegeEscalation": False,
                "readOnlyRootFilesystem": True,
                "capabilities": {"drop": ["ALL"]},
            },
            "container identity or isolation differs",
        )
        require(
            "command" not in container and set(container["resources"]) == {"requests", "limits"},
            "entrypoint or budgets missing",
        )
        for budget in container["resources"].values():
            require(
                set(budget) == {"cpu", "memory", "ephemeral-storage"},
                "resource budget is incomplete",
            )
        require(
            container["args"][1:4] == ["--request", "/inputs/request.json", "--request-sha256"]
            and len(container["args"]) == 5,
            "request binding differs",
        )
    require(
        runner["args"][0] == "run" and publisher["args"][0] == "publish",
        "runner/publisher phases differ",
    )
    require(
        runner["env"]
        == [
            {
                "name": "PERFENG_EXECUTOR_POD_UID",
                "valueFrom": {"fieldRef": {"fieldPath": "metadata.uid"}},
            }
        ],
        "runner must not receive storage credentials",
    )
    require(
        len(publisher["env"]) == 3
        and {value["name"] for value in publisher["env"]}
        == {"PERFENG_S3_ENDPOINT", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"},
        "publisher environment differs",
    )
    environment = {value["name"]: value for value in publisher["env"]}
    storage_secret = (
        environment["AWS_ACCESS_KEY_ID"].get("valueFrom", {}).get("secretKeyRef", {}).get("name")
    )
    require(
        bool(storage_secret)
        and all(
            environment[name]
            == {
                "name": name,
                "valueFrom": {"secretKeyRef": {"name": storage_secret, "key": key}},
            }
            for name, key in (
                ("AWS_ACCESS_KEY_ID", "access-key"),
                ("AWS_SECRET_ACCESS_KEY", "secret-key"),
            )
        ),
        "publisher credentials must reference access-key and secret-key in one external Secret",
    )
    for container in (runner, publisher):
        require("envFrom" not in container, "whole-Secret imports are forbidden")
    require(
        "api" in {mount["name"] for mount in runner["volumeMounts"]}
        and "api" not in {mount["name"] for mount in publisher["volumeMounts"]},
        "Kubernetes token must remain runner-only",
    )
    require(
        next(mount for mount in publisher["volumeMounts"] if mount["name"] == "results").get(
            "readOnly"
        )
        is True,
        "publisher must not alter capture bytes",
    )
    volumes = {volume["name"]: volume for volume in pod["volumes"]}
    require(
        set(volumes) == {"inputs", "api", "results", "runner-tmp", "publisher-tmp"},
        "unreviewed volume",
    )
    require(
        volumes["results"]["emptyDir"] == {"sizeLimit": "128Mi"}, "capture volume must be bounded"
    )
    require(
        all("hostPath" not in volume and "secret" not in volume for volume in pod["volumes"]),
        "unreviewed filesystem credentials",
    )


def validate() -> None:
    """Lint, render and reject dangerous overrides without promoting any runtime bundle."""
    definition = inputs.object_json(inputs.read(inputs.PACKAGE / "workload.json"))
    contracts.validate("workload/v1/workload.schema.json", definition)
    require(
        definition["configuration"]["sha256"]
        == inputs.digest(inputs.read(inputs.PACKAGE / "config.yml")),
        "workload checksum differs",
    )
    require(
        inputs.digest(inputs.read(inputs.PACKAGE / "profile.json")) == inputs.PROFILE_SHA256,
        "profile snapshot differs",
    )
    config = yaml.safe_load(inputs.read(inputs.PACKAGE / "config.yml"))
    job = config["jobs"][0]
    require(
        len(config["jobs"]) == 1
        and job["jobIterations"] == 10
        and job["qps"] == 2
        and job["burst"] == 2,
        "workload iteration/rate budget differs",
    )
    require(
        config["global"]["gc"] is False
        and all(
            job[key] is False for key in ("cleanup", "gc", "preLoadImages", "namespacedIterations")
        ),
        "namespace/preload/cleanup operations must remain disabled",
    )
    require(
        job["objects"] == [{"objectTemplate": "pod.yml", "replicas": 1}]
        and job["namespace"] == "__TARGET_NAMESPACE__",
        "unreviewed object input",
    )
    require(
        config["metricsEndpoints"]
        == [
            {
                "alias": "local-results",
                "indexer": {"type": "local", "metricsDirectory": "__METRICS_DIRECTORY__"},
            }
        ],
        "measurements must remain local",
    )
    require("hooks" not in config["global"] and "hooks" not in job, "runtime hooks are forbidden")
    pod = yaml.safe_load(
        inputs.read(inputs.PACKAGE / "pod.yml").decode().replace("{{.Iteration}}", "0")
    )
    require(
        pod["kind"] == "Pod" and pod["metadata"]["namespace"] == "__TARGET_NAMESPACE__",
        "explicit Pod namespace is required",
    )
    spec = pod["spec"]
    require(
        set(spec)
        == {
            "automountServiceAccountToken",
            "enableServiceLinks",
            "restartPolicy",
            "terminationGracePeriodSeconds",
            "nodeSelector",
            "securityContext",
            "containers",
        },
        "unexpected benchmark Pod capability",
    )
    require(
        spec["automountServiceAccountToken"] is False
        and spec["enableServiceLinks"] is False
        and spec["restartPolicy"] == "Never",
        "benchmark Pod credentials/restarts differ",
    )
    require(
        spec["nodeSelector"]
        == {"workload": "sut", "kubernetes.io/os": "linux", "kubernetes.io/arch": "amd64"},
        "benchmark placement differs",
    )
    require(
        spec["securityContext"]
        == {
            "runAsNonRoot": True,
            "runAsUser": 65532,
            "runAsGroup": 65532,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "benchmark identity differs",
    )
    require(len(spec["containers"]) == 1, "benchmark must use one candidate container")
    container = spec["containers"][0]
    require(
        set(container) == {"name", "image", "imagePullPolicy", "securityContext", "resources"}
        and container["image"] == inputs.CANDIDATE
        and container["imagePullPolicy"] == "Never",
        "candidate/command identity differs",
    )
    require(
        container["securityContext"]
        == {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
        },
        "benchmark container isolation differs",
    )
    require(
        container["resources"]
        == {
            "requests": {"cpu": "1m", "memory": "1Mi", "ephemeral-storage": "64Ki"},
            "limits": {"cpu": "10m", "memory": "16Mi", "ephemeral-storage": "1Mi"},
        },
        "benchmark resource budget differs",
    )
    deployment.helm(
        "lint", str(CHART), "--strict", "--values", str(VALUES), "--namespace", "perf-generators"
    )
    validate_objects(render())
    for override in (
        "image=unsafe:latest",
        "targetNamespace=perf-platform",
        "requestSha256=wrong",
        "s3Endpoint=http://unreviewed.example",
        "extraOverride=true",
    ):
        render(override, succeeds=False)
