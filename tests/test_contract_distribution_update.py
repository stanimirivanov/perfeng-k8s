"""Verify the reviewed staged snapshot contains only expected contract bytes."""

import tempfile
import unittest
from pathlib import Path

from scripts import contained_contracts, contracts
from scripts.contracts_distribution import write_snapshot


class ContractDistributionUpdateTests(unittest.TestCase):
    def test_writes_both_families_to_a_fresh_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "contracts"
            primary = {"schemas/primary.json": b"primary", "lock.json": b"primary lock"}
            contained = {"contained.json": b"contained", "lock.json": b"contained lock"}
            write_snapshot(target, primary, contained)
            self.assertEqual(
                {
                    item.relative_to(target).as_posix(): item.read_bytes()
                    for item in target.rglob("*")
                    if item.is_file()
                },
                {**primary, **{f"contained/{name}": data for name, data in contained.items()}},
            )
            with self.assertRaises(FileExistsError):
                write_snapshot(target, primary, contained)

    def test_rejects_cross_family_staging_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "contracts"
            with self.assertRaisesRegex(ValueError, "destination"):
                write_snapshot(target, {"contained/lock.json": b"substitute"}, {})
            self.assertFalse(target.exists())

    def test_selection_revisions_are_independent(self) -> None:
        self.assertNotEqual(contracts.EXPECTED_COMMIT, contained_contracts.REVISION)
