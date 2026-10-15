"""Build the copied engine and run one synthetic Linux recovery exercise."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from review_run import review_run

ROOT = Path(__file__).resolve().parents[1]


def separate(first, second):
    return not first.is_relative_to(second) and not second.is_relative_to(first)


def execute(work):
    if work.exists() or work.is_symlink():
        raise ValueError('Choose a new work directory; existing paths are not replaced')
    work = work.expanduser().resolve()
    raw_cache = os.environ.get('CARGO_TARGET_DIR')
    cache = (ROOT / raw_cache).resolve() if raw_cache else (
        Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'backup-restore-drill/target').resolve()
    if not separate(work, ROOT) or not separate(cache, ROOT) or not separate(work, cache):
        raise ValueError('Keep work, build cache and source checkout in separate directories')
    work.mkdir(mode=0o700)
    cache.mkdir(parents=True, exist_ok=True)
    receipts = work / 'receipts'
    receipts.mkdir(mode=0o700)
    commands = [
        ('source-before', [sys.executable, '-B', ROOT / 'tools/verify_source.py']),
        ('review-tests', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tools', '-p', 'test_*.py', '-v']),
        ('cli-build', ['cargo', 'build', '--locked', '--no-default-features', '--manifest-path', ROOT / 'app/Cargo.toml', '--target-dir', cache]),
        ('drill-tests', ['cargo', 'test', '--locked', '--manifest-path', ROOT / 'drill/Cargo.toml', '--target-dir', cache]),
        ('drill-build', ['cargo', 'build', '--locked', '--manifest-path', ROOT / 'drill/Cargo.toml', '--target-dir', cache]),
    ]
    stages = []
    environment = {**os.environ, 'CARGO_BUILD_JOBS': os.environ.get('CARGO_BUILD_JOBS', '2')}

    def run(name, command, capture=False):
        print(f'{name}: running', flush=True)
        started = time.monotonic()
        with (work / f'{name}.log').open('w', encoding='utf-8') as log:
            child = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding='utf-8', errors='replace', env=environment,
                                     start_new_session=True)
            lines = []
            try:
                for line in child.stdout:
                    log.write(line)
                    print(line, end='', flush=True)
                    if capture:
                        lines.append(line)
                code = child.wait()
            except BaseException:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=5)
                raise
            finally:
                child.stdout.close()
        stages.append({'stage': name, 'exit': code, 'seconds': round(time.monotonic() - started, 2)})
        (work / 'stages.json').write_text(json.dumps(stages, indent=2) + '\n', encoding='utf-8')
        if code:
            raise ValueError(f'{name} failed; inspect {work / (name + ".log")}. Partial output was retained.')
        return ''.join(lines)

    for name, command in commands:
        run(name, command)
    stdout = run('actual-drill', [cache / 'debug/rustic-synthetic-drill', cache / 'debug/rustic', receipts], capture=True)
    output = Path(stdout.strip()).resolve()
    if output.parent != receipts or not output.is_dir():
        raise ValueError('The drill did not report its new receipt directory')
    code = review_run(output, work / 'review')
    if code:
        raise ValueError('Current files differ; inspect the retained review before another run')
    run('source-after', [sys.executable, '-B', ROOT / 'tools/verify_source.py'])
    print(f'Open {work / "review/report.html"}', flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog='Requires Python 3.12 and the recorded Rust/Cargo toolchain. Cached builds are reused; all output is retained.')
    parser.add_argument('output', type=Path, help='New work directory outside the source checkout; parent must exist')
    args = parser.parse_args()
    previous = os.umask(0o077)
    try:
        return execute(args.output)
    finally:
        os.umask(previous)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(f'Drill could not complete: {error}', file=sys.stderr)
        raise SystemExit(2) from error
