"""Check tracked release sources or APK/archive contents without printing matched secrets."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
            rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'github_pat_[A-Za-z0-9_]{30,}',
            rb'AKIA[A-Z0-9]{16}', rb'\b[0-9]{7,12}:[A-Za-z0-9_-]{30,}\b']
FORBIDDEN = {'.env', 'local.properties', 'inbox.sqlite', 'outbox.db'}


def scan(name, content, private):
    if any(re.search(pattern, content) for pattern in PATTERNS):
        raise SystemExit(f'Possible credential in {name}; value redacted')
    if any(pattern.lower() in content.lower() for pattern in private):
        raise SystemExit(f'Private information in {name}; value redacted')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('artifacts', nargs='*', type=Path)
    parser.add_argument('--private-patterns', type=Path, help='Private JSON array of strings; never commit this file')
    args = parser.parse_args()
    private = [value.encode() for value in json.loads(args.private_patterns.read_text()) if len(value) >= 6] if args.private_patterns else []
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    checked = 0
    for name in filter(None, files):
        path = Path(name)
        if path.name in FORBIDDEN or path.suffix in ('.jks', '.keystore', '.p12', '.pem', '.key', '.sqlite', '.db', '.apk') or any(part in ('data', '.signing', '.git', '__pycache__') for part in path.parts):
            raise SystemExit(f'Private/runtime file tracked: {name}')
        scan(name, (ROOT / name).read_bytes(), private)
        checked += 1
    for artifact in args.artifacts:
        if zipfile.is_zipfile(artifact):
            with zipfile.ZipFile(artifact) as archive:
                for entry in archive.infolist():
                    if not entry.is_dir(): scan(artifact.name + ':' + entry.filename, archive.read(entry), private)
        else:
            scan(artifact.name, artifact.read_bytes(), private)
    print(f'Privacy audit passed: {checked} tracked source files and {len(args.artifacts)} artifacts. No matched credentials or private patterns.')


if __name__ == '__main__':
    main()
