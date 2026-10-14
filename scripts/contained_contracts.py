"""Offline contracts for the new contained path, without rewriting the legacy snapshot."""

import hashlib
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry

from scripts import contracts

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "contracts/contained"
REVISION = "3b86afa18b468d831c7c2c176618180db18b2764"
VERSION = "0.22.0"


def validators() -> dict[str, Draft202012Validator]:
    """Verify exact vendored bytes and disable schema retrieval outside this snapshot."""
    lock = contracts.parse_json((SNAPSHOT / "lock.json").read_bytes())
    if (
        lock["commit"] != REVISION
        or lock["version"] != VERSION
        or set(lock["files"])
        != {
            "artifact-reference.schema.json",
            "environment.schema.json",
            "kubernetes-benchmark-evidence.schema.json",
            "raw-result.schema.json",
        }
    ):
        raise ValueError("Contained contract snapshot identity differs")
    result = {}
    for name, digest in lock["files"].items():
        content = (SNAPSHOT / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("Contained contract snapshot checksum differs")
        schema = contracts.parse_json(content)
        Draft202012Validator.check_schema(schema)
        result[name] = Draft202012Validator(
            schema, registry=Registry(retrieve=contracts.no_network), format_checker=FormatChecker()
        )
    return result


VALIDATORS = validators()


def validate(name: str, value: Any) -> None:
    """Validate the owned boundary without fetching remote schemas."""
    VALIDATORS[f"{name}.schema.json"].validate(value)
