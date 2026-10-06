import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.research_docs import PAGES, main


class ResearchTests(unittest.TestCase):
    def test_success_and_failure_manifest_without_network(self):
        raw = b'{"resources": [{"name": "Guild", "methods": [{"name": "Roster", "path": "/test"}]}]}'
        count = 0
        def fetch(url, timeout):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("remote-error")
            return io.BytesIO(raw)
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.redirect_stdout(io.StringIO()):
                main(Path(directory), fetch)
            manifest = json.loads((Path(directory) / "manifest.json").read_text())
            self.assertEqual(len(manifest), len(PAGES))
            self.assertEqual(manifest[1]["error"], "OSError")
            self.assertEqual(manifest[0]["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual((Path(directory) / manifest[0]["file"]).read_bytes(), raw)
