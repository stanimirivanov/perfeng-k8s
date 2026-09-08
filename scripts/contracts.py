"""Pinned offline contract validation for Kubernetes benchmark evidence."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Never

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
EXPECTED_COMMIT = "badd9206a88a48042dda54a25c6e362088d23858"
VERSION = "0.13.0"
EXPECTED_FILES = {
    "schemas/artifact/v1/artifact-reference.schema.json",
    "schemas/catalogue/v2/test-catalogue.schema.json",
    "schemas/raw-result/v2/raw-result.schema.json",
    "schemas/result/v1/test-result.schema.json",
    "schemas/workload/v1/workload.schema.json",
}


def reject_constant(value: str) -> Never:
    """Reject JSON constants outside the standard number grammar."""
    raise ValueError(f"Non-finite JSON value: {value}")


def finite_float(value: str) -> float:
    """Parse only finite JSON floating-point values."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build an object while rejecting duplicate field names."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def parse_json(data: bytes) -> Any:
    """Parse strict finite JSON with unique object fields."""
    return json.loads(
        data,
        parse_constant=reject_constant,
        parse_float=finite_float,
        object_pairs_hook=unique_object,
    )


def no_network(uri: str) -> Never:
    """Reject contract references absent from the reviewed local snapshot."""
    raise NoSuchResource(ref=uri)


def load_validators() -> dict[str, Draft202012Validator]:
    """Verify the snapshot and compile all schemas without network access."""
    lock = parse_json((CONTRACTS / "lock.json").read_bytes())
    if (
        not isinstance(lock, dict)
        or lock.get("commit") != EXPECTED_COMMIT
        or lock.get("version") != VERSION
    ):
        raise ValueError("Unexpected contract snapshot provenance")
    files = lock.get("files")
    if not isinstance(files, dict) or set(files) != EXPECTED_FILES:
        raise ValueError("Unexpected contract snapshot inventory")

    schemas: dict[str, Any] = {}
    for path, expected in files.items():
        if not isinstance(path, str) or not isinstance(expected, str):
            raise ValueError("Invalid contract snapshot lock")
        data = (CONTRACTS / path).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Vendored contract checksum mismatch: {path}")
        schema = parse_json(data)
        Draft202012Validator.check_schema(schema)
        schemas[path] = schema

    registry = Registry(retrieve=no_network).with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    return {
        path: Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
        for path, schema in schemas.items()
    }


VALIDATORS = load_validators()


def validate(name: str, value: Any) -> None:
    """Validate a value against one schema in the pinned snapshot."""
    VALIDATORS[f"schemas/{name}"].validate(value)
