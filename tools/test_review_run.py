"""Reader boundaries; actual Rustic integration is exercised by run_drill.py."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from review_run import (
    current_manifest,
    inspect_run,
    read_json,
    review_run,
    validate_manifest,
)


def fixture(parent, name='run', filename='日本語.txt'):
    root = parent / name
    for folder in ('source', 'restore'):
        (root / folder / 'empty-directory').mkdir(parents=True)
        (root / folder / filename).write_bytes(b'abc\x00\xff\n')
    manifest = list(current_manifest(root / 'source').values())
    original = {'status': 'passed', 'cli': '/home/private-person/not-to-copy',
        'password': 'not-to-copy', 'manifest': manifest, 'cli_sha256': 'a' * 64,
        'restored_snapshot_id': 'b' * 64, 'second_snapshot_id': 'c' * 64,
        'repeat_data_added_files': 0, 'repeat_data_added': 0, 'repeat_data_added_packed': 0,
        'read_data_check': 'passed', 'wrong_password_rejected': True,
        'digest_manifest_match': True, 'literal_bytes_match': True}
    (root / 'source-manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    (root / 'result.json').write_text(json.dumps(original), encoding='utf-8')
    return root


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)

    def test_current_digests_literal_bytes_and_private_subset_output(self):
        root = fixture(self.parent)
        original = (root / 'result.json').read_bytes()
        output = self.parent / 'review'
        self.assertEqual(review_run(root, output), 0)
        self.assertEqual((root / 'result.json').read_bytes(), original)
        result = json.loads((output / 'review.json').read_text(encoding='utf-8'))
        self.assertEqual(result['status'], 'matched')
        self.assertTrue(all(result['checks'].values()))
        self.assertEqual((result['expected_regular_files'], result['expected_directories']), (1, 1))
        self.assertEqual(len(list(output.iterdir())), 6)
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        for path in output.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('not-to-copy', path.read_text(encoding='utf-8'))

    def test_changed_restore_is_not_hidden_by_recorded_success(self):
        root = fixture(self.parent)
        original = (root / 'result.json').read_bytes()
        file = root / 'restore/日本語.txt'
        original_stat = file.stat()
        file.write_bytes(b'abX\x00\xff\n')
        os.utime(file, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        output = self.parent / 'mismatch'
        self.assertEqual(review_run(root, output), 1)
        result = json.loads((output / 'review.json').read_text(encoding='utf-8'))
        self.assertEqual(result['status'], 'mismatch')
        self.assertTrue(result['checks']['current_source_matches_saved'])
        self.assertFalse(result['checks']['current_restore_matches_saved'])
        self.assertFalse(result['checks']['current_literal_file_bytes_match'])
        self.assertEqual((root / 'result.json').read_bytes(), original)
        self.assertIn('Recorded drill: passed', (output / 'report.html').read_text(encoding='utf-8'))
        self.assertIn('Current files do not match', (output / 'report.html').read_text(encoding='utf-8'))

    def test_extra_missing_and_changed_type_are_rejected(self):
        for kind in ('extra', 'missing', 'type', 'empty-directory'):
            with self.subTest(kind=kind):
                root = fixture(self.parent, kind)
                if kind == 'extra':
                    (root / 'restore/extra.txt').write_bytes(b'extra')
                elif kind == 'empty-directory':
                    (root / 'restore/empty-directory').rmdir()
                else:
                    (root / 'restore/日本語.txt').unlink()
                    if kind == 'type':
                        (root / 'restore/日本語.txt').mkdir()
                self.assertEqual(review_run(root, self.parent / ('review-' + kind)), 1)

    def test_changed_source_also_fails_against_saved_baseline(self):
        root = fixture(self.parent)
        for folder in ('source', 'restore'):
            (root / folder / '日本語.txt').write_bytes(b'both changed')
        result = inspect_run(root)[0]
        self.assertEqual(result['status'], 'mismatch')
        self.assertTrue(result['checks']['current_literal_file_bytes_match'])
        self.assertFalse(result['checks']['current_source_matches_saved'])

    def test_existing_output_and_broken_symlink_are_never_replaced(self):
        root = fixture(self.parent)
        for kind in ('file', 'directory', 'symlink'):
            output = self.parent / kind
            if kind == 'file':
                output.write_bytes(b'keep')
            elif kind == 'directory':
                output.mkdir()
                (output / 'keep').write_bytes(b'keep')
            else:
                output.symlink_to('missing')
            with self.assertRaisesRegex(ValueError, 'existing paths'):
                review_run(root, output)
        self.assertEqual((self.parent / 'file').read_bytes(), b'keep')
        self.assertEqual((self.parent / 'directory/keep').read_bytes(), b'keep')
        self.assertTrue((self.parent / 'symlink').is_symlink())

    def test_output_cannot_be_inside_the_run(self):
        root = fixture(self.parent)
        with self.assertRaisesRegex(ValueError, 'outside'):
            review_run(root, root / 'report')
        self.assertFalse((root / 'report').exists())

    def test_symlink_and_special_file_are_not_followed(self):
        for kind in ('symlink', 'fifo'):
            root = fixture(self.parent, kind)
            path = root / 'restore/unsupported'
            if kind == 'symlink':
                path.symlink_to(self.parent / 'never-read')
            else:
                os.mkfifo(path)
            output = self.parent / ('review-' + kind)
            with self.assertRaisesRegex(ValueError, 'Symlinks and special'):
                review_run(root, output)
            self.assertFalse(output.exists())

    def test_saved_paths_duplicate_sizes_and_empty_manifest_are_validated(self):
        for name in ('../outside', '/absolute', 'nested//bad', './bad', 'x\\bad', 'bad\x00'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_manifest([{'path': name, 'type': 'directory'}])
        for value in ([], [{'path': 'same', 'type': 'directory'}] * 2,
                [{'path': 'f', 'type': 'file', 'size': True, 'sha256': 'a' * 64}]):
            with self.assertRaises(ValueError):
                validate_manifest(value)

    def test_inconsistent_recorded_claims_and_bad_json_fail_before_output(self):
        root = fixture(self.parent)
        result = json.loads((root / 'result.json').read_text(encoding='utf-8'))
        result['wrong_password_rejected'] = False
        (root / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        output = self.parent / 'review'
        with self.assertRaisesRegex(ValueError, 'gates'):
            review_run(root, output)
        self.assertFalse(output.exists())
        (root / 'result.json').write_text('{truncated', encoding='utf-8')
        with self.assertRaises(ValueError):
            review_run(root, output)
        self.assertFalse(output.exists())
        huge = self.parent / 'huge.json'
        huge.write_bytes(b' ' * 1_048_577)
        with self.assertRaisesRegex(ValueError, '1 MiB'):
            read_json(huge)

    def test_unsafe_filename_is_displayed_as_text(self):
        root = fixture(self.parent, filename='<img src=x onerror="alert(1)">.txt')
        output = self.parent / 'review'
        self.assertEqual(review_run(root, output), 0)
        html = (output / 'report.html').read_text(encoding='utf-8')
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img', html)
        self.assertNotIn('<script', html)


if __name__ == '__main__':
    unittest.main()
