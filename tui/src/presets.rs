//! Level-1 custom presets: named JSON snapshots of EEPROM knobs.
//!
//! A "preset" here = full `rapoo get` JSON + metadata. This gives users
//! "my frenzy-low-latency" vs "office-quiet" without touching firmware.
//! New DSP preset *values* (e.g. 6=myTune) are NOT possible without a
//! firmware patch (SHA512-signed Nordic image) — see rapoo-flasher README.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Preset {
    pub name: String,
    pub desc: String,
    pub settings: Value,
}

pub fn preset_dir() -> PathBuf {
    std::env::var("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            dirs_home().join(".config")
        })
        .join("rapoo/presets")
}

fn dirs_home() -> PathBuf {
    std::env::var("HOME").map(PathBuf::from).unwrap_or_else(|_| PathBuf::from("."))
}

pub fn list_presets() -> Vec<Preset> {
    let dir = preset_dir();
    let mut out = vec![];
    if let Ok(rd) = fs::read_dir(&dir) {
        for e in rd.flatten() {
            let p = e.path();
            if p.extension().map(|x| x == "json").unwrap_or(false) {
                if let Ok(txt) = fs::read_to_string(&p) {
                    if let Ok(pr) = serde_json::from_str::<Preset>(&txt) {
                        out.push(pr);
                    }
                }
            }
        }
    }
    // builtins
    out.push(builtin_frenzy());
    out.push(builtin_office());
    out
}

fn builtin_frenzy() -> Preset {
    Preset {
        name: "frenzy-low-latency [builtin]".into(),
        desc: "1000Hz frenzy, key-scan 1000Hz, LOD 1.0mm, Maximum+turbo".into(),
        settings: serde_json::json!({
            "polling": "1000Hz", "sensor_mode": "frenzy",
            "key_scan": 3, "lod_index": 4,
            "rf_boost": "maximum", "rf_protocol": "turbo",
            "motion_sync": false, "glass": false
        }),
    }
}
fn builtin_office() -> Preset {
    Preset {
        name: "office-quiet [builtin]".into(),
        desc: "125Hz office, Adaptive, sleep 10min".into(),
        settings: serde_json::json!({
            "polling": "125Hz", "sensor_mode": "office",
            "rf_boost": "adaptive", "sleep": 10
        }),
    }
}

pub fn save_preset(name: &str, desc: &str, settings: &Value) -> Result<PathBuf> {
    let dir = preset_dir();
    fs::create_dir_all(&dir).context("create preset dir")?;
    let safe: String = name
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '-' || c == '_' { c } else { '_' })
        .collect();
    let path = dir.join(format!("{safe}.json"));
    let p = Preset {
        name: name.into(),
        desc: desc.into(),
        settings: settings.clone(),
    };
    fs::write(&path, serde_json::to_string_pretty(&p)?)?;
    Ok(path)
}

/// Diff live settings vs preset: returns changed human-readable lines.
pub fn diff_preset(live: &Value, preset: &Value) -> Vec<String> {
    let mut lines = vec![];
    if let (Some(a), Some(b)) = (live.as_object(), preset.as_object()) {
        for (k, pv) in b {
            // preset files may use CLI flag names; map a few
            let live_key = match k.as_str() {
                "polling" => "polling_rate_label",
                "sensor_mode" => "sensor_mode_preset",
                "key_scan" => "key_scan_rate_index",
                "sleep" => "sleep_time_minutes",
                "lod_index" => "liftoff_index",
                "rf_boost" => "rf_boost_enabled",
                "rf_protocol" => "rf_protocol_label",
                "motion_sync" => "motion_sync",
                "glass" => "glass_tracking",
                other => other,
            };
            let lv = a.get(live_key).unwrap_or(&Value::Null);
            if lv != pv {
                lines.push(format!("{live_key}: {lv} -> {pv}"));
            }
        }
    }
    lines
}
