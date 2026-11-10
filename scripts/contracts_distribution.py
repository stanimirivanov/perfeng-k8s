"""Compare both k8s snapshots to independently signed historical profiles offline."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
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


def write_snapshot(target: Path, primary: dict[str, bytes], contained: dict[str, bytes]) -> None:
    """Prepare both families together under a fresh operator-owned directory."""
    for path in (*primary, *contained):
        parts = PurePosixPath(path).parts
        if not parts or any(part in {"/", "..", "contained"} for part in parts):
            raise ValueError("Invalid contract staging destination")
    files = {**primary, **{f"contained/{name}": data for name, data in contained.items()}}
    target.mkdir(mode=0o700)
    try:
        for name, data in files.items():
            output = target / name
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as stream:
                stream.write(data)
    except BaseException:
        shutil.rmtree(target)
        raise


def stage_family(
    tool: Path,
    scratch: Path,
    family: str,
    revision: str,
    snapshot: Path,
    verified: dict[str, str],
    inputs: list[str],
    ledger_digest: str,
) -> dict[str, bytes]:
    """Materialize the complete closure privately and return only reviewed destinations."""
    source_paths = (
        CONTAINED_SOURCES
        if family == "contained"
        else {name: name for name in contracts.EXPECTED_FILES}
    )
    destinations = {source: f"snapshot/{name}" for name, source in source_paths.items()}
    selection = scratch / f"{family}-selection.json"
    selection.write_text(
        json.dumps(
            {
                "sourceRevision": revision,
                "members": {
                    source: {
                        "sha256": sha,
                        "destination": destinations.get(source, f"closure/{source}"),
                    }
                    for source, sha in verified.items()
                },
            }
        ),
        encoding="utf-8",
    )
    store = scratch / f"{family}-store"
    store.mkdir(mode=0o700)
    result = subprocess.run(
        [
            str(tool / "runtime/bin/python3.12"),
            "-IB",
            str(tool / "materialize.py"),
            *inputs,
            "--selection",
            str(selection),
            "--target",
            str(store),
            "--execute",
        ],
        cwd=scratch,
        env={},
        check=True,
        timeout=120,
        stdout=subprocess.PIPE,
    )
    pointer = (store / "current").read_bytes()
    if not re.fullmatch(rb"[a-f0-9]{64}\n", pointer):
        raise ValueError("Invalid materializer generation")
    generation = store / pointer[:-1].decode("ascii")
    if result.stdout != f"{generation}\n".encode():
        raise ValueError("Materializer output disagrees with its generation")
    files = {
        name: (generation / destinations[source]).read_bytes()
        for name, source in source_paths.items()
    }
    for name, source in source_paths.items():
        if hashlib.sha256(files[name]).hexdigest() != verified[source]:
            raise ValueError(f"Prepared schema bytes differ: {name}")
    ledger = (snapshot / "lock.json").read_bytes()
    if hashlib.sha256(ledger).hexdigest() != ledger_digest:
        raise ValueError("Snapshot ledger differs from the reviewed distribution pin")
    return {**files, "lock.json": ledger}


def shadow(
    assets: Path,
    bootstrap: Path,
    verifier: Path,
    *,
    target: Path | None = None,
    rollback: Path | None = None,
) -> dict[str, Any]:
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
        staged = {}
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
            inputs = [
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
            ]
            result = subprocess.run(
                [
                    str(tool / "runtime/bin/python3.12"),
                    "-IB",
                    "-c",
                    "import sys; sys.path.insert(0, sys.argv.pop(1)); "
                    "from scripts.contracts_inspect import main; sys.exit(main())",
                    str(tool),
                    *inputs,
                ],
                cwd=scratch,
                env={},
                check=True,
                timeout=60,
                stdout=subprocess.PIPE,
            )
            verified = contracts.parse_json(result.stdout)
            families[family] = {
                "sourceRevision": revision,
                "manifestSha256": manifest_digest,
                "members": compare(
                    snapshot,
                    revision,
                    verified,
                    contained=family == "contained",
                ),
            }
            if target is not None:
                staged[family] = stage_family(
                    tool,
                    scratch,
                    family,
                    revision,
                    snapshot,
                    verified,
                    inputs,
                    lock["snapshotLedgers"][family],
                )
            if rollback is not None:
                retained = rollback / snapshot.relative_to(ROOT)
                compare(retained, revision, verified, contained=family == "contained")
                if (
                    hashlib.sha256((retained / "lock.json").read_bytes()).hexdigest()
                    != (lock["snapshotLedgers"][family])
                ):
                    raise ValueError("Retained rollback ledger differs from the reviewed pin")
        if target is not None:
            write_snapshot(target, staged["primary"], staged["contained"])
    return {
        "status": "passed",
        "historyRelease": lock["historyRelease"],
        "toolRelease": lock["toolRelease"],
        "toolArchiveSha256": lock["tool"]["archiveSha256"],
        "families": families,
        **({"prepared": True} if target is not None else {}),
        **({"rollbackScope": "distribution-path; same revisions"} if rollback is not None else {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("assets", "bootstrap", "verifier"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--rollback", type=Path)
    args = parser.parse_args()
    if args.rollback is not None and args.target is None:
        parser.error("--rollback requires a fresh --target for cold restoration")
    try:
        print(
            json.dumps(
                shadow(
                    args.assets,
                    args.bootstrap,
                    args.verifier,
                    target=args.target,
                    rollback=args.rollback,
                ),
                indent=2,
            )
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"contracts-shadow: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
