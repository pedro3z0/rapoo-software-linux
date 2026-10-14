//! App model: cached device state + validation (no ratatui here).
//!
//! Mirrors backend/rapoo/device.py MouseSettings ranges so the TUI
//! validates locally before spawning `rapoo set`.

use crate::proto;
use anyhow::{anyhow, Result};
use serde_json::Value;

#[derive(Debug, Clone, Default)]
pub struct Settings {
    pub raw: Value,
    pub current_dpi_stage: u8, // 0-based
    pub dpi_x: Vec<u16>,
    pub dpi_y: Vec<u16>,
    pub polling_raw: u8,
    pub polling_label: String,
    pub sleep_min: u8,
    pub angle: i8,
    pub glass: bool,
    pub motion: bool,
    pub linear: bool,
    pub ripple: bool,
    pub debounce_press: u8,
    pub debounce_release: u8,
    pub key_scan_idx: u8,
    pub key_scan_label: String,
    pub sensor_slots: Vec<u8>,
    pub sensor_preset: String,
    pub rf_proto_raw: u8,
    pub rf_proto_label: String,
    pub rf_boost: bool,
    pub low_bat_light: bool,
    pub dc_switch: bool,
    pub lod_index: u8,
    pub lod_label: String,
}

impl Settings {
    pub fn from_json(v: &Value) -> Self {
        let g = |k: &str| v.get(k).cloned().unwrap_or(Value::Null);
        let gi = |k: &str| g(k).as_i64().unwrap_or(0);
        let gb = |k: &str| g(k).as_bool().unwrap_or(false);
        let gs = |k: &str| g(k).as_str().unwrap_or("").to_string();
        let gu = |k: &str| -> Vec<u16> {
            v.get(k)
                .and_then(|a| a.as_array())
                .map(|a| a.iter().map(|x| x.as_u64().unwrap_or(0) as u16).collect())
                .unwrap_or_default()
        };
        let gu8 = |k: &str| -> Vec<u8> {
            v.get(k)
                .and_then(|a| a.as_array())
                .map(|a| a.iter().map(|x| x.as_u64().unwrap_or(0) as u8).collect())
                .unwrap_or_default()
        };
        Settings {
            raw: v.clone(),
            current_dpi_stage: gi("current_dpi_stage") as u8,
            dpi_x: gu("dpi_stages_x"),
            dpi_y: gu("dpi_stages_y"),
            polling_raw: gi("polling_rate_raw") as u8,
            polling_label: gs("polling_rate_label"),
            sleep_min: gi("sleep_time_minutes") as u8,
            angle: gi("sensor_angle") as i8,
            glass: gb("glass_tracking"),
            motion: gb("motion_sync"),
            linear: gb("linear_correction"),
            ripple: gb("ripple_correction"),
            debounce_press: gi("debounce_press_ms") as u8,
            debounce_release: gi("debounce_release_ms") as u8,
            key_scan_idx: gi("key_scan_rate_index") as u8,
            key_scan_label: gs("key_scan_rate_label"),
            sensor_slots: gu8("sensor_mode_slots"),
            sensor_preset: gs("sensor_mode_preset"),
            rf_proto_raw: gi("rf_protocol_raw") as u8,
            rf_proto_label: gs("rf_protocol_label"),
            rf_boost: gb("rf_boost_enabled"),
            low_bat_light: gb("low_battery_light_enabled"),
            dc_switch: gb("dc_switch_enabled"),
            lod_index: gi("liftoff_index") as u8,
            lod_label: gs("liftoff_label"),
            ..Default::default()
        }
    }
}

// ---- validation (same limits as device.py) ----

pub fn check_dpi(dpi: i64) -> Result<()> {
    if (50..=30000).contains(&dpi) {
        Ok(())
    } else {
        Err(anyhow!("DPI must be 50-30000, got {dpi}"))
    }
}
pub fn check_stage(i: i64) -> Result<()> {
    if (0..=6).contains(&i) {
        Ok(())
    } else {
        Err(anyhow!("DPI stage must be 1-7, got {}", i + 1))
    }
}
pub fn check_sleep(m: i64) -> Result<()> {
    if (1..=60).contains(&m) {
        Ok(())
    } else {
        Err(anyhow!("Sleep must be 1-60 min, got {m}"))
    }
}
pub fn check_angle(a: i64) -> Result<()> {
    if (-30..=30).contains(&a) {
        Ok(())
    } else {
        Err(anyhow!("Angle must be -30..+30, got {a}"))
    }
}
pub fn check_polling(label: &str) -> Result<u8> {
    proto::polling_raw(label).ok_or_else(|| anyhow!("Unknown polling {label}"))
}
pub fn check_sensor_preset(name: &str, poll_raw: u8) -> Result<u8> {
    let v = proto::sensor_value(name)
        .ok_or_else(|| anyhow!("Unknown preset {name} (office/balanced/firepower/hyperCore/competitive/frenzy)"))?;
    let allowed = proto::allowed_presets(poll_raw);
    if allowed.contains(&v) {
        Ok(v)
    } else {
        let names: Vec<_> = allowed.iter().map(|x| proto::sensor_preset(*x)).collect();
        Err(anyhow!(
            "Preset {} not allowed at {} (allowed: {})",
            name,
            proto::polling_label(poll_raw),
            names.join("/")
        ))
    }
}
pub fn check_key_scan(idx: i64) -> Result<()> {
    if [3, 4, 5, 6].contains(&idx) {
        Ok(())
    } else {
        Err(anyhow!("Key-scan index must be 3-6 (1000/2000/4000/8000Hz)"))
    }
}
pub fn check_lod_index(i: i64) -> Result<()> {
    if (1..=11).contains(&i) {
        Ok(())
    } else {
        Err(anyhow!("LOD index must be 1-11"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn validation_ranges() {
        assert!(check_dpi(1600).is_ok());
        assert!(check_dpi(49).is_err());
        assert!(check_sleep(10).is_ok());
        assert!(check_sleep(0).is_err());
        assert!(check_angle(-30).is_ok());
        assert!(check_angle(31).is_err());
        assert!(check_sensor_preset("frenzy", 129).is_ok());
        assert!(check_sensor_preset("office", 129).is_err());
        assert!(check_sensor_preset("office", 8).is_ok());
        assert!(check_key_scan(3).is_ok());
        assert!(check_key_scan(2).is_err());
    }
}
