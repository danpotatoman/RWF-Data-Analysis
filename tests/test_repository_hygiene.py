"""Verify publication guardrails with invented values and isolated Git indexes."""
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import repository_hygiene as hygiene


class HygieneTests(unittest.TestCase):
    def categories(self, path, content, **kwargs):
        return {f.category for f in hygiene.inspect_content(path, content.encode(), **kwargs)}

    def test_names_and_empty_example_are_safe_but_values_fail(self):
        example = '\n'.join(p + '_CLIENT_' + k + '=' for p in ('BLIZZARD', 'WCL')
                            for k in ('ID', 'SECRET'))
        self.assertFalse(self.categories('.env.example', example))
        value = 'invented-' + 'sensitive-value'
        self.assertIn('credential environment assignment',
                      self.categories('.env.example', example + value))
        key = 'client_' + 'secret'
        self.assertIn('credential literal',
                      self.categories('config.json', '{"' + key + '":"' + value + '"}'))

    def test_private_paths_emails_size_and_binary_are_rejected(self):
        path = 'C:' + '\\Users\\' + 'example\\project'
        self.assertIn('personal absolute path', self.categories('docs/example.md', path))
        email = 'someone' + '@' + 'example.test'
        self.assertIn('email needs privacy review', self.categories('docs/example.md', email))
        self.assertIn('file exceeds 1 MiB review limit',
                      self.categories('docs/large.md', 'a' * (hygiene.MAX_BYTES + 1)))
        self.assertIn('binary/non-UTF-8 content needs review',
                      {f.category for f in hygiene.inspect_content('image.png', bytes([255]))})

    def test_forced_local_files_symlinks_and_archives_fail(self):
        for path in ('data/sample.json', 'nested/.env', 'config.local.json',
                     'database.sqlite-wal', 'archive.zip', '.vscode/settings.json'):
            with self.subTest(path=path):
                self.assertTrue(self.categories(path, '{}'))
        self.assertIn('symlink/submodule/unmerged entry needs review',
                      self.categories('link.md', 'target', mode='120000'))

    def test_synthetic_exemption_is_exact_and_scoped(self):
        text = '{"' + 'access_' + 'token' + '":"' + 'secret-' + 'token' + '"}'
        self.assertFalse(self.categories('tests/test_probe.py', text))
        self.assertIn('credential literal', self.categories('tests/fixtures/response.json', text))
        self.assertIn('fixture contains authentication fields',
                      self.categories('tests/fixtures/response.json', text))
        self.assertIn('credential literal', self.categories('tests/new_test.py', text))

    def test_known_credentials_and_basic_pairs_detected_without_diagnostics_leak(self):
        identity, value = 'invented-' + 'identity', 'invented-' + 'secret'
        known = hygiene.known_credentials({'WCL_CLIENT_ID': identity, 'WCL_CLIENT_SECRET': value})
        for content in known:
            findings = hygiene.inspect_content('docs/example.md', content, known=known)
            self.assertIn('known process credential or encoded OAuth pair',
                          {f.category for f in findings})
            self.assertNotIn(value, repr(findings))

    def test_authenticated_headers_and_private_keys_fail(self):
        text = '{"' + 'Authorization' + '":"' + 'Bearer' + ' invented-value"}'
        self.assertIn('authenticated header', self.categories('request.json', text))
        key = '-----BEGIN ' + 'PRIVATE KEY-----'
        self.assertIn('high-confidence secret pattern', self.categories('docs/key.md', key))

    def test_index_scans_staged_bytes_and_force_added_ignored_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                result = subprocess.run(['git', '-c', 'safe.directory=' + str(root), *args],
                                        cwd=root, capture_output=True)
                self.assertEqual(result.returncode, 0, 'isolated Git operation failed')
            git('init', '--quiet')
            (root / '.gitignore').write_text('.env\n')
            (root / 'README.md').write_text('safe documentation\n')
            value = 'invented-' + 'staged-credential'
            (root / '.env').write_text('WCL_CLIENT_SECRET=' + value)
            git('add', '.gitignore', 'README.md')
            git('add', '-f', '.env')
            # Sanitizing working bytes does not fix the staged secret.
            (root / '.env').write_text('')
            output = io.StringIO()
            clean_env = {p + '_CLIENT_' + k: '' for p in ('BLIZZARD', 'WCL') for k in ('ID', 'SECRET')}
            clean_env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='safe.directory',
                             GIT_CONFIG_VALUE_0=str(root))
            with patch.object(hygiene, 'ROOT', root), patch.dict('os.environ', clean_env):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(hygiene.main(['--staged']), 1)
            self.assertIn('credential environment assignment', output.getvalue())
            self.assertNotIn(value, output.getvalue())
            git('rm', '--cached', '-f', '.env')
            with patch.object(hygiene, 'ROOT', root), patch.dict('os.environ', clean_env):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(hygiene.main(['--tracked']), 0)


if __name__ == '__main__':
    unittest.main()
