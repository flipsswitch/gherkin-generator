import contextlib
import errno
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gherkin
from privacy import PNG_SIGNATURE, clean_png, create_output_directory, error_summary, ignore_output_file, png_chunks
from tools import privacy_scan


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)


def test_png(metadata=b''):
    header = struct.pack('>2I5B', 1, 1, 8, 2, 0, 0, 0)
    return PNG_SIGNATURE + chunk(b'IHDR', header) + metadata + chunk(b'IDAT', zlib.compress(b'\0\xff\0\0')) + chunk(b'IEND', b'')


class PrivacyTests(unittest.TestCase):
    def test_exception_messages_and_names_are_never_copied(self):
        secret = 'gh' + 'p_' + 'a' * 30
        filename = str(Path.home() / 'private-client' / 'proposal.dgn')
        error = PermissionError(errno.EACCES, secret, filename)
        result = error_summary(error)
        self.assertEqual(result['type'], 'PermissionError')
        self.assertEqual(result['errno'], errno.EACCES)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(filename, json.dumps(result))
        custom_error = type(secret, (Exception,), {})
        self.assertEqual(error_summary(custom_error(secret))['type'], 'Exception')

    def test_new_custom_directory_ignores_all_future_reports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, 'init', '--quiet')
            output = create_output_directory(root / 'custom' / 'model')
            for name in ('parameters.json', 'rooms.csv', 'future-report.json', '.private-diagnostics.txt'):
                path = output / name
                path.write_text('synthetic', encoding='utf-8')
                result = self.git(root, 'check-ignore', str(path))
                self.assertEqual(result.returncode, 0)
            with self.assertRaises(FileExistsError):
                create_output_directory(output)

    def test_single_output_ignore_is_literal_and_preserves_existing_rules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, 'init', '--quiet')
            (root / '.gitignore').write_text('existing-rule', encoding='utf-8')
            target = root / 'plan [draft] #1.json'
            target.write_text('{}', encoding='utf-8')
            ignore_output_file(target)
            ignore_output_file(target)
            self.assertTrue((root / '.gitignore').read_text().startswith('existing-rule\n'))
            self.assertEqual((root / '.gitignore').read_text().count('/plan'), 1)
            self.assertEqual(self.git(root, 'check-ignore', str(target)).returncode, 0)
            neighbor = root / 'plan d #1.json'
            neighbor.write_text('{}', encoding='utf-8')
            self.assertEqual(self.git(root, 'check-ignore', str(neighbor)).returncode, 1)

    def test_geometry_cli_protects_custom_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, 'init', '--quiet')
            output = root / 'arbitrary.json'
            with patch.object(sys, 'argv', ['gherkin.py', '--output', str(output)]), patch.object(gherkin, 'generate', return_value={'counts': {}}), contextlib.redirect_stdout(io.StringIO()):
                gherkin.main()
            self.assertEqual(json.loads(output.read_text()), {'counts': {}})
            self.assertEqual(self.git(root, 'check-ignore', str(output)).returncode, 0)

    def test_output_ignore_overrides_an_existing_negation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, 'init', '--quiet')
            (root / '.gitignore').write_text('*/\n/geometry.json\n!geometry.json\n', encoding='utf-8')
            target = root / 'geometry.json'
            target.write_text('{}', encoding='utf-8')
            self.assertEqual(self.git(root, 'check-ignore', str(target)).returncode, 1)
            ignore_output_file(target)
            self.assertEqual(self.git(root, 'check-ignore', str(target)).returncode, 0)

    def test_png_text_and_exif_removed_without_changing_pixels(self):
        metadata = chunk(b'tEXt', b'Author\0synthetic') + chunk(b'eXIf', b'synthetic')
        original = test_png(metadata)
        with tempfile.TemporaryDirectory() as temporary:
            filename = Path(temporary) / 'preview.png'
            filename.write_bytes(original)
            self.assertEqual(len(privacy_scan.scan_bytes(original)), 2)
            clean_png(filename)
            cleaned = filename.read_bytes()
        self.assertFalse(privacy_scan.scan_bytes(cleaned))
        self.assertEqual([data for kind, data in png_chunks(original) if kind == b'IDAT'],
                         [data for kind, data in png_chunks(cleaned) if kind == b'IDAT'])

    def test_invalid_png_cannot_hide_trailing_data(self):
        for data in (test_png() + b'private', test_png()[:-1], test_png()[:24] + b'bad'):
            self.assertEqual(privacy_scan.scan_bytes(data), [{'rule': 'invalid_png'}])

    def test_scanner_detects_secrets_paths_and_contacts_without_echoing_values(self):
        fixtures = {
            'credential': 'gh' + 'p_' + 'A' * 30,
            'secret_assignment': 'password' + ' = ' + repr('synthetic-secret'),
            'email': 'person' + '@' + 'example.invalid',
            'workstation_path': 'Z:' + chr(92) + chr(92).join(('Users', 'synthetic', 'model.dgn')),
            'private_network': '.'.join(('192', '168', '5', '2')),
            'credential_url': 'https://' + 'user:synthetic' + '@' + 'example.invalid',
            'phone': '+' + '1 (202) ' + '555' + '-0100',
        }
        for rule, value in fixtures.items():
            with self.subTest(rule=rule):
                results = privacy_scan.scan_text(value)
                self.assertIn(rule, {item['rule'] for item in results})
                self.assertNotIn(value, json.dumps(results))
        self.assertFalse(privacy_scan.scan_text('https://example.invalid/public-document'))

    def test_noreply_allowed_only_in_git_identity_headers(self):
        email = '1+fixture' + '@' + 'users.noreply.github.com'
        self.assertFalse(privacy_scan.scan_text('author Fixture <' + email + '> 0 +0000', commit=True))
        self.assertTrue(privacy_scan.scan_text(email))
        self.assertTrue(privacy_scan.scan_text('Commit message ' + email, commit=True))

    def test_archive_scans_content_metadata_and_native_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'source.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('repo/preview.png', test_png(chunk(b'tEXt', b'Author\0synthetic')))
                output.writestr('repo/model.dgn', b'\x00native')
                output.writestr('repo/note.txt', 'gh' + 'p_' + 'A' * 30)
                output.comment = b'synthetic project comment'
            audit = privacy_scan.Audit()
            privacy_scan.scan_archive(archive, audit)
            rules = {item['rule'] for item in audit.findings}
            self.assertTrue({'png_metadata', 'private_or_generated_file', 'unexpected_binary', 'credential', 'archive_comment'} <= rules)

    def test_deleted_secret_and_private_commit_identity_remain_detectable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.git(root, 'init', '--quiet')
            self.git(root, 'config', 'user.name', 'Fixture')
            self.git(root, 'config', 'user.email', 'fixture' + '@' + 'example.invalid')
            path = root / 'deleted.txt'
            path.write_text('gh' + 'p_' + 'A' * 30, encoding='utf-8')
            self.git(root, 'add', 'deleted.txt')
            self.assertEqual(self.git(root, 'commit', '--quiet', '-m', 'Fixture first commit').returncode, 0)
            self.git(root, 'rm', '--quiet', 'deleted.txt')
            self.assertEqual(self.git(root, 'commit', '--quiet', '-m', 'Fixture second commit').returncode, 0)
            self.assertEqual(self.git(root, 'tag', '-a', 'fixture-tag', '-m', 'gh' + 'p_' + 'B' * 30).returncode, 0)
            audit = privacy_scan.Audit()
            privacy_scan.scan_working_tree(root, audit)
            self.assertFalse(audit.findings)
            privacy_scan.scan_history(root, audit)
            self.assertEqual(audit.counts['history_commits'], 2)
            self.assertEqual(audit.counts['history_tags'], 1)
            self.assertIn('credential', {item['rule'] for item in audit.findings})
            self.assertIn('email', {item['rule'] for item in audit.findings})
            head = self.git(root, 'rev-parse', 'HEAD').stdout.decode().strip()
            (root / '.git' / 'shallow').write_text(head + '\n', encoding='utf-8')
            with self.assertRaises(RuntimeError):
                privacy_scan.scan_history(root, privacy_scan.Audit())

    def test_workstation_path_in_filename_is_redacted(self):
        path = '/home' + '/synthetic/private.txt'
        audit = privacy_scan.Audit()
        audit.file(path, b'safe', 'fixture')
        self.assertNotIn(path, json.dumps(audit.findings))
        self.assertTrue(audit.findings)

    def test_generated_files_are_flagged_even_if_force_added(self):
        for name in ('custom/model.blend2', 'custom/model.dgn.bak', 'custom/rooms.csv', 'custom/.env', 'custom/object-mapping.json'):
            self.assertIn('private_or_generated_file', {item['rule'] for item in privacy_scan.scan_name(name)})

    def git(self, root, *args):
        executable = shutil.which('git')
        self.assertIsNotNone(executable, 'Git is required for privacy integration tests')
        environment = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        return subprocess.run([executable, '-C', str(root), *args], capture_output=True, env=environment)


if __name__ == '__main__':
    unittest.main()
