# Source analysis, duplication and bounded adaptation

| Copied OSS source | Exact revision | Retained files | Executed responsibility |
| --- | --- | ---: | --- |
| [Rustic CLI](https://github.com/rustic-rs/rustic/tree/143d073f6039fcf29b64191ceb36c926744b6fe4) | `143d073f6039fcf29b64191ceb36c926744b6fe4` | 195 | CLI commands, configuration, snapshot selection and subprocess contracts |
| [Rustic core workspace](https://github.com/rustic-rs/rustic_core/tree/6fa7b56ebc750c6af0e6bc6bbe90c1781b60a38d) | `6fa7b56ebc750c6af0e6bc6bbe90c1781b60a38d` | 331 | Backup/restore engine, repository checks, local backend, and copied testing support |

Both components are Apache-2.0 OR MIT. Their complete tracked source trees, Cargo files, fixtures, workspace members, documentation, and license files are retained unchanged under `components/`. [source-manifest.json](source-manifest.json) records every path, original Git mode, byte length, Git blob SHA-1, and SHA-256. No tracked source symlinks were present. The CLI tracks `build.sh` as executable; the tested commands do not invoke that script. Git mode restoration after a new public checkout has not been exercised.

## Inspected original implementation

- [`tests/backup_restore.rs`](components/rustic-cli/tests/backup_restore.rs) starts the built CLI as a subprocess, initializes a temporary repository, backs up the fixture, restores it, and compares the directory tree. Its separate read-data test performs two backups, requires `Added to the repo: 0 B`, and rejects `WARN`/`ERROR` check output.
- [`tests/repositories.rs`](components/rustic-cli/tests/repositories.rs) opens and unpacks the checked-in `src-snapshot.tar.gz` fixture. The original selected tests were executed before adaptation.
- [`src/commands/backup.rs`](components/rustic-cli/src/commands/backup.rs) formats the repeated-backup repository-byte result from `data_added_packed`; the copied core snapshot type defines the summary fields. The drill now checks all three zero-added-data fields explicitly.
- [`src/commands/check.rs`](components/rustic-cli/src/commands/check.rs) evaluates the core check result; [`crates/backend/src/local.rs`](components/rustic-core-workspace/crates/backend/src/local.rs) supplies filesystem storage with temporary-file sync/rename. These implementations are executed through the CLI, rather than replaced by a new backup core.

## Composition of actual copied source

`app/` was first verified as a byte-for-byte copy of all 195 CLI files. Its 193 non-Cargo files remain identical. Only `Cargo.toml` and the resulting `Cargo.lock` change: core, backend and testing dependencies now resolve to the sibling copied core workspace. [composition.diff](composition.diff) records the complete two-file delta, and [app-source-manifest.json](app-source-manifest.json) records the final app hashes and lock comparison.

The original CLI lock contains Git core/backend dependencies and a separate registry core through registry testing support. The composed lock removes those four package instances, adds local core/backend/testing, and retains the versions/checksums of 755 registry packages without adding registry packages. Locked metadata confirmed the CLI, core, backend and testing manifests resolve locally. Backend defaults `opendal`, `rest` and `rclone` remain active. No copied component manifest or engine code was changed.

## Adaptation of the copied tests

`drill/original/backup_restore.rs`, `repositories.rs`, and the two license files were copied unchanged from the pinned CLI. [drill/source-copy-manifest.json](drill/source-copy-manifest.json) identifies their bytes. [drill/ORIGINAL_TO_ADAPTED.patch](drill/ORIGINAL_TO_ADAPTED.patch) shows the full original test → executable drill change; [drill/adaptation.json](drill/adaptation.json) records the current source, lock, and patch hashes.

The adaptation retains real CLI subprocess operations. It replaces the upstream fixture with generated regular files/directories, restores the full first snapshot ID observed in `backup --json`, isolates output/profile/cache/password paths, rejects an existing or overlapping restore destination, and retains logs. It adds path/type/size/SHA-256 comparisons plus direct byte equality and a wrong-password rejection check. It provides no replacement backup, storage, encryption, or check implementation.

Independent review findings `RUSTIC-01` and `RUSTIC-02` resulted in small acceptance-gate fixes: the repeated-backup gate requires `data_added_files`, `data_added`, and `data_added_packed` to be zero; the read-data gate rejects `WARN` or `ERROR` in retained stderr. Focused regressions cover those fixes. `RUSTIC-03` remains the explicit regular-file/directory scope limitation.

The root Apache/MIT license files preserve the CLI's original notice, including Copyright (c) 2022 Alexander Weiss. Copied core and original-test license files remain in place. Registry packages retain their independent licenses. Git metadata, original comparison checkouts, task-local logs, generated receipts, binaries, build targets, and dependency caches are excluded from this public source tree.
