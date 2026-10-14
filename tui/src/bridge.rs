//! Bridge to the Python `rapoo` CLI (subprocess, --json).
//!
//! v1 strategy: zero protocol duplication. The Rust TUI shells out to
//! `rapoo <cmd> --json` (or `./rapoo` from repo root) and parses JSON.
//! Native hidraw port is a v2 task behind `--native-hid`.

use anyhow::{anyhow, Context, Result};
use serde_json::Value;
use std::path::PathBuf;
use std::process::Command;

#[derive(Debug, Clone)]
pub struct Bridge {
    /// argv[0] for rapoo: e.g. "rapoo" or "/path/to/rapoo"
    pub rapoo_bin: String,
    pub profile: u8,
    pub timeout_s: f64,
}

impl Bridge {
    pub fn detect() -> Self {
        // Prefer repo-local launcher when CWD is inside the repo; else PATH.
        let repo_launcher = find_repo_launcher();
        let bin = repo_launcher
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_else(|| "rapoo".to_string());
        Bridge {
            rapoo_bin: bin,
            profile: 0,
            timeout_s: 10.0,
        }
    }

    fn run(&self, args: &[&str]) -> Result<String> {
        let mut cmd_args: Vec<String> =
            args.iter().map(|s| s.to_string()).collect();
        // inject --profile for commands that accept it
        let needs_profile = args.first().map(|c| {
            matches!(*c, "get" | "set" | "backup" | "restore")
        }).unwrap_or(false);
        if needs_profile && !args.contains(&"--profile") {
            cmd_args.push("--profile".into());
            cmd_args.push(self.profile.to_string());
        }
        let out = Command::new(&self.rapoo_bin)
            .args(&cmd_args)
            .output()
            .with_context(|| format!("spawn {}", self.rapoo_bin))?;
        let stdout = String::from_utf8_lossy(&out.stdout).to_string();
        let stderr = String::from_utf8_lossy(&out.stderr).to_string();
        if !out.status.success() {
            return Err(map_cli_error(&stderr, &stdout));
        }
        Ok(stdout)
    }

    pub fn run_json(&self, args: &[&str]) -> Result<Value> {
        let mut full: Vec<&str> = args.to_vec();
        let mut owned: Vec<String> = vec![];
        // append --json if not present and command supports it
        if !args.contains(&"--json")
            && matches!(args.first().copied(), Some("get") | Some("status") | Some("raw") | Some("pair"))
        {
            owned = args.iter().map(|s| s.to_string()).collect();
            owned.push("--json".into());
            full = owned.iter().map(|s| s.as_str()).collect();
        }
        let stdout = self.run(&full)?;
        serde_json::from_str(&stdout).context("parse rapoo --json output")
    }

    pub fn list_text(&self) -> Result<String> {
        self.run(&["list"])
    }

    pub fn get(&self) -> Result<Value> {
        self.run_json(&["get"])
    }

    pub fn status(&self) -> Result<Value> {
        let t = self.timeout_s.to_string();
        self.run_json(&["status", "--timeout", &t])
    }

    pub fn set(&self, extra: &[&str]) -> Result<String> {
        let mut args = vec!["set"];
        args.extend(extra.iter().copied());
        self.run(&args)
    }

    pub fn backup(&self, file: &str) -> Result<String> {
        self.run(&["backup", file])
    }

    pub fn restore(&self, file: &str) -> Result<String> {
        self.run(&["restore", file])
    }

    pub fn raw(&self, offset: &str, len: &str) -> Result<Value> {
        self.run_json(&["raw", "--offset", offset, "--length", len])
    }

    pub fn pair_query(&self) -> Result<Value> {
        self.run_json(&["pair", "--query"])
    }
}

fn find_repo_launcher() -> Option<PathBuf> {
    // Walk up from CWD looking for ./rapoo launcher + backend/rapoo/cli.py
    let mut dir = std::env::current_dir().ok()?;
    loop {
        if dir.join("rapoo").is_file() && dir.join("backend/rapoo/cli.py").is_file() {
            return Some(dir.join("rapoo"));
        }
        if !dir.pop() {
            return None;
        }
    }
}

fn map_cli_error(stderr: &str, stdout: &str) -> anyhow::Error {
    let msg = format!("{stderr}\n{stdout}").trim().to_string();
    if msg.contains("Permission denied") || msg.contains("hidraw") {
        anyhow!(
            "Permission denied on /dev/hidraw.\nInstall udev rule first:\n  ./install.sh\nThen unplug/replug the dongle.\n\n{msg}"
        )
    } else if msg.contains("No Rapoo") || msg.contains("interface 1") {
        anyhow!("No Rapoo config interface found.\nPlug in dongle/mouse, then replug.\n\n{msg}")
    } else if msg.contains("asleep") || msg.contains("No status report") {
        anyhow!("No status report — mouse may be asleep.\nMove the mouse, then retry (R).\n\n{msg}")
    } else {
        anyhow!(msg)
    }
}
