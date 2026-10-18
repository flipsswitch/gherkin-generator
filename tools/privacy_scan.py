import argparse
import hashlib
import io
import json
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from privacy import PNG_PUBLIC_CHUNKS, PNG_SIGNATURE, png_chunks


RULES = {
    'credential': re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:(?:proj|svcacct)-)?[A-Za-z0-9_-]{20,}|(?:AKIA|ASIA)[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{35}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----'),
    'secret_assignment': re.compile(r'''(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|client[_-]?secret|secret[_-]?key|aws_secret_access_key)\b['"]?\s*[:=]\s*['"][^'"\r\n]{8,}['"]'''),
    'bearer_token': re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}'),
    'jwt': re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'),
    'credential_url': re.compile(r'\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@', re.I),
    'email': re.compile(r'[A-Za-z0-9_.+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}'),
    'workstation_path': re.compile(r'(?<![A-Za-z0-9])[A-Za-z]:[\\/]|/(?:Users|home|root|mnt|media|Volumes|tmp|private/var)/|\\\\[A-Za-z0-9_-]+\\'),
    'private_network': re.compile(r'(?i)\b(?:local' r'host|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b'),
    'private_tool_state': re.compile(r'(?i)\.(?:codex|agents|aws)[/\\]|\b(?:context' r'Token|review' r'Token)\b'),
    'phone': re.compile(r'(?<![\w.])(?:\+[1-9][0-9 ()-]{8,18}[0-9]|\([0-9]{3}\) [0-9]{3}-[0-9]{4})(?![\w.])'),
}
FORBIDDEN_SUFFIXES = ('.blend', '.dgn', '.dgnlib', '.glb', '.log', '.pem', '.key', '.p12', '.pfx', '.pyc', '.zip', '.gz')
GENERATED_NAMES = frozenset(('run-log.json', 'object-mapping.json', 'geometry.json', 'gherkin-geometry.json',
                             'rooms.csv', 'components.csv', 'electrical-circuits.csv', 'lift-schedule.json',
                             'design-status.json', 'native-readback.json', 'reopened-readback.json'))


def scan_text(content, commit=False):
    findings = []
    for name, pattern in RULES.items():
        for match in pattern.finditer(content):
            if commit and name == 'email':
                line = content[:match.start()].rsplit('\n', 1)[-1]
                if line.startswith(('author ', 'committer ', 'tagger ')) and re.fullmatch(r'(?:[0-9]+\+)?[A-Za-z0-9-]+@users\.noreply\.github\.com', match.group()):
                    continue
            findings.append({'rule': name, 'line': content.count('\n', 0, match.start()) + 1})
    return findings


def public_label(path):
    if scan_text(path) or any(ord(c) < 32 for c in path):
        return 'redacted-path-' + hashlib.sha256(path.encode()).hexdigest()[:12]
    return path


def scan_name(path):
    name = PurePosixPath(path).name.lower()
    parts = PurePosixPath(path).parts
    results = scan_text(path)
    forbidden = (name.startswith('.env') or name.endswith(FORBIDDEN_SUFFIXES) or
                 re.search(r'\.(?:blend[0-9]+|dgn\..+)$', name) or name in GENERATED_NAMES or
                 any(p in ('outputs', '.git', '.aws', '.ssh', '__pycache__') for p in parts))
    if forbidden:
        results.append({'rule': 'private_or_generated_file'})
    if PurePosixPath(path).is_absolute() or '..' in parts or '\\' in path:
        results.append({'rule': 'unsafe_path'})
    return results


def scan_bytes(data):
    if data.startswith(PNG_SIGNATURE):
        try:
            chunks = list(png_chunks(data))
        except ValueError:
            return [{'rule': 'invalid_png'}]
        return [{'rule': 'png_metadata', 'chunk': kind.decode('ascii', errors='replace')}
                for kind, _ in chunks if kind not in PNG_PUBLIC_CHUNKS]
    try:
        content = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return [{'rule': 'unexpected_binary'}]
    if '\x00' in content:
        return [{'rule': 'unexpected_binary'}]
    return scan_text(content)


class Audit:
    def __init__(self):
        self.findings = []
        self.counts = {'working_files': 0, 'history_blobs': 0, 'history_commits': 0, 'history_tags': 0, 'archive_files': 0, 'png_files': 0}

    def add(self, path, results, **context):
        self.findings.extend({'file': public_label(path), **context, **result} for result in results)

    def file(self, path, data, scope):
        self.add(path, scan_name(path), scope=scope)
        self.add(path, scan_bytes(data), scope=scope)
        if data.startswith(PNG_SIGNATURE):
            self.counts['png_files'] += 1


def git_command(repo, *args):
    executable = shutil.which('git')
    if not executable:
        raise RuntimeError('Git is required for checkout and history scans')
    result = subprocess.run([executable, '-C', str(repo), *args], capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError('Git inspection failed; use a complete local checkout')
    return result.stdout


def scan_working_tree(repo, audit):
    names = set(git_command(repo, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').decode('utf-8').split('\0')) - {''}
    for name in sorted(names):
        path = repo / name
        if path.is_symlink():
            audit.add(name, [{'rule': 'symlink'}], scope='working')
        elif path.is_file():
            audit.file(name, path.read_bytes(), 'working')
            audit.counts['working_files'] += 1


def scan_history(repo, audit):
    if git_command(repo, 'rev-parse', '--is-shallow-repository').strip() != b'false':
        raise RuntimeError('History scan requires full history; fetch with depth zero')
    commits = git_command(repo, 'rev-list', '--all').decode().splitlines()
    if not commits:
        raise RuntimeError('History scan requires at least one commit')
    names = {}
    for commit in commits:
        tree = git_command(repo, 'ls-tree', '-rz', '--full-tree', commit)
        for entry in tree.split(b'\0'):
            if not entry:
                continue
            info, raw_name = entry.split(b'\t', 1)
            mode, kind, oid = info.decode().split()
            name = raw_name.decode('utf-8')
            audit.add(name, scan_name(name), scope='history', commit=commit)
            if mode == '120000' or kind != 'blob':
                audit.add(name, [{'rule': 'symlink_or_submodule'}], scope='history', commit=commit)
            names.setdefault(oid, name)
    objects = git_command(repo, 'rev-list', '--objects', '--all', '--no-object-names').decode().splitlines()
    executable = shutil.which('git')
    result = subprocess.run([executable, '-C', str(repo), 'cat-file', '--batch'],
                            input=('\n'.join(objects) + '\n').encode(), capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError('Could not read all historical objects')
    stream = io.BytesIO(result.stdout)
    for expected in objects:
        oid, kind, size = stream.readline().decode().strip().split()
        data = stream.read(int(size))
        if oid != expected or stream.read(1) != b'\n':
            raise RuntimeError('Incomplete history read')
        if kind == 'blob':
            audit.add(names.get(oid, 'historical-blob'), scan_bytes(data), scope='history', object=oid)
            audit.counts['history_blobs'] += 1
        elif kind in ('commit', 'tag'):
            audit.add('git-' + kind, scan_text(data.decode('utf-8'), commit=True), scope='history', object=oid)
            audit.counts['history_commits' if kind == 'commit' else 'history_tags'] += 1


def safe_zip_extra(extra):
    while len(extra) >= 4:
        tag, length = struct.unpack_from('<HH', extra)
        if tag != 0x5455 or length not in (1, 5, 9, 13) or len(extra) < length + 4:
            return False
        extra = extra[length + 4:]
    return not extra


def scan_archive(filename, audit):
    with zipfile.ZipFile(filename) as archive:
        if archive.comment and not re.fullmatch(b'[0-9a-f]{40,64}', archive.comment):
            audit.add('source-archive', [{'rule': 'archive_comment'}], scope='archive')
        seen, total = set(), 0
        for info in archive.infolist():
            name = info.filename
            if name in seen:
                audit.add(name, [{'rule': 'duplicate_archive_entry'}], scope='archive')
            seen.add(name)
            if info.comment or not safe_zip_extra(info.extra):
                audit.add(name, [{'rule': 'archive_metadata'}], scope='archive')
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                audit.add(name, [{'rule': 'symlink'}], scope='archive')
            if info.is_dir():
                audit.add(name, scan_name(name), scope='archive')
                continue
            total += info.file_size
            if info.file_size > 128 * 1024 * 1024 or total > 256 * 1024 * 1024:
                raise RuntimeError('Source archive exceeds inspection limits')
            audit.file(name, archive.read(info), 'archive')
            audit.counts['archive_files'] += 1


def main():
    parser = argparse.ArgumentParser(description='Screen public source, local Git history and source ZIPs without printing matched values.')
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--history', action='store_true')
    parser.add_argument('--archive', type=Path, action='append', default=[])
    args = parser.parse_args()
    audit = Audit()
    try:
        if not args.archive or args.history:
            scan_working_tree(args.repo.resolve(), audit)
        if args.history:
            scan_history(args.repo.resolve(), audit)
        for archive in args.archive:
            scan_archive(archive, audit)
    except (OSError, ValueError, RuntimeError, UnicodeError, zipfile.BadZipFile):
        print(json.dumps({'passed': False, 'error': 'Inspection incomplete. Check Git availability, full history, permissions and source archive format.'}))
        return 2
    print(json.dumps({'passed': not audit.findings, 'counts': audit.counts, 'findings': audit.findings}, indent=2))
    return int(bool(audit.findings))


if __name__ == '__main__':
    raise SystemExit(main())
