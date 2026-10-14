"""Supervise the packaged upstream executable and atomically mark a complete frozen capture."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from scripts import contained_observation as observation
from scripts import evidence
from scripts.contained_inputs import (
    FILES,
    Request,
    digest,
    encode,
    read,
    resolve,
    resolved_document,
)

EXECUTABLE = Path("/usr/local/bin/kube-burner")
EXECUTABLE_SHA256 = "108da35bf5458788c9f6759c4ce0b060a114a00ad916a51f510957f971f39e0c"
MAXIMUM_SECONDS = 300
SAMPLE_SECONDS = 5
MAXIMUM_GAP_SECONDS = 30


def create(path: Path, content: bytes) -> None:
    """Retain local bytes create-only; the completion marker is published atomically separately."""
    with path.open("xb") as target:
        target.write(content)


def stop(process: subprocess.Popen) -> None:
    """Reap only the process group we created; do not mutate any Kubernetes resources."""
    if process.poll() is None:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)


def run(request: Request, output: Path, api: observation.ObservationAPI, executor_uid: str) -> None:
    """Require valid initial observations, bound the process and preserve later FAIL/UNKNOWN evidence."""
    with EXECUTABLE.open("rb") as binary:
        executable_sha256 = hashlib.file_digest(binary, "sha256").hexdigest()
    if not executor_uid or executable_sha256 != EXECUTABLE_SHA256:
        raise ValueError("Executor identity or packaged executable checksum differs")
    output = output.absolute()
    if output.is_symlink() or output.is_junction() or output.resolve() != output:
        raise ValueError("Redirected capture directory is forbidden")
    output.mkdir(exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Capture directory must be empty")
    observation.guard(api, request, empty=True)
    started = observation.now()
    nodes, samples, checks = observation.sample(api, request, executor_uid)
    initial = observation.evidence(request, nodes, samples, checks, started, observation.now())
    create(output / "initial-qualification.json", encode(initial))
    if any(status != "PASS" for status in checks.values()):
        raise ValueError("Initial qualification failed or is unknown; no benchmark launched")
    resolved = resolve(request, output)
    for name, text in resolved.items():
        create(output / name, text.encode())
    create(
        output / "resolved-inputs.json",
        encode(resolved_document(request, output)),
    )
    command = [
        str(EXECUTABLE),
        "init",
        "--config",
        str(output / "config.yml"),
        "--uuid",
        request.run_id,
        "--timeout",
        "4m",
        "--skip-log-file",
    ]
    # No ambient AWS credentials, kubeconfig, tool templating variables or proxy configuration.
    environment = {
        key: os.environ[key]
        for key in ("PATH", "KUBERNETES_SERVICE_HOST", "KUBERNETES_SERVICE_PORT")
        if key in os.environ
    }
    environment["HOME"] = "/tmp"
    deadline = time.monotonic() + MAXIMUM_SECONDS
    previous_sample = time.monotonic()
    with (output / "runner.log").open("xb") as log:
        log.write(b"Starting packaged kube-burner 2.8.5 with verified contained inputs.\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=output,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=os.name == "posix",
        )
        previous_handler = signal.getsignal(signal.SIGTERM)

        def interrupted(signum, frame):
            raise InterruptedError("Contained execution interrupted")

        signal.signal(signal.SIGTERM, interrupted)
        try:
            while True:
                if (
                    time.monotonic() >= deadline
                    or (output / "runner.log").stat().st_size > 1024 * 1024
                ):
                    raise ValueError("Benchmark deadline or log bound exceeded")
                current_nodes, current_samples, current_checks = observation.sample(
                    api, request, executor_uid
                )
                if current_nodes != nodes:
                    raise ValueError("Stable node inventory changed during measurement")
                current_time = time.monotonic()
                if (
                    current_time - previous_sample > MAXIMUM_GAP_SECONDS
                    and current_checks["interference"] != "FAIL"
                ):
                    current_checks["interference"] = "UNKNOWN"
                previous_sample = current_time
                samples.extend(current_samples)
                print(
                    f"Collected {len(samples)} node samples; process still supervised.", flush=True
                )
                if len(samples) > 4096:
                    raise ValueError("Sample bound exceeded; no truncation permitted")
                for key, status in current_checks.items():
                    if status == "FAIL" or (status == "UNKNOWN" and checks[key] != "FAIL"):
                        checks[key] = status
                if process.poll() is not None:
                    break
                time.sleep(min(SAMPLE_SECONDS, max(0, deadline - time.monotonic())))
            if process.returncode != 0:
                raise ValueError("kube-burner did not complete successfully")
        finally:
            signal.signal(signal.SIGTERM, previous_handler)
            stop(process)
    completed = observation.now()
    qualification = observation.evidence(request, nodes, samples, checks, started, completed)
    create(output / "qualification.json", encode(qualification))
    for name in evidence.ARTIFACT_TYPES:
        evidence.validate_payload(name, read(output / name), request.run_id)
    descriptors = {
        name: {"sha256": digest(read(output / name)), "sizeBytes": len(read(output / name))}
        for name in FILES
    }
    receipt: dict[str, Any] = {
        "schemaVersion": 1,
        "kind": "ContainedKubernetesExecution",
        "runId": request.run_id,
        "requestSha256": request.sha256,
        "exitCode": 0,
        "startedAt": observation.stamp(started),
        "completedAt": observation.stamp(completed),
        "artifacts": descriptors,
    }
    temporary = output / ".complete"
    create(temporary, encode(receipt))
    try:
        os.link(temporary, output / "complete.json")
    finally:
        temporary.unlink()
