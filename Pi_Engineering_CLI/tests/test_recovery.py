import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pi_operations import backup, restore
from pi_workspace import Workspace, UserError


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / "source"
        source.mkdir()
        self.workspace = Workspace(source)
        self.workspace.save(self.workspace.config())
        self.workspace.create("Public recovery fixture", "engineer", "fixture")
        self.environment = patch.dict(os.environ, {"PI_TEST_RECOVERY": "public-test-passphrase-only"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.archive = self.root / "backup.pi"
        backup(self.workspace, self.archive, "PI_TEST_RECOVERY")
        target = self.root / "target"
        target.mkdir()
        self.target = Workspace(target)

    def assert_blocked(self):
        with self.assertRaisesRegex(UserError, "Restore is unfinished"):
            self.target.config()
        with self.assertRaisesRegex(UserError, "Restore is unfinished"):
            with self.target.database():
                self.fail("partial database was opened")
        with self.assertRaises(UserError):
            self.target.save(self.workspace.config())

    def test_interruption_before_publication_blocks_state(self):
        with patch("pi_operations.os.rename", side_effect=OSError("injected publication failure")):
            with self.assertRaises(OSError):
                restore(self.target, self.archive, "PI_TEST_RECOVERY")
        self.assertFalse(self.target.directory.exists())
        self.assert_blocked()

    def test_interruption_after_publication_blocks_state(self):
        with patch("pi_operations.sync_directory", side_effect=[None, None, OSError("injected sync failure")]):
            with self.assertRaises(OSError):
                restore(self.target, self.archive, "PI_TEST_RECOVERY")
        self.assertTrue(self.target.config_path.exists())
        self.assertTrue((self.target.directory / "tasks.sqlite3").exists())
        self.assert_blocked()

    def test_success_clears_marker_and_restores_records(self):
        restore(self.target, self.archive, "PI_TEST_RECOVERY")
        self.assertFalse((self.target.root / ".pi-restore-in-progress").exists())
        self.assertEqual(self.target.runs()[0]["request"], "Public recovery fixture")
        self.assertEqual(self.target.config(), self.workspace.config())

    def test_concurrent_state_is_not_overwritten(self):
        original = os.rename
        def concurrent(source, target):
            target.mkdir()
            (target / "concurrent.txt").write_text("preserve")
            return original(source, target)
        with patch("pi_operations.os.rename", side_effect=concurrent):
            with self.assertRaises(OSError):
                restore(self.target, self.archive, "PI_TEST_RECOVERY")
        self.assertEqual((self.target.directory / "concurrent.txt").read_text(), "preserve")
        self.assert_blocked()
