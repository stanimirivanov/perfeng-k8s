"""Preview or execute repository-owned Kubernetes benchmarks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from scripts import contracts, validate

MAXIMUM_DOWNLOAD_BYTES = 200 * 1024 * 1024
RUN_ID_PATTERN = re.compile(r"^perf-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}$")
CONTEXT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,252}$")
BENCHMARK_NAMESPACE = "perfeng-pod-startup"


class BenchmarkError(RuntimeError):
    """Benchmark preparation or execution could not complete safely."""


@dataclass(frozen=True)
class ToolAsset:
    """A checksum-pinned kube-burner distribution for one host platform."""

    version: str
    url: str
    archive_sha256: str
    executable_sha256: str
    archive_kind: str
    executable_name: str


@dataclass(frozen=True)
class RunPlan:
    """Validated inputs for one explicit pod-startup execution."""

    kubeconfig: Path
    context: str
    run_id: str
    output: Path
    tool: ToolAsset


def sha256_file(path: Path) -> str:
    """Hash a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def host_asset() -> ToolAsset:
    """Resolve the reviewed kube-burner asset for this host."""
    release = validate.load_json(validate.RELEASE_PATH)
    version = release["version"]
    if not isinstance(version, str):
        raise BenchmarkError("Pinned kube-burner version is invalid")

    system = platform.system()
    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64"}:
        raise BenchmarkError("Only AMD64 benchmark hosts are currently reviewed")
    if system != "Linux":
        raise BenchmarkError("Only Linux benchmark hosts are supported")
    key, archive_kind, executable_name = "linux-amd64", "tar", "kube-burner"

    assets = validate.mapping(release["assets"], "kube-burner assets")
    asset = validate.mapping(assets[key], f"kube-burner asset {key}")
    return ToolAsset(
        version=version,
        url=str(asset["url"]),
        archive_sha256=str(asset["sha256"]),
        executable_sha256=str(asset["executableSha256"]),
        archive_kind=archive_kind,
        executable_name=executable_name,
    )


def validated_plan(args: argparse.Namespace) -> RunPlan:
    """Validate caller-controlled paths and target identity."""
    validate.validate()
    kubeconfig = Path(args.kubeconfig).expanduser().resolve()
    if not kubeconfig.is_file():
        raise BenchmarkError("Kubeconfig must identify an existing file")
    if not isinstance(args.context, str) or CONTEXT_PATTERN.fullmatch(args.context) is None:
        raise BenchmarkError("Context has an invalid form")
    if not isinstance(args.run_id, str) or RUN_ID_PATTERN.fullmatch(args.run_id) is None:
        raise BenchmarkError("Run ID must use perf-YYYYMMDD-HHMMSS-xxxxxxxx form")

    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise BenchmarkError("Output directory must not already exist")
    repository_local = validate.ROOT / ".local"
    if output.is_relative_to(validate.ROOT) and not output.is_relative_to(repository_local):
        raise BenchmarkError("Repository-local output must be placed under .local")

    if args.execute and args.confirm_context != args.context:
        raise BenchmarkError("Execution requires --confirm-context to exactly match --context")
    return RunPlan(kubeconfig, args.context, args.run_id, output, host_asset())


def download(url: str, destination: Path) -> str:
    """Download a bounded archive and return its SHA-256."""
    digest = hashlib.sha256()
    total = 0
    try:
        with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as target:
            declared = response.headers.get("Content-Length")
            if declared is not None and int(declared) > MAXIMUM_DOWNLOAD_BYTES:
                raise BenchmarkError("Pinned tool archive exceeds the download limit")
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAXIMUM_DOWNLOAD_BYTES:
                    raise BenchmarkError("Pinned tool archive exceeds the download limit")
                digest.update(chunk)
                target.write(chunk)
    except (OSError, ValueError, urllib.error.URLError) as error:
        raise BenchmarkError("Could not download the pinned kube-burner archive") from error
    return digest.hexdigest()


def copy_archive_member(source: IO[bytes], destination: Path) -> None:
    """Copy one bounded executable from a verified archive."""
    with destination.open("wb") as target:
        copied = 0
        while chunk := source.read(1024 * 1024):
            copied += len(chunk)
            if copied > MAXIMUM_DOWNLOAD_BYTES:
                raise BenchmarkError("Pinned executable exceeds the extraction limit")
            target.write(chunk)


def extract_executable(archive: Path, destination: Path, asset: ToolAsset) -> None:
    """Extract only the expected regular executable from the archive."""
    try:
        if asset.archive_kind == "zip":
            with zipfile.ZipFile(archive) as package:
                member = package.getinfo(asset.executable_name)
                if member.is_dir() or member.file_size > MAXIMUM_DOWNLOAD_BYTES:
                    raise BenchmarkError("Pinned archive executable is invalid")
                with package.open(member) as source:
                    copy_archive_member(source, destination)
        else:
            with tarfile.open(archive, mode="r:gz") as package:
                member = package.getmember(asset.executable_name)
                source = package.extractfile(member)
                if not member.isfile() or source is None or member.size > MAXIMUM_DOWNLOAD_BYTES:
                    raise BenchmarkError("Pinned archive executable is invalid")
                with source:
                    copy_archive_member(source, destination)
    except (KeyError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise BenchmarkError("Could not extract the pinned kube-burner executable") from error


def acquire_tool(asset: ToolAsset) -> Path:
    """Return a cached executable after verifying or securely installing it."""
    tool_directory = validate.ROOT / ".local" / "tools" / "kube-burner" / asset.version
    executable = tool_directory / asset.executable_name
    if executable.is_file() and sha256_file(executable) == asset.executable_sha256:
        return executable

    tool_directory.mkdir(parents=True, exist_ok=True)
    print(f"Downloading kube-burner {asset.version}...", flush=True)
    archive_handle, archive_name = tempfile.mkstemp(prefix="download-", dir=tool_directory)
    os.close(archive_handle)
    executable_handle, executable_name = tempfile.mkstemp(prefix="executable-", dir=tool_directory)
    os.close(executable_handle)
    archive, candidate = Path(archive_name), Path(executable_name)
    try:
        if download(asset.url, archive) != asset.archive_sha256:
            raise BenchmarkError("Downloaded kube-burner archive checksum does not match")
        extract_executable(archive, candidate, asset)
        if sha256_file(candidate) != asset.executable_sha256:
            raise BenchmarkError("Extracted kube-burner executable checksum does not match")
        candidate.chmod(0o755)
        candidate.replace(executable)
    finally:
        archive.unlink(missing_ok=True)
        candidate.unlink(missing_ok=True)
    return executable


def kubectl_command(plan: RunPlan, *arguments: str) -> list[str]:
    """Build a command bound to the exact caller-approved cluster context."""
    kubectl = shutil.which("kubectl")
    if kubectl is None:
        raise BenchmarkError("kubectl is required for target and cleanup verification")
    return [
        kubectl,
        "--kubeconfig",
        str(plan.kubeconfig),
        "--context",
        plan.context,
        *arguments,
    ]


def verify_context(plan: RunPlan) -> None:
    """Require the named context to exist and its cluster to be reachable."""
    result = subprocess.run(
        kubectl_command(plan, "get", "nodes", "-o", "name"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise BenchmarkError("The confirmed Kubernetes context is unavailable or has no nodes")


def namespace_removed(plan: RunPlan) -> bool:
    """Report whether kube-burner removed its owned namespace."""
    result = subprocess.run(
        kubectl_command(
            plan,
            "get",
            "namespace",
            BENCHMARK_NAMESPACE,
            "-o",
            "name",
            "--ignore-not-found",
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode == 0 and not result.stdout.strip()


def benchmark_command(plan: RunPlan, executable: Path) -> list[str]:
    """Build the pinned kube-burner command for a validated plan."""
    return [
        str(executable),
        "init",
        "--config",
        str(validate.WORKLOAD_ROOT / "config.yml"),
        "--uuid",
        plan.run_id,
        "--kubeconfig",
        str(plan.kubeconfig),
        "--kube-context",
        plan.context,
        "--timeout",
        "5m",
        "--skip-log-file",
    ]


def terminal_text(value: str, encoding: str | None) -> str:
    """Replace characters unsupported by the active terminal encoding."""
    if encoding is None:
        return value
    return value.encode(encoding, errors="replace").decode(encoding)


def stream(command: Sequence[str], cwd: Path, environment: Mapping[str, str], log: Path) -> int:
    """Run a command while mirroring merged output to the terminal and a file."""
    with log.open("w", encoding="utf-8", newline="\n") as output:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as error:
            raise BenchmarkError("Could not start the pinned kube-burner executable") from error
        if process.stdout is None:
            raise BenchmarkError("Could not capture kube-burner output")
        for line in process.stdout:
            print(terminal_text(line, sys.stdout.encoding), end="", flush=True)
            output.write(line)
        return process.wait()


def artifact(path: Path, root: Path) -> dict[str, Any]:
    """Describe an immutable local result artifact."""
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "sizeBytes": path.stat().st_size,
    }


def execute(plan: RunPlan) -> int:
    """Execute one confirmed benchmark and write its local receipt."""
    print(f"Verifying Kubernetes context {plan.context}...", flush=True)
    verify_context(plan)
    executable = acquire_tool(plan.tool)
    plan.output.mkdir(parents=True)
    started = datetime.now(UTC)
    command = benchmark_command(plan, executable)
    environment = {**os.environ, "METRICS_DIRECTORY": plan.output.as_posix()}
    print(f"Running {plan.run_id} against {plan.context}...", flush=True)
    return_code = stream(command, validate.WORKLOAD_ROOT, environment, plan.output / "runner.log")
    cleaned = namespace_removed(plan)
    measurement_files = [
        path
        for path in sorted(plan.output.rglob("*.json"))
        if path.name != "execution.json" and path.stat().st_size > 0
    ]
    receipt = {
        "schemaVersion": 1,
        "kind": "KubernetesBenchmarkExecution",
        "contractsVersion": contracts.VERSION,
        "runId": plan.run_id,
        "benchmark": "pod-startup",
        "context": plan.context,
        "startedAt": started.isoformat().replace("+00:00", "Z"),
        "completedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "exitCode": return_code,
        "namespaceRemoved": cleaned,
        "tool": {
            "name": "kube-burner",
            "version": plan.tool.version,
            "artifact": {
                "kind": "release-archive",
                "url": plan.tool.url,
                "archiveSha256": plan.tool.archive_sha256,
                "executableSha256": plan.tool.executable_sha256,
            },
        },
        "workload": {
            "file": validate.WORKLOAD_DEFINITION.relative_to(validate.ROOT).as_posix(),
            "id": "pod-startup-smoke",
            "version": "1.0.0",
            "sha256": sha256_file(validate.WORKLOAD_DEFINITION),
        },
        "inputs": {
            "configSha256": sha256_file(validate.WORKLOAD_ROOT / "config.yml"),
            "templateSha256": sha256_file(validate.WORKLOAD_ROOT / "templates" / "pod.yml"),
            "containerImage": validate.EXPECTED_IMAGE,
        },
        "log": artifact(plan.output / "runner.log", plan.output),
        "measurements": [artifact(path, plan.output) for path in measurement_files],
    }
    (plan.output / "execution.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if return_code != 0:
        raise BenchmarkError(f"kube-burner failed with exit code {return_code}")
    if not cleaned:
        raise BenchmarkError("Benchmark namespace remains; inspect it before cleanup")
    if not measurement_files:
        raise BenchmarkError("Benchmark produced no non-empty JSON measurement files")
    print(f"Benchmark completed; results: {plan.output}")
    return 0


def parser() -> argparse.ArgumentParser:
    """Build the command-line contract."""
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("benchmark", choices=["pod-startup"])
    value.add_argument("--kubeconfig", required=True)
    value.add_argument("--context", required=True)
    value.add_argument("--run-id", required=True)
    value.add_argument("--output", required=True)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--confirm-context")
    return value


def main(arguments: Sequence[str] | None = None) -> int:
    """Preview by default and execute only after exact context confirmation."""
    try:
        args = parser().parse_args(arguments)
        plan = validated_plan(args)
        if not args.execute:
            print("Benchmark preview; no tool download or cluster access was performed.")
            print(f"Benchmark: pod-startup\nContext: {plan.context}\nRun ID: {plan.run_id}")
            print(f"Output: {plan.output}")
            print("Add --execute and --confirm-context with the exact context to run it.")
            return 0
        return execute(plan)
    except (BenchmarkError, validate.ValidationError) as error:
        print(f"Kubernetes benchmark error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
