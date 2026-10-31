from __future__ import annotations

import argparse
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import benchmark

RUN_ID = "perf-20260908-120000-a1b2c3d4"


class BenchmarkCommandTests(unittest.TestCase):
    def test_windows_host_is_rejected_before_download(self) -> None:
        with (
            patch.object(benchmark.platform, "system", return_value="Windows"),
            patch.object(benchmark.platform, "machine", return_value="AMD64"),
        ):
            with self.assertRaisesRegex(benchmark.BenchmarkError, "Only Linux"):
                benchmark.host_asset()

    def test_terminal_output_replaces_unsupported_unicode(self) -> None:
        self.assertEqual(
            benchmark.terminal_text("Writing results 📁\n", "cp1252"),
            "Writing results ?\n",
        )

    def test_preview_does_not_acquire_tool_or_contact_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kubeconfig = root / "config"
            kubeconfig.write_text("fixture", encoding="utf-8")
            output = root / "results"
            stdout = io.StringIO()
            with (
                patch.object(benchmark, "acquire_tool") as acquire,
                patch.object(benchmark, "verify_context") as verify,
                redirect_stdout(stdout),
            ):
                result = benchmark.main(
                    [
                        "pod-startup",
                        "--kubeconfig",
                        str(kubeconfig),
                        "--context",
                        "kind-perfeng-local",
                        "--run-id",
                        RUN_ID,
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(result, 0)
            self.assertIn("no tool download or cluster access", stdout.getvalue())
            acquire.assert_not_called()
            verify.assert_not_called()
            self.assertFalse(output.exists())

    def test_execution_requires_exact_context_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kubeconfig = root / "config"
            kubeconfig.write_text("fixture", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                result = benchmark.main(
                    [
                        "pod-startup",
                        "--kubeconfig",
                        str(kubeconfig),
                        "--context",
                        "kind-perfeng-local",
                        "--run-id",
                        RUN_ID,
                        "--output",
                        str(root / "results"),
                        "--execute",
                        "--confirm-context",
                        "other-context",
                    ]
                )

            self.assertEqual(result, 1)
            self.assertIn("exactly match", stderr.getvalue())

    def test_cached_executable_is_verified_before_reuse(self) -> None:
        content = b"verified executable"
        digest = hashlib.sha256(content).hexdigest()
        asset = benchmark.ToolAsset(
            version="1.0.0",
            url="https://example.invalid/tool.zip",
            archive_sha256="a" * 64,
            executable_sha256=digest,
            archive_kind="zip",
            executable_name="kube-burner",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / ".local" / "tools" / "kube-burner" / "1.0.0" / asset.executable_name
            executable.parent.mkdir(parents=True)
            executable.write_bytes(content)
            with (
                patch.object(benchmark.validate, "ROOT", root),
                patch.object(benchmark, "download") as download,
            ):
                resolved = benchmark.acquire_tool(asset)

            self.assertEqual(resolved, executable)
            download.assert_not_called()

    def test_repository_output_outside_local_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            kubeconfig = Path(directory) / "config"
            kubeconfig.write_text("fixture", encoding="utf-8")
            args = argparse.Namespace(
                kubeconfig=str(kubeconfig),
                context="kind-perfeng-local",
                run_id=RUN_ID,
                output=str(benchmark.validate.ROOT / "results"),
                execute=False,
                confirm_context=None,
            )
            with self.assertRaisesRegex(benchmark.BenchmarkError, "under .local"):
                benchmark.validated_plan(args)

    def test_execution_injects_a_yaml_safe_output_path(self) -> None:
        plan = benchmark.RunPlan(
            kubeconfig=Path("config"),
            context="kind-perfeng-local",
            run_id=RUN_ID,
            output=Path("C:/benchmark results/run-01"),
            tool=benchmark.ToolAsset("1.0.0", "url", "a" * 64, "b" * 64, "zip", "tool"),
        )
        with (
            patch.object(benchmark, "verify_context"),
            patch.object(benchmark, "acquire_tool", return_value=Path("tool")),
            patch.object(benchmark, "stream", return_value=1) as stream,
            patch.object(benchmark, "namespace_removed", return_value=True),
            patch.object(benchmark, "artifact", return_value={}),
            patch.object(Path, "mkdir"),
            patch.object(Path, "write_text"),
            redirect_stdout(io.StringIO()),
            self.assertRaisesRegex(benchmark.BenchmarkError, "exit code 1"),
        ):
            benchmark.execute(plan)

        environment = stream.call_args.args[2]
        self.assertEqual(environment["METRICS_DIRECTORY"], "C:/benchmark results/run-01")

    def test_success_receipt_pins_contract_workload_and_release_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            plan = benchmark.RunPlan(
                kubeconfig=Path("config"),
                context="kind-perfeng-local",
                run_id=RUN_ID,
                output=output,
                tool=benchmark.host_asset(),
            )

            def write_capture(_command, _cwd, _environment, log: Path) -> int:
                log.write_text("completed\n", encoding="utf-8")
                for name in (
                    "jobSummary.json",
                    "podLatencyMeasurement-pod-startup-smoke.json",
                    "podLatencyQuantilesMeasurement-pod-startup-smoke.json",
                ):
                    (output / name).write_text("[]\n", encoding="utf-8")
                return 0

            with (
                patch.object(benchmark, "verify_context"),
                patch.object(benchmark, "acquire_tool", return_value=Path("tool")),
                patch.object(benchmark, "stream", side_effect=write_capture),
                patch.object(benchmark, "namespace_removed", return_value=True),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(benchmark.execute(plan), 0)

            receipt = json.loads((output / "execution.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["contractsVersion"], "0.13.0")
            self.assertEqual(receipt["workload"]["id"], "pod-startup-smoke")
            self.assertEqual(
                receipt["tool"]["artifact"],
                {
                    "kind": "release-archive",
                    "url": plan.tool.url,
                    "archiveSha256": plan.tool.archive_sha256,
                    "executableSha256": plan.tool.executable_sha256,
                },
            )


if __name__ == "__main__":
    unittest.main()
