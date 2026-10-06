"""Offline publication checks. Diagnostics contain locations/categories, never values."""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 1024 * 1024
LOCAL_DIRS = {
    'data', 'reports', 'outputs', 'artifacts', 'local', 'tmp', '.venv', 'venv',
    'env', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.tox',
    '.nox', '.idea', '.vscode', '.aws', '.codex', '.agents', 'target', 'build',
    'dist', 'htmlcov',
}
LOCAL_SUFFIXES = ('.sqlite', '.db', '.log', '.lock', '.pid', '.tmp', '.temp',
                  '.bak', '.pyc', '.pyo', '.class', '.jar', '.zip', '.tar', '.gz',
                  '.pem', '.key', '.p12', '.pfx')
TEXT_SUFFIXES = {'.py', '.md', '.txt', '.graphql', '.json', '.jsonl', '.yaml',
                 '.yml', '.toml', '.ini', '.cfg', '.sh', '.example'}
TEXT_NAMES = {'.gitignore', '.gitattributes', 'pre-commit', 'LICENSE', 'NOTICE',
              'COPYING', 'Dockerfile', 'Makefile'}
KEY = r'(?:[\w-]*client[_-]?(?:id|secret)|api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|token)'
LITERAL = re.compile(r'''(?im)(?<![\w-])['"]?''' + KEY + r'''['"]?\s*[:=]\s*(['"])([^'"\r\n]+)\1''')
ENV_ASSIGNMENT = re.compile(r'(?im)^[ \t]*(?:BLIZZARD|WCL)_CLIENT_(?:ID|SECRET)[ \t]*=[ \t]*(\S[^\r\n]*)$')
AUTH_VALUE = re.compile(r'''(?i)['"]?authorization['"]?\s*[:=]\s*['"](?:bearer|basic)\s+([^'"\r\n]+)''')
PERSONAL_PATH = re.compile(r'(?i)(?:[a-z]:[\\/]+Users[\\/]+|/(?:Users|home)/)[^\s\x00"\'<>]+')
EMAIL = re.compile(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b')
HIGH_CONFIDENCE = re.compile(
    r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'
    r'|\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}'
    r'|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,}'
    r'|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b'
    r'|https?://[^\s/"\']+:[^\s/"\']+@'
)
FIXTURE_AUTH = re.compile(r'''(?i)['"](?:authorization|proxy-authorization|cookie|set-cookie|access_token|refresh_token|client_secret|client_id|api_key)['"]\s*:''')

# Exact, reviewed in-memory synthetic markers only, scoped to their existing files.
# Never add real values or path-wide exclusions. Fixtures do not get exemptions.
SYNTHETIC_VALUES = {
    'rwf/pilot_synthetic.py': {'synthetic-token-never-archive'},
    'tests/test_probe.py': {'secret-token', 'private-id', 'private-secret'},
    'tests/test_pilot.py': {'NEVER-SAVE-LIVE-WIRING-TOKEN', 'TOKENEXCLUDED',
                          'once', 'temporary', 'x', 'synthetic-credential-never-archive'},
}


@dataclass(frozen=True)
class Finding:
    path: str
    category: str
    line: int = 0


def known_credentials(environ):
    """Return bytes only in memory, including encoded OAuth Basic pairs."""
    result = []
    for provider in ('BLIZZARD', 'WCL'):
        identity = environ.get(provider + '_CLIENT_ID', '')
        secret = environ.get(provider + '_CLIENT_SECRET', '')
        result.extend(v.encode() for v in (identity, secret) if v)
        if identity and secret:
            result.append(base64.b64encode((identity + ':' + secret).encode()))
    return result


def inspect_content(path, content, mode='100644', known=()):
    """Inspect a public candidate, including files forcibly added despite ignores."""
    findings = []
    p = PurePosixPath(path)
    name = p.name.lower()
    fixture = path.startswith('tests/fixtures/')
    if mode not in ('100644', '100755'):
        findings.append(Finding(path, 'symlink/submodule/unmerged entry needs review'))
    if any(part.lower() in LOCAL_DIRS for part in p.parts[:-1]):
        findings.append(Finding(path, 'local/generated directory'))
    if (name.startswith('.env') and name != '.env.example'
            or re.search(r'(?:credentials?|secrets?)(?:[._-]|$)', name)
            or '.local.' in name or name in {'desktop.ini', 'thumbs.db', '.ds_store'}
            or '.sqlite' in name or re.search(r'\.db(?:-|$)', name)
            or name.endswith(LOCAL_SUFFIXES)
            or name.endswith('.jsonl') and not fixture):
        findings.append(Finding(path, 'private/generated filename'))
    if len(content) > MAX_BYTES:
        findings.append(Finding(path, 'file exceeds 1 MiB review limit'))
    if any(value in content for value in known):
        findings.append(Finding(path, 'known process credential or encoded OAuth pair'))
    if p.suffix.lower() not in TEXT_SUFFIXES and p.name not in TEXT_NAMES:
        findings.append(Finding(path, 'unreviewed file type'))
    try:
        text = content.decode('utf-8-sig')
    except UnicodeError:
        findings.append(Finding(path, 'binary/non-UTF-8 content needs review'))
        return findings
    if '\x00' in text:
        findings.append(Finding(path, 'binary content needs review'))
    allowed = SYNTHETIC_VALUES.get(path, set())
    for category, pattern in (
        ('personal absolute path', PERSONAL_PATH), ('email needs privacy review', EMAIL),
        ('high-confidence secret pattern', HIGH_CONFIDENCE),
        ('credential literal', LITERAL), ('credential environment assignment', ENV_ASSIGNMENT),
        ('authenticated header', AUTH_VALUE),
    ):
        for match in pattern.finditer(text):
            if category == 'credential literal' and match.group(2) in allowed:
                continue
            line = text.count('\n', 0, match.start()) + 1
            findings.append(Finding(path, category, line))
    if fixture:
        for match in FIXTURE_AUTH.finditer(text):
            findings.append(Finding(path, 'fixture contains authentication fields',
                                    text.count('\n', 0, match.start()) + 1))
    if name == '.env.example':
        expected = {p + '_CLIENT_' + k for p in ('BLIZZARD', 'WCL') for k in ('ID', 'SECRET')}
        assignments = []
        for line in text.splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            key, separator, value = line.partition('=')
            assignments.append(key)
            if not separator or key not in expected or value.strip():
                findings.append(Finding(path, 'example must contain only empty credential assignments'))
        if set(assignments) != expected or len(assignments) != len(expected):
            findings.append(Finding(path, 'example credential names missing/duplicated'))
    return findings


def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    if result.returncode:
        # Git stderr may include local paths or content; never echo it.
        raise RuntimeError('Git inspection failed; verify repository/index locally')
    return result.stdout


def candidates(index=False):
    """Index modes scan all index blobs; default scans working public candidates."""
    if index:
        for record in git('ls-files', '--stage', '-z').split(b'\0'):
            if not record:
                continue
            metadata, raw_path = record.split(b'\t', 1)
            mode, oid, stage = metadata.decode().split()
            path = raw_path.decode('utf-8')
            if stage != '0':
                yield path, b'', 'unmerged'
            else:
                yield path, git('cat-file', 'blob', oid), mode
    else:
        names = git('ls-files', '--cached', '--others', '--exclude-standard', '-z')
        for raw_path in sorted(set(names.split(b'\0')) - {b''}):
            path = raw_path.decode('utf-8')
            local = ROOT / path
            if local.is_symlink():
                yield path, os.readlink(local).encode(), '120000'
            elif local.is_file():
                yield path, local.read_bytes(), '100644'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--staged', action='store_true', help='scan entire index, using staged bytes')
    group.add_argument('--tracked', action='store_true', help='scan entire index (CI/clone)')
    args = parser.parse_args(argv)
    try:
        known = known_credentials(os.environ)
        findings = []
        count = 0
        public = list(candidates(args.staged or args.tracked))
        names = {path for path, _, _ in public}
        for path, content, mode in public:
            count += 1
            findings.extend(inspect_content(path, content, mode, known))
            if path.startswith('tests/fixtures/') and 'tests/fixtures/README.md' not in names:
                findings.append(Finding(path, 'fixture provenance README missing from public tree'))
        if not count:
            print('FAIL: no public candidates; initialize Git/add reviewed files first')
            return 1
        for item in sorted(set(findings), key=lambda f: (f.path, f.line, f.category)):
            # Escape control characters in names; never print matched content.
            location = ascii(item.path) + (':' + str(item.line) if item.line else '')
            print('FAIL: ' + location + ': ' + item.category)
        label = 'index' if args.staged or args.tracked else 'working public candidates'
        print(f'{"FAIL" if findings else "PASS"}: {count} files checked ({label})')
        return 1 if findings else 0
    except (OSError, RuntimeError, UnicodeError, ValueError):
        print('FAIL: unable to inspect public candidates; verify Git and readable files locally')
        return 1


if __name__ == '__main__':
    sys.exit(main())
