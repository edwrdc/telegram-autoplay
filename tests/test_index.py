import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_index


class IndexTests(unittest.TestCase):
    def test_checked_in_catalog_matches_plugin(self):
        expected = build_index.build_index()
        self.assertEqual(json.loads(build_index.INDEX.read_text()), expected)
        entry = expected["plugins"][0]
        data = build_index.PLUGIN.read_bytes()
        self.assertEqual(entry["size"], len(data))
        self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
        self.assertLess(len(json.dumps(expected).encode()), 1024 * 1024)

    def test_timestamp_is_stable_until_plugin_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = root / "autoplay.plugin"
            index = root / "extera-plugins.json"
            plugin.write_bytes(build_index.PLUGIN.read_bytes())
            with patch.multiple(build_index, ROOT=root, PLUGIN=plugin, INDEX=index):
                first = build_index.build_index()
                first["plugins"][0]["updated_at"] = "2025-01-01T00:00:00Z"
                index.write_text(json.dumps(first))
                self.assertEqual(build_index.build_index(), first)
                plugin.write_bytes(plugin.read_bytes() + b"\n# Change\n")
                changed = build_index.build_index()["plugins"][0]
                self.assertNotEqual(changed["sha256"], first["plugins"][0]["sha256"])
                self.assertNotEqual(changed["updated_at"], "2025-01-01T00:00:00Z")

    def test_check_rejects_stale_catalog_without_writing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "extera-plugins.json"
            index.write_text('{"plugins": []}')
            with patch.object(build_index, "INDEX", index), patch("sys.argv", ["build_index.py", "--check"]):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    build_index.main()
                self.assertEqual(error.exception.code, 1)
                self.assertEqual(index.read_text(), '{"plugins": []}')

    def test_missing_metadata_is_rejected_without_importing_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "broken.plugin"
            plugin.write_text('__id__ = "test"\n__name__ = "Test"\nraise Exception("Do not execute")\n')
            with patch.object(build_index, "PLUGIN", plugin):
                with self.assertRaisesRegex(ValueError, "Missing plugin version"):
                    build_index.build_index()


if __name__ == "__main__":
    unittest.main()
