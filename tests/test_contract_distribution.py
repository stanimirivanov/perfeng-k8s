"""Exercise the independent Kubernetes contract selections."""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import contracts_distribution


class ContractDistributionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.snapshot = Path(temporary.name) / "contracts"
        shutil.copytree(contracts_distribution.ROOT / "contracts", self.snapshot)
        self.primary = self.snapshot
        self.contained = self.snapshot / "contained"

    def test_both_selections_match_their_own_member_bytes(self) -> None:
        for snapshot, contained in ((self.primary, False), (self.contained, True)):
            with self.subTest(snapshot=snapshot):
                lock = json.loads((snapshot / "lock.json").read_bytes())
                members = {}
                for name, digest in lock["files"].items():
                    if contained:
                        name = contracts_distribution.CONTAINED_SOURCES[name]
                    members[name] = digest
                members["LICENSE"] = hashlib.sha256(b"additional signed member").hexdigest()
                matched = contracts_distribution.compare(
                    snapshot, lock["commit"], members, contained=contained
                )
                self.assertEqual(matched, lock["files"])

    def test_mixed_revision_or_overlapping_member_is_refused(self) -> None:
        primary = json.loads((self.primary / "lock.json").read_bytes())
        contained = json.loads((self.contained / "lock.json").read_bytes())
        members = {
            source: contained["files"][name]
            for name, source in contracts_distribution.CONTAINED_SOURCES.items()
        }
        with self.assertRaisesRegex(ValueError, "revision"):
            contracts_distribution.compare(self.primary, contained["commit"], members)
        with self.assertRaisesRegex(ValueError, "signed member"):
            contracts_distribution.compare(self.primary, primary["commit"], members)

    def test_changed_local_schema_is_refused(self) -> None:
        lock = json.loads((self.primary / "lock.json").read_bytes())
        name = next(iter(lock["files"]))
        (self.primary / name).write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "snapshot bytes"):
            contracts_distribution.compare(self.primary, lock["commit"], lock["files"])
