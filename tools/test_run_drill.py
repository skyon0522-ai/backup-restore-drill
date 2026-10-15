"""Exercise actual runner preflight without invoking any build or backup command."""
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import run_drill

ROOT = Path(__file__).resolve().parents[1]


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)

    def run_cli(self, output, cache=None):
        environment = {**os.environ, 'CARGO_TARGET_DIR': str(cache or self.parent / 'cache')}
        return subprocess.run([sys.executable, '-B', ROOT / 'tools/run_drill.py', str(output)],
            env=environment, capture_output=True, timeout=10, check=False)

    def test_help_does_not_start_build_or_create_output(self):
        result = subprocess.run([sys.executable, '-B', ROOT / 'tools/run_drill.py', '--help'],
            capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'New work directory', result.stdout)
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_existing_file_directory_and_symlink_are_preserved(self):
        for kind in ('file', 'directory', 'symlink'):
            output = self.parent / kind
            if kind == 'file':
                output.write_bytes(b'keep')
            elif kind == 'directory':
                output.mkdir()
                (output / 'keep').write_bytes(b'keep')
            else:
                output.symlink_to('missing')
            result = self.run_cli(output)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b'existing paths', result.stderr)
        self.assertFalse((self.parent / 'cache').exists())
        self.assertEqual((self.parent / 'file').read_bytes(), b'keep')
        self.assertEqual((self.parent / 'directory/keep').read_bytes(), b'keep')
        self.assertTrue((self.parent / 'symlink').is_symlink())

    def test_output_inside_source_is_refused_before_writing(self):
        output = ROOT / ('never-created-runner-test-' + self.parent.name)
        self.assertFalse(output.exists())
        result = self.run_cli(output)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'separate directories', result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse((self.parent / 'cache').exists())

    def test_overlapping_or_source_local_build_cache_is_refused(self):
        output = self.parent / 'work'
        for cache in (output / 'build', ROOT / ('never-created-build-cache-' + self.parent.name)):
            self.assertFalse(cache.exists())
            result = self.run_cli(output, cache)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b'separate directories', result.stderr)
            self.assertFalse(output.exists())
            self.assertFalse(cache.exists())

    def test_failed_source_gate_retains_logs_and_stops_before_build(self):
        source = self.parent / 'source'
        (source / 'tools').mkdir(parents=True)
        (source / 'tools/verify_source.py').write_text("print('deliberate source gate failure')\nraise SystemExit(3)\n", encoding='utf-8')
        output = self.parent / 'work'
        with patch.object(run_drill, 'ROOT', source), patch.dict(os.environ, {'CARGO_TARGET_DIR': str(self.parent / 'cache')}), redirect_stdout(StringIO()):
            with self.assertRaisesRegex(ValueError, 'source-before failed'):
                run_drill.execute(output)
        self.assertIn('deliberate source gate failure', (output / 'source-before.log').read_text(encoding='utf-8'))
        self.assertFalse((output / 'review').exists())
        self.assertFalse((output / 'cli-build.log').exists())


if __name__ == '__main__':
    unittest.main()
