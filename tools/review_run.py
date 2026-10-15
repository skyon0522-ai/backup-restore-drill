"""Read-only current-file review of a completed synthetic Rustic drill (Python 3.12)."""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
from html import escape
from pathlib import Path, PurePosixPath


def read_json(path):
    with path.open('rb') as stream:
        data = stream.read(1_048_577)
    if len(data) > 1_048_576:
        raise ValueError(f'{path.name} exceeds the 1 MiB review limit')
    return json.loads(data), hashlib.sha256(data).hexdigest()


def validate_manifest(value):
    if not isinstance(value, list) or not value:
        raise ValueError('The saved manifest must be a nonempty array')
    entries = {}
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str):
            raise ValueError('Invalid saved manifest entry')
        name = item['path']
        if (not name or PurePosixPath(name).is_absolute() or '\\' in name or any(ord(char) < 32 or ord(char) == 127 for char in name)
                or any(part in ('', '.', '..') for part in name.split('/')) or name in entries):
            raise ValueError('Manifest paths must be unique, relative and non-traversing')
        if item.get('type') == 'directory' and set(item) == {'path', 'type'}:
            pass
        elif item.get('type') == 'file' and set(item) == {'path', 'type', 'size', 'sha256'}:
            if type(item['size']) is not int or item['size'] < 0 or not isinstance(item['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', item['sha256']):
                raise ValueError('Invalid file size or SHA-256 in saved manifest')
        else:
            raise ValueError('Unsupported manifest type or fields')
        entries[name] = dict(item)
    return entries


def current_manifest(directory):
    if not stat.S_ISDIR(directory.lstat().st_mode):
        raise ValueError(f'{directory.name} must be a real directory, not a symlink')
    entries = {}

    def visit(at):
        for path in sorted(at.iterdir()):
            name = path.relative_to(directory).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                entries[name] = {'path': name, 'type': 'directory'}
                visit(path)
            elif stat.S_ISREG(mode):
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                entries[name] = {'path': name, 'type': 'file', 'size': path.stat().st_size, 'sha256': digest}
            else:
                raise ValueError('Symlinks and special files are outside this review')
    visit(directory)
    return entries


def equal_bytes(first, second):
    with first.open('rb') as left, second.open('rb') as right:
        while True:
            a, b = left.read(65_536), right.read(65_536)
            if a != b:
                return False
            if not a:
                return True


def inspect_run(root):
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError('The run must be a real directory, not a symlink')
    for name in ('result.json', 'source-manifest.json'):
        if not stat.S_ISREG((root / name).lstat().st_mode):
            raise ValueError('Recorded JSON must be a regular file, not a symlink')
    original, result_hash = read_json(root / 'result.json')
    saved, manifest_hash = read_json(root / 'source-manifest.json')
    expected = validate_manifest(saved)
    if not isinstance(original, dict) or original.get('manifest') != saved or original.get('status') != 'passed':
        raise ValueError('A consistent completed drill result is required')
    for name in ('cli_sha256', 'restored_snapshot_id', 'second_snapshot_id'):
        if not isinstance(original.get(name), str) or not re.fullmatch('[a-f0-9]{64}', original[name]):
            raise ValueError('Invalid recorded binary digest or snapshot ID')
    if original['restored_snapshot_id'] == original['second_snapshot_id']:
        raise ValueError('Two distinct recorded snapshots are required')
    for name in ('repeat_data_added_files', 'repeat_data_added', 'repeat_data_added_packed'):
        if type(original.get(name)) is not int or original[name] != 0:
            raise ValueError('The recorded repeat-backup gate did not pass')
    if original.get('read_data_check') != 'passed' or any(original.get(name) is not True for name in (
            'wrong_password_rejected', 'digest_manifest_match', 'literal_bytes_match')):
        raise ValueError('The recorded drill gates are incomplete')
    source = current_manifest(root / 'source')
    restored = current_manifest(root / 'restore')
    literal = all(source.get(name, {}).get('type') == restored.get(name, {}).get('type') == 'file'
        and equal_bytes(root / 'source' / name, root / 'restore' / name)
        for name, entry in expected.items() if entry['type'] == 'file')
    checks = {'current_source_matches_saved': source == expected,
              'current_restore_matches_saved': restored == expected,
              'current_literal_file_bytes_match': literal}
    recorded = {name: original[name] for name in ('status', 'cli_sha256', 'restored_snapshot_id',
        'second_snapshot_id', 'repeat_data_added_files', 'repeat_data_added', 'repeat_data_added_packed',
        'read_data_check', 'wrong_password_rejected', 'digest_manifest_match', 'literal_bytes_match')}
    review = {'schema_version': 1, 'status': 'matched' if all(checks.values()) else 'mismatch',
        'checks': checks, 'recorded_drill_status': 'passed', 'input_result_sha256': result_hash,
        'input_saved_manifest_sha256': manifest_hash,
        'expected_regular_files': sum(row['type'] == 'file' for row in expected.values()),
        'expected_directories': sum(row['type'] == 'directory' for row in expected.values()),
        'expected_file_bytes': sum(row.get('size', 0) for row in expected.values()),
        'changed_paths': [name for name in sorted(set(expected) | set(source) | set(restored))
            if expected.get(name) != source.get(name) or expected.get(name) != restored.get(name)],
        'scope': 'Current generated source/restore paths, sizes, SHA-256 and literal file bytes only; editable local records are not authenticated.'}
    return review, recorded, expected, source, restored


def describe(entry):
    if entry is None:
        return 'Missing'
    if entry['type'] == 'directory':
        return 'Directory'
    return f"{entry['size']} bytes · {entry['sha256']}"


def render(review, recorded, expected, source, restored):
    rows = []
    for name in sorted(set(expected) | set(source) | set(restored)):
        state = 'Matches' if expected.get(name) == source.get(name) == restored.get(name) else 'Differs'
        cells = [name, describe(expected.get(name)), describe(source.get(name)), describe(restored.get(name)), state]
        rows.append('<tr>' + ''.join('<td>' + escape(cell) + '</td>' for cell in cells) + '</tr>')
    cards = ''.join(f'<section><h2>{label}</h2><p>{"Passed" if review["checks"][key] else "Failed"}</p></section>'
        for key, label in (('current_source_matches_saved', 'Source vs saved baseline'),
            ('current_restore_matches_saved', 'Restore vs saved baseline'),
            ('current_literal_file_bytes_match', 'Source vs restore bytes')))
    headline = 'Current files match' if review['status'] == 'matched' else 'Current files do not match'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>Backup restore review</title><style>
body{{margin:0;font:16px/1.6 system-ui,sans-serif;background:#f4f7fb;color:#182736}}
main{{max-width:78rem;margin:auto;padding:2rem 1rem}}h1{{line-height:1.2}}p{{max-width:78ch}}
.panel{{padding:1.5rem;border:1px solid #d1dce8;border-radius:.6rem;background:white;margin:1rem 0;overflow-wrap:anywhere}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem}}.grid section{{background:#eaf1f8;padding:1rem}}
.grid h2{{font-size:1rem;margin:0 0 .5rem}}.grid p{{font-weight:600;margin:0}}
.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:68rem}}th,td{{text-align:left;padding:.7rem;border-bottom:1px solid #d1dce8;vertical-align:top}}thead{{background:#eaf1f8}}
td:first-child,td:last-child,th{{white-space:nowrap}}td{{font-family:ui-monospace,monospace;overflow-wrap:anywhere}}summary{{cursor:pointer;font-weight:600}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
a{{color:#155b87}}:focus-visible{{outline:3px solid #155b87;outline-offset:2px}}
@media(max-width:650px){{main{{padding:1rem .5rem}}.panel{{padding:1rem}}.grid{{grid-template-columns:1fr}}}}
@media print{{body{{background:white}}main{{max-width:none;padding:0}}.panel{{border:0;padding:0}}}}
</style></head><body><main><h1>Backup restore review</h1>
<p>Current-file checks for one completed synthetic Rustic exercise. No backup, restore or deletion command is run by this review.</p>
<section class="panel"><h2>{headline}</h2><div class="grid">{cards}</div>
<p>{review['expected_regular_files']} expected regular files · {review['expected_directories']} expected directories · {review['expected_file_bytes']} expected file bytes</p></section>
<section class="panel"><h2>Recorded exercise</h2><p>Recorded drill: passed. This is the saved result, separate from the current-file checks above.</p>
<p>Restored first snapshot: <code>{recorded['restored_snapshot_id']}</code><br>Second snapshot: <code>{recorded['second_snapshot_id']}</code></p>
<p>Repeat file/tree data added: 0. The second backup still creates a snapshot record. The saved run reports a successful read-data check and rejection of the wrong password.</p>
<p>Rustic binary SHA-256: <code>{recorded['cli_sha256']}</code></p></section>
<section class="panel"><h2>Current manifest comparison</h2><p>Changed paths: {escape(', '.join(review['changed_paths']) or 'None')}</p>
<div class="scroll" tabindex="0" role="region" aria-label="Manifest comparison"><table><thead><tr><th scope="col">Path</th><th scope="col">Saved baseline</th><th scope="col">Current source</th><th scope="col">Current restore</th><th scope="col">Result</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p>Swipe sideways on small screens, or focus the table and use the arrow keys.</p></section>
<details class="panel"><summary>Evidence and limits</summary><pre>{escape(json.dumps(review, indent=2, ensure_ascii=False))}</pre>
<p><a href="review.json">Current review</a> · <a href="recorded-checks.json">Recorded check fields</a> · <a href="saved-manifest.json">Saved baseline</a> · <a href="current-source.json">Current source</a> · <a href="current-restore.json">Current restore</a></p>
<p>Names, sizes and hashes are retained; file contents, passwords, backup keys and the machine-specific CLI path are not copied. The original run remains separate.</p>
</details><section class="panel"><h2>Scope</h2><p>The drill uses generated fixtures and a fixed public demo password. This review does not authenticate editable records or prove production recovery, metadata/symlink/special-file fidelity, power-loss safety, concurrent-read consistency or cloud recovery.</p></section>
</main></body></html>'''


def review_run(root, output):
    root = Path(root)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a new review directory; existing paths are not replaced')
    resolved_root, resolved_output = root.resolve(), output.resolve()
    if resolved_output.is_relative_to(resolved_root) or resolved_root.is_relative_to(resolved_output):
        raise ValueError('The review directory must be outside the original run')
    review, recorded, expected, source, restored = inspect_run(root)
    output.mkdir(mode=0o700)
    values = {'review.json': review, 'recorded-checks.json': recorded,
        'saved-manifest.json': [expected[name] for name in sorted(expected)],
        'current-source.json': [source[name] for name in sorted(source)],
        'current-restore.json': [restored[name] for name in sorted(restored)]}
    for name, value in values.items():
        with os.fdopen(os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    with os.fdopen(os.open(output / 'report.html', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
        stream.write(render(review, recorded, expected, source, restored))
    return 0 if review['status'] == 'matched' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog='Exit 0: matched; 1: mismatch; 2: invalid input or incomplete output.')
    parser.add_argument('run', type=Path, help='A completed synthetic drill directory')
    parser.add_argument('output', type=Path, help='A new review directory outside the run; its parent must exist')
    args = parser.parse_args()
    code = review_run(args.run, args.output)
    print(args.output.resolve() / 'report.html')
    return code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(f'Review could not complete: {error}. A partial new output may remain; existing output is never replaced.', file=sys.stderr)
        raise SystemExit(2) from error
