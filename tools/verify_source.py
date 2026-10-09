"""Read-only checks of the pinned component copies and recorded adaptations.

Reuses the file-size/SHA-256 manifest comparison pattern from the inspected
transactional-outbox source-copy verifier; adds Git blob identity for Rustic.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def check_tree(relative, entries):
    directory = ROOT / relative
    expected = {entry["path"] for entry in entries}
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    assert actual == expected, (relative, sorted(expected - actual), sorted(actual - expected))
    for entry in entries:
        path = directory / entry["path"]
        assert not path.is_symlink(), path
        data = path.read_bytes()
        assert len(data) == entry["bytes"], path
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], path
        if "git_blob_sha1" in entry:
            blob = f"blob {len(data)}\0".encode() + data
            assert hashlib.sha1(blob).hexdigest() == entry["git_blob_sha1"], path
    return len(entries)


source = load("source-manifest.json")
components = {item["name"]: check_tree(item["duplicate_root"], item["entries"])
              for item in source["repositories"]}
app = load("app-source-manifest.json")
app_count = check_tree(app["root"], app["entries"])
changed = [entry["path"] for entry in app["entries"]
           if (ROOT / "app" / entry["path"]).read_bytes()
           != (ROOT / app["source_component"] / entry["path"]).read_bytes()]
assert sorted(changed) == ["Cargo.lock", "Cargo.toml"], changed
original = load("drill/source-copy-manifest.json")
original_entries = [entry | {"path": entry["path"].removeprefix("original/")}
                    for entry in original["copied_files"]]
original_count = check_tree("drill/original", original_entries)
adaptation = load("drill/adaptation.json")
for entry in adaptation["entries"]:
    data = (ROOT / "drill" / entry["path"]).read_bytes()
    assert len(data) == entry["bytes"], entry["path"]
    assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
for name in ("LICENSE-MIT", "LICENSE-APACHE"):
    assert (ROOT / name).read_bytes() == (ROOT / "components/rustic-cli" / name).read_bytes(), name
assert (ROOT / ".gitattributes").read_bytes() == b"* -text\n"
print(json.dumps({"status": "passed", "component_files": components,
                  "app_files": app_count, "app_unchanged_files": app_count - len(changed),
                  "app_changed_files": sorted(changed), "copied_original_test_and_license_files": original_count,
                  "drill_recorded_adaptation_files": len(adaptation["entries"]),
                  "component_bytes_and_git_blob_identities": "matched",
                  "root_license_bytes": "matched"}, indent=2))
