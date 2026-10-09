# Synthetic backup and restore drill

Create an inspectable local recovery exercise before considering a backup workflow for business data. This example builds a copied Rustic CLI against copied core/backend source, backs up generated files twice, checks the repository, restores the first recorded snapshot, and compares the restored paths and bytes. The drill retains its inputs, command logs, manifests, and result for review.

## Repository map

| Start here | Purpose |
| --- | --- |
| [drill/](drill/) | Executable recovery exercise adapted from upstream subprocess tests |
| [app/](app/) | Copied CLI with local Cargo bindings |
| [components/rustic-cli/](components/rustic-cli/) and [components/rustic-core-workspace/](components/rustic-core-workspace/) | Unchanged CLI/core/backend source and original licenses |
| [DESIGN.md](DESIGN.md) and [PROVENANCE.md](PROVENANCE.md) | Exercise design, reuse boundary and exact pinned revisions |
| [VERIFICATION.md](VERIFICATION.md) and [verification-summary.json](verification-summary.json) | Observed checks, cache reuse and unverified conditions |
| [composition.diff](composition.diff) and [source-manifest.json](source-manifest.json) | Local dependency binding changes and copied-source identities |

Copied upstream guides retain their original site/license-relative routes, including some links that do not resolve from their nested GitHub location. For complete upstream documentation, use the pinned [Rustic CLI repository](https://github.com/rustic-rs/rustic/tree/143d073f6039fcf29b64191ceb36c926744b6fe4) and [Rustic core repository](https://github.com/rustic-rs/rustic_core/tree/6fa7b56ebc750c6af0e6bc6bbe90c1781b60a38d). This root README is the entry point for the assembled drill, rather than the retained upstream app README.

## Run the local example

Use Rust/Cargo 1.99.0 and Python 3.12 on Linux. The recorded environment is Ubuntu 24.04. Cargo uses the checked-in lockfiles; registry dependencies are normal Cargo downloads. The selected graph contains native crates, whose required build tools depend on the features and cached artifacts. This verification does not establish minimum native prerequisites.

The staged reproduction reuses both the Cargo registry cache and an existing CLI build target after verifying that the staged app bytes and copied component identities match the verified composition. Cargo executes the staged manifest; the drill has a separate build target and a new synthetic output directory. This differs from the procedure below with a wholly fresh CLI target. A fresh CLI target, fresh dependency download, and remote CI are not verified by this staging run. See [verification-summary.json](verification-summary.json) for the actual result.

From the repository directory in a POSIX shell, create a separate build/output directory:

```sh
python3 tools/verify_source.py
BUILD_PARENT=$(mktemp -d)
mkdir "$BUILD_PARENT/receipts"
cargo build --manifest-path app/Cargo.toml --locked --no-default-features --target-dir "$BUILD_PARENT/cli"
cargo test --manifest-path drill/Cargo.toml --locked --target-dir "$BUILD_PARENT/drill"
cargo build --manifest-path drill/Cargo.toml --locked --target-dir "$BUILD_PARENT/drill"
"$BUILD_PARENT/drill/debug/rustic-synthetic-drill" "$BUILD_PARENT/cli/debug/rustic" "$BUILD_PARENT/receipts"
python3 tools/verify_source.py
```

The runner prints the new receipt directory. Open its `result.json`, `source-manifest.json`, `restore-manifest.json`, and command stdout/stderr files. This additional read command prints the stable acceptance fields from every run under the new output parent:

```sh
python3 - "$BUILD_PARENT/receipts" <<'PY'
import json
import sys
from pathlib import Path
for path in sorted(Path(sys.argv[1]).glob("rustic-drill-*/result.json")):
    result = json.loads(path.read_text())
    keys = ["status", "repeat_data_added_files", "repeat_data_added", "repeat_data_added_packed",
            "read_data_check", "wrong_password_rejected", "digest_manifest_match", "literal_bytes_match"]
    print(json.dumps({key: result[key] for key in keys}, indent=2))
PY
```

The observed acceptance output was:

```json
{
  "status": "passed",
  "repeat_data_added_files": 0,
  "repeat_data_added": 0,
  "repeat_data_added_packed": 0,
  "read_data_check": "passed",
  "wrong_password_rejected": true,
  "digest_manifest_match": true,
  "literal_bytes_match": true
}
```

The fixture contains five regular files and two directories: binary bytes, repeated content, an empty file, Unicode path/content, and an empty directory. Snapshot IDs and the executed CLI SHA-256 are retained in each result. The zero-added-data fields concern repository file/tree data on the repeated backup; the run still creates a second snapshot record.

## How the source is used

`app/` is the copied Rustic CLI. Its two Cargo files connect `rustic_core`, `rustic_backend`, and test-support `rustic_testing` to the unchanged `components/rustic-core-workspace/` source. `drill/src/main.rs` adapts the copied CLI subprocess tests into an executable exercise. Every init, backup, read-data check, wrong-password attempt, and restore runs the actual composed CLI. The drill supplies synthetic inputs and verifies results; Rustic owns the backup engine, repository storage, and cryptography.

The original 195-file CLI and 331-file core workspace copies remain in `components/`. Their source manifests, original test copies, licenses, and adaptation diffs are included. See [PROVENANCE.md](PROVENANCE.md) for exact pins and [VERIFICATION.md](VERIFICATION.md) for the original → duplicate → composition checks and staged reproduction.

## Research background

Sean Quinlan and Sean Dorward, [Venti: A New Approach to Archival Data Storage](https://www.usenix.org/conference/fast-02/venti-new-approach-archival-data-storage), FAST 2002, describe content-addressed blocks and coalescing duplicate content. That storage property provides context for this drill's repeated-backup check: the copied Rustic engine reports no new file/tree data on the second backup of an unchanged input. The command flow and acceptance checks come from the pinned Rustic implementation and tests, rather than a new implementation of Venti. The drill checks restored paths and literal bytes; it does not reproduce Venti's performance results or establish a write-once storage policy.

## Scope and handling

The executable accepts only a CLI path and an existing output parent. It creates a new child with atomic directory creation, uses a generated password and isolated profile/cache, retains all output, and has no deletion command. It rejects an existing or overlapping restore destination. It does not accept user-data source paths.

The demonstrated scope is synthetic regular files and directories on Linux. It does not verify symlinks, special files, filesystem metadata, real business data, cross-platform recovery, interrupted writes, power loss, concurrent operations, remote/cloud repositories, retention, or production readiness. The backend's default transport features remain compiled; `--no-default-features` disables CLI defaults only. This procedure uses the local backend exclusively.

The adaptation uses Apache-2.0 OR MIT. Exact upstream license files are retained at the root and in the copied source directories; see [LICENSE.md](LICENSE.md). No account, external repository, deployment, or publication is needed for the drill.
