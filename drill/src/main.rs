//! Adapted from rustic CLI tests/backup_restore.rs: init, backup twice, check, restore, compare.
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    env,
    error::Error,
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn fail(message: &str) -> Box<dyn Error> {
    message.to_owned().into()
}

fn run(binary: &Path, root: &Path, name: &str, args: &[&str]) -> Result<String> {
    run_with_password(binary, root, name, args, &root.join("password"), true)
}

fn run_with_password(
    binary: &Path,
    root: &Path,
    name: &str,
    args: &[&str],
    password: &Path,
    should_succeed: bool,
) -> Result<String> {
    let mut command = Command::new(binary);
    command.env_clear();
    if let Some(home) = env::var_os("HOME") {
        command.env("HOME", home);
    }
    let output = command
        .env("XDG_CONFIG_HOME", root.join("config"))
        .env("XDG_CACHE_HOME", root.join("cache"))
        .arg("-r")
        .arg(root.join("repo"))
        .arg("--password-file")
        .arg(password)
        .arg("--no-progress")
        .arg("--use-profile")
        .arg(root.join("empty-profile"))
        .arg("--cache-dir")
        .arg(root.join("cache"))
        .args(args)
        .output()?;
    fs::write(root.join(format!("{name}.stdout")), &output.stdout)?;
    fs::write(root.join(format!("{name}.stderr")), &output.stderr)?;
    if output.status.success() != should_succeed {
        return Err(fail(&format!(
            "{name} returned unexpected status ({}); see retained stdout/stderr",
            output.status
        )));
    }
    Ok(String::from_utf8(output.stdout)?)
}

fn manifest(dir: &Path) -> Result<Value> {
    fn walk(base: &Path, at: &Path, entries: &mut Vec<Value>) -> Result<()> {
        let mut paths = fs::read_dir(at)?
            .map(|e| e.map(|e| e.path()))
            .collect::<std::io::Result<Vec<_>>>()?;
        paths.sort();
        for path in paths {
            let relative = path
                .strip_prefix(base)?
                .to_string_lossy()
                .replace('\\', "/");
            let meta = fs::symlink_metadata(&path)?;
            if meta.is_dir() {
                entries.push(json!({"path": relative, "type": "directory"}));
                walk(base, &path, entries)?;
            } else if meta.is_file() {
                let bytes = fs::read(&path)?;
                entries.push(
                    json!({"path": relative, "type": "file", "size": bytes.len(),
                    "sha256": format!("{:x}", Sha256::digest(&bytes))}),
                );
            } else {
                return Err(fail("unexpected symlink or special file"));
            }
        }
        Ok(())
    }
    let mut entries = Vec::new();
    walk(dir, dir, &mut entries)?;
    Ok(json!(entries))
}

fn literal_bytes_match(source: &Path, restored: &Path, source_manifest: &Value) -> Result<bool> {
    for entry in source_manifest
        .as_array()
        .ok_or_else(|| fail("manifest is not an array"))?
    {
        if entry["type"] == "file" {
            let path = entry["path"]
                .as_str()
                .ok_or_else(|| fail("manifest path missing"))?;
            if fs::read(source.join(path))? != fs::read(restored.join(path))? {
                return Ok(false);
            }
        }
    }
    Ok(true)
}

fn repeat_backup_added_nothing(summary: &Value) -> bool {
    ["data_added_files", "data_added", "data_added_packed"]
        .iter()
        .all(|field| summary[*field].as_u64() == Some(0))
}

fn check_log_clean(stderr: &str) -> bool {
    !stderr.contains("WARN") && !stderr.contains("ERROR")
}

fn ensure_fresh_destination(source: &Path, repo: &Path, destination: &Path) -> Result<()> {
    if destination.exists() {
        return Err(fail("restore destination must not exist"));
    }
    if destination.starts_with(source)
        || source.starts_with(destination)
        || destination.starts_with(repo)
        || repo.starts_with(destination)
    {
        return Err(fail("restore destination overlaps source or repository"));
    }
    Ok(())
}

fn fresh_root(parent: &Path) -> Result<PathBuf> {
    if !parent.is_dir() {
        return Err(fail("output parent must be an existing directory"));
    }
    let parent = parent.canonicalize()?;
    for attempt in 0..16 {
        let nanos = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
        let root = parent.join(format!(
            "rustic-drill-{}-{nanos}-{attempt}",
            std::process::id()
        ));
        match fs::create_dir(&root) {
            Ok(()) => return Ok(root),
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err(e.into()),
        }
    }
    Err(fail("could not create a fresh output directory"))
}

fn drill(binary: &Path, parent: &Path) -> Result<PathBuf> {
    let binary = binary.canonicalize()?;
    if !binary.is_file() {
        return Err(fail("Rustic CLI path must be a file"));
    }
    let cli_sha256 = format!("{:x}", Sha256::digest(fs::read(&binary)?));
    let root = fresh_root(parent)?;
    if binary.starts_with(&root) {
        return Err(fail("CLI and drill workspace overlap"));
    }
    fs::write(root.join("empty-profile.toml"), "")?;
    fs::write(root.join("password"), "synthetic-drill-only\n")?;
    let source = root.join("source");
    fs::create_dir_all(source.join("nested/空のフォルダ"))?;
    fs::write(source.join("nested/日本語.txt"), "復元テスト\n".as_bytes())?;
    fs::write(source.join("binary.bin"), [0, 1, 2, 255, 0, 127])?;
    fs::write(source.join("empty.dat"), [])?;
    fs::write(source.join("copy-a.txt"), b"same bytes")?;
    fs::write(source.join("nested/copy-b.txt"), b"same bytes")?;
    let before = manifest(&source)?;
    fs::write(
        root.join("source-manifest.json"),
        serde_json::to_vec_pretty(&before)?,
    )?;
    run(&binary, &root, "init", &["init"])?;
    let source_arg = source
        .to_str()
        .ok_or_else(|| fail("non-UTF-8 source path"))?;
    let first: Value = serde_json::from_str(&run(
        &binary,
        &root,
        "backup-1",
        &["backup", "--json", "--as-path", "/", source_arg],
    )?)?;
    let id = first["id"]
        .as_str()
        .ok_or_else(|| fail("backup JSON has no snapshot id"))?;
    if id.len() != 64 || !id.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(fail("invalid snapshot ID"));
    }
    let second: Value = serde_json::from_str(&run(
        &binary,
        &root,
        "backup-2",
        &["backup", "--json", "--as-path", "/", source_arg],
    )?)?;
    if second["id"].as_str() == Some(id) {
        return Err(fail("second backup did not create another snapshot"));
    }
    if !repeat_backup_added_nothing(&second["summary"]) {
        return Err(fail("repeat backup added data to repository"));
    }
    fs::write(
        root.join("wrong-password"),
        "incorrect-synthetic-password\n",
    )?;
    run_with_password(
        &binary,
        &root,
        "wrong-password",
        &["snapshots", "--json"],
        &root.join("wrong-password"),
        false,
    )?;
    if !fs::read_to_string(root.join("wrong-password.stderr"))?.contains("No suitable key found") {
        return Err(fail(
            "wrong-password command failed for an unexpected reason",
        ));
    }
    run(&binary, &root, "check", &["check", "--read-data"])?;
    if !check_log_clean(&fs::read_to_string(root.join("check.stderr"))?) {
        return Err(fail("read-data check reported WARN or ERROR"));
    }
    let destination = root.join("restore");
    ensure_fresh_destination(&source, &root.join("repo"), &destination)?;
    let dest_arg = destination
        .to_str()
        .ok_or_else(|| fail("non-UTF-8 restore path"))?;
    run(&binary, &root, "restore", &["restore", id, dest_arg])?;
    let after = manifest(&destination)?;
    fs::write(
        root.join("restore-manifest.json"),
        serde_json::to_vec_pretty(&after)?,
    )?;
    if before != after {
        return Err(fail("restored files differ from source manifest"));
    }
    if !literal_bytes_match(&source, &destination, &before)? {
        return Err(fail("restored file bytes differ from source"));
    }
    fs::write(
        root.join("result.json"),
        serde_json::to_vec_pretty(&json!({
            "status": "passed", "cli": binary, "cli_sha256": cli_sha256,
            "restored_snapshot_id": id,
            "second_snapshot_id": second["id"],
            "repeat_data_added_files": second["summary"]["data_added_files"],
            "repeat_data_added": second["summary"]["data_added"],
            "repeat_data_added_packed": second["summary"]["data_added_packed"],
            "read_data_check": "passed", "wrong_password_rejected": true,
            "digest_manifest_match": true, "literal_bytes_match": true, "manifest": before
        }))?,
    )?;
    Ok(root)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn changed_restored_bytes_are_rejected() -> Result<()> {
        let temp = tempfile::tempdir()?;
        let source = temp.path().join("source");
        let restored = temp.path().join("restore");
        fs::create_dir(&source)?;
        fs::create_dir(&restored)?;
        fs::write(source.join("file"), b"same")?;
        fs::write(restored.join("file"), b"same")?;
        let original = manifest(&source)?;
        assert!(literal_bytes_match(&source, &restored, &original)?);
        fs::write(restored.join("file"), b"tampered")?;
        assert!(!literal_bytes_match(&source, &restored, &original)?);
        Ok(())
    }

    #[test]
    fn destination_guard_rejects_existing_and_overlap() -> Result<()> {
        let temp = tempfile::tempdir()?;
        let source = temp.path().join("source");
        let repo = temp.path().join("repo");
        fs::create_dir(&source)?;
        fs::create_dir(&repo)?;
        let existing = temp.path().join("existing");
        fs::create_dir(&existing)?;
        fs::write(existing.join("keep"), b"do not touch")?;
        assert!(ensure_fresh_destination(&source, &repo, &existing).is_err());
        assert_eq!(fs::read(existing.join("keep"))?, b"do not touch");
        assert!(ensure_fresh_destination(&source, &repo, &source.join("nested")).is_err());
        assert!(ensure_fresh_destination(&source, &repo, &repo.join("nested")).is_err());
        assert!(ensure_fresh_destination(&source, &repo, &temp.path().join("restore")).is_ok());
        Ok(())
    }

    #[test]
    fn repeat_backup_rejects_nonzero_packed_or_uncompressed_bytes() {
        let zero = json!({"data_added_files": 0, "data_added": 0, "data_added_packed": 0});
        assert!(repeat_backup_added_nothing(&zero));
        assert!(!repeat_backup_added_nothing(
            &json!({"data_added_files": 0, "data_added": 0, "data_added_packed": 1})
        ));
        assert!(!repeat_backup_added_nothing(
            &json!({"data_added_files": 0, "data_added": 1, "data_added_packed": 0})
        ));
    }

    #[test]
    fn read_data_check_rejects_warning_and_error_logs() {
        assert!(check_log_clean("[INFO] checked data"));
        assert!(!check_log_clean("[WARN] check warning"));
        assert!(!check_log_clean("[ERROR] check error"));
    }
}

fn main() {
    let args: Vec<_> = env::args_os().collect();
    if args.len() != 3 {
        eprintln!("usage: rustic-synthetic-drill RUSTIC_CLI EXISTING_OUTPUT_PARENT");
        std::process::exit(2);
    }
    match drill(Path::new(&args[1]), Path::new(&args[2])) {
        Ok(root) => println!("{}", root.display()),
        Err(e) => {
            eprintln!("drill failed: {e}");
            std::process::exit(1);
        }
    }
}
