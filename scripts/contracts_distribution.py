"""Compare both k8s snapshots to independently signed historical profiles offline."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from scripts import contained_contracts, contracts

ROOT = contracts.CONTRACTS.parent
LOCK = ROOT / "contracts/distribution.lock.json"
CONTAINED_SOURCES = {
    "artifact-reference.schema.json": "schemas/artifact/v1/artifact-reference.schema.json",
    "environment.schema.json": "schemas/environment/v1/environment.schema.json",
    "kubernetes-benchmark-evidence.schema.json": (
        "schemas/kubernetes-benchmark-evidence/v1/kubernetes-benchmark-evidence.schema.json"
    ),
    "raw-result.schema.json": "schemas/raw-result/v2/raw-result.schema.json",
}


def compare(
    snapshot: Path, revision: str, members: dict[str, str], *, contained: bool = False
) -> dict[str, str]:
    """Require one family's exact revision, path selection, and schema digests."""
    ledger = contracts.parse_json((snapshot / "lock.json").read_bytes())
    expected_revision, version, paths = (
        (contained_contracts.REVISION, contained_contracts.VERSION, CONTAINED_SOURCES)
        if contained
        else (
            contracts.EXPECTED_COMMIT,
            contracts.VERSION,
            {name: name for name in contracts.EXPECTED_FILES},
        )
    )
    if (revision, ledger["commit"], ledger["version"]) != (
        expected_revision,
        expected_revision,
        version,
    ):
        raise ValueError("Contract family revision or version mismatch")
    files = ledger["files"]
    if files.keys() != paths.keys():
        raise ValueError("Contract family member selection mismatch")
    for name, digest in files.items():
        if members.get(paths[name]) != digest:
            raise ValueError(f"Missing or different signed member: {name}")
        if hashlib.sha256((snapshot / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Different snapshot bytes: {name}")
    return files


def shadow(assets: Path, bootstrap: Path, verifier: Path) -> dict[str, Any]:
    """Restore the pinned tool and require both complete signed profiles before passing."""
    if not all(path.is_absolute() for path in (assets, bootstrap, verifier)):
        raise ValueError("Assets, bootstrap, and verifier must use absolute paths")
    lock = contracts.parse_json(LOCK.read_bytes())
    with tempfile.TemporaryDirectory(prefix="perfeng-k8s-contracts-") as directory:
        scratch = Path(directory)
        tool, pins = scratch / "tool", scratch / "tool-pins.json"
        pins.write_text(json.dumps(lock["tool"]), encoding="utf-8")
        subprocess.run(
            [
                str(bootstrap / ".venv/bin/python"),
                "-IB",
                "-c",
                "import sys; sys.path.insert(0, sys.argv.pop(1)); "
                "from scripts.contracts_tool_release import main; sys.exit(main())",
                str(bootstrap),
                "restore",
                "--archive",
                str(assets / "tool/materializer.tar.gz"),
                "--bundle",
                str(assets / "tool/materializer.sigstore.jsonl"),
                "--verifier",
                str(verifier),
                "--pins",
                str(pins),
                "--target",
                str(tool),
            ],
            cwd=scratch,
            env={},
            check=True,
            timeout=120,
            stdout=subprocess.DEVNULL,
        )
        families = {}
        history = assets / "history"
        for family, revision, snapshot in (
            ("primary", contracts.EXPECTED_COMMIT, contracts.CONTRACTS),
            ("contained", contained_contracts.REVISION, contained_contracts.SNAPSHOT),
        ):
            policy = scratch / f"{family}.json"
            manifest_digest = lock["manifests"][family]
            policy.write_text(
                json.dumps({**lock["publisher"], "manifestSha256": manifest_digest}),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(tool / "runtime/bin/python3.12"),
                    "-IB",
                    "-c",
                    "import sys; sys.path.insert(0, sys.argv.pop(1)); "
                    "from scripts.contracts_inspect import main; sys.exit(main())",
                    str(tool),
                    "--manifest",
                    str(history / f"{revision}.manifest.json"),
                    "--archive",
                    str(history / f"{revision}.tar.gz"),
                    "--bundle",
                    str(history / "manifest.sigstore.jsonl"),
                    "--policy",
                    str(policy),
                    "--verifier",
                    str(verifier),
                ],
                cwd=scratch,
                env={},
                check=True,
                timeout=60,
                stdout=subprocess.PIPE,
            )
            families[family] = {
                "sourceRevision": revision,
                "manifestSha256": manifest_digest,
                "members": compare(
                    snapshot,
                    revision,
                    contracts.parse_json(result.stdout),
                    contained=family == "contained",
                ),
            }
    return {
        "status": "passed",
        "historyRelease": lock["historyRelease"],
        "toolRelease": lock["toolRelease"],
        "toolArchiveSha256": lock["tool"]["archiveSha256"],
        "families": families,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("assets", "bootstrap", "verifier"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(shadow(args.assets, args.bootstrap, args.verifier), indent=2))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"contracts-shadow: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
