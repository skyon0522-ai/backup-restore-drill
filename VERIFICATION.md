# Observed verification: 2026-10-09

The historical local comparisons used Ubuntu 24.04, Rust/Cargo 1.99.0, the checked-in locks, and a task-local Cargo dependency cache. Original, duplicate, and composed CLI tests used separate target directories. Inherited `RUSTIC_*` settings were removed, an empty absolute profile was selected, and repository caches were isolated. The composed tests and drill used the existing cache offline. No fresh dependency-download claim is made.

## Original → unchanged duplicate → composed application

| Stage | Executed contract | Observed result |
| --- | --- | --- |
| Original pinned CLI | `cargo test --locked --no-default-features --test backup_restore test_backup_and_restore_passes` | Passed |
| Original pinned CLI | `cargo test --locked --no-default-features --test backup_restore test_backup_and_check_passes` | Passed |
| Unchanged CLI duplicate | Both exact commands above | Passed from a separate compiled target |
| Composed local-path CLI | Both exact commands above | Passed from another compiled target; local core/backend/testing resolved |
| Corrected synthetic drill | `cargo test --locked --offline` | Four focused tests passed |
| Corrected synthetic drill | Actual composed CLI subprocess exercise | Passed; first selected snapshot restored and byte comparisons matched |

Historical source checks verified all 526 original/duplicate blobs against byte length, SHA-256 and Git blob SHA-1, with pinned clean Git checkouts. The app retained 193 identical paths and only the two expected Cargo changes; 755 retained registry package versions/checksums were unchanged. The composed CLI reported `rustic 0.11.4`, SHA-256 `e1770047a1af7e3d591eaa552c54f019a93e40d5a70c806e29695f0acb3c7fee`. Compact historical evidence and current source hashes are retained in [verification-summary.json](verification-summary.json); machine-specific logs remain outside this source tree.

## What the drill gates prove

The run created a new synthetic workspace, initialized a local repository, backed up the five-file/two-directory fixture twice, rejected a wrong password for the expected key-selection reason, performed `check --read-data`, and restored the full first snapshot ID after the second backup existed. It required:

1. Zero repeat `data_added_files`, `data_added`, and `data_added_packed`. A second snapshot record is still created.
2. Successful read-data check with no `WARN` or `ERROR` marker in retained stderr.
3. Equal recursive path/type/size/SHA-256 manifests, including the empty directory.
4. Equal literal bytes for every regular file, including binary data, duplicate content, Unicode content, and an empty file.

The four focused tests reject altered restore bytes, existing/overlapping destinations, nonzero packed or uncompressed repeat data, and warning/error check output. Independent review initially identified two missing gates; both were corrected and checked. Its synthetic-file limitation remains attached to the result.

## Reproduce from this source tree

Run the exact procedure in [README.md](README.md). `tools/verify_source.py` is read-only: it checks both complete component trees, the 195 app paths and exact two-file delta, unchanged copied original tests/licenses, recorded drill adaptation hashes, root license bytes, and byte-preserving `.gitattributes`. It derives from the already-used file-size/hash manifest comparison pattern, with Git blob checks for the Rustic entries.

The staged reproduction status, build/cache handling, command results and synthetic acceptance fields are recorded in [verification-summary.json](verification-summary.json). Generated workspaces and full runtime receipts are kept outside the staged tree. The workflow in `.github/workflows/checks.yml` runs the same source check, locked builds, four drill tests, and synthetic exercise. Remote CI has not run.

The staged source check, CLI build, four focused tests, drill build, restore exercise, README result-reader, and final source check all passed. The run reused both the registry cache and an existing CLI build target after checking source identity; Cargo compiled from the staged app manifest. The drill used a new target. A focused second drill retained its full logs in persistent local output after the initial temporary workspace became unavailable in a later WSL invocation. A wholly fresh CLI target and dependency download remain untested.

The checks establish only the demonstrated local synthetic behavior. They do not establish general backup fidelity, metadata/symlink/special-file handling, cross-platform behavior, real-user recovery, power-loss safety, concurrent operations, cloud recovery, throughput, or production readiness. No broader upstream suite was rerun for this staging step.
