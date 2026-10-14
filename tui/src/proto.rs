//! Rapoo protocol tables — ported from backend/rapoo/protocol.py + official
//! WebHID bundle (EV/VV/PV tables verified 2026-10-14 from index-3ShGzFuu.js).
//!
//! Bundle evidence:
//!   EV=[{5,frenzy},{4,competitive},{3,hyperCore},{2,firepower},{1,balanced},{0,office}]
//!   PV=[8,4,2,1,132,130,129]
//!   VV={8:[1,0],4:[1,0],2:[2,1,0],1:[5,4,3,2,1],132:[5,4,3,2],130:[5,4,3],129:[5,4,3]}
//!   cybercafe BV=[{5,frenzy},{4,competitive},{3,hyperCore}], FV=[1,132,130,129]
//!   paw3311 DV=[{5,hyperCore},{2,firepower},{0,office}], UV=[0,1,2,3]
//!   dd=["125Hz","250Hz","500Hz","1000Hz","2000Hz","4000Hz","8000Hz"]
//!   kQ subtitles: frenzy/competitive="Corded Gaming", firepower="High Performance",
//!     balanced="Low Power", office="Office"

/// Polling slot order: profile+732 slot index -> polling raw code.
pub const POLLING_RATE_SLOTS: [u8; 7] = [8, 4, 2, 1, 132, 130, 129];

/// Raw polling code -> label.
pub fn polling_label(raw: u8) -> &'static str {
    match raw {
        8 => "125Hz",
        4 => "250Hz",
        2 => "500Hz",
        1 => "1000Hz",
        132 => "2000Hz",
        130 => "4000Hz",
        129 => "8000Hz",
        _ => "?",
    }
}

/// Label -> raw polling code.
pub fn polling_raw(label: &str) -> Option<u8> {
    match label {
        "125Hz" => Some(8),
        "250Hz" => Some(4),
        "500Hz" => Some(2),
        "1000Hz" => Some(1),
        "2000Hz" => Some(132),
        "4000Hz" => Some(130),
        "8000Hz" => Some(129),
        _ => None,
    }
}

pub const POLLING_LABELS: [&str; 7] = [
    "125Hz", "250Hz", "500Hz", "1000Hz", "2000Hz", "4000Hz", "8000Hz",
];

/// Sensor-mode value -> preset name (13K retail tier: VT0 Air MAX / VT3 Air).
pub fn sensor_preset(value: u8) -> &'static str {
    match value {
        5 => "frenzy",
        4 => "competitive",
        3 => "hyperCore",
        2 => "firepower",
        1 => "balanced",
        0 => "office",
        _ => "?",
    }
}

pub fn sensor_value(name: &str) -> Option<u8> {
    match name.to_lowercase().as_str() {
        "frenzy" => Some(5),
        "competitive" => Some(4),
        "hypercore" => Some(3),
        "firepower" => Some(2),
        "balanced" => Some(1),
        "office" => Some(0),
        _ => None,
    }
}

/// Official marketing copy per preset (bundle i18n + kQ subtitles).
/// (title, excerpt, power_class)
pub fn sensor_info(name: &str) -> (&'static str, &'static str, &'static str) {
    match name {
        "frenzy" => ("Frenzy Gaming", "≥20K engine, ultra-fast scan", "Corded Gaming"),
        "competitive" => (
            "Gaming Hyper",
            "≥{scanRate}KFPS engine scan rate",
            "Corded Gaming",
        ),
        "hyperCore" => ("Hyper Core", "Microsecond response", "Corded Gaming"),
        "firepower" => ("Firepower", "Esports gaming", "High Performance"),
        "balanced" => ("Balanced", "Gaming + low power", "Low Power"),
        "office" => ("Office", "Daily use", "Office"),
        _ => ("Unknown", "", ""),
    }
}

/// VV table: polling raw -> allowed sensor values.
pub fn allowed_presets(poll_raw: u8) -> &'static [u8] {
    match poll_raw {
        8 | 4 => &[1, 0],
        2 => &[2, 1, 0],
        1 => &[5, 4, 3, 2, 1],
        132 => &[5, 4, 3, 2],
        130 | 129 => &[5, 4, 3],
        _ => &[5, 4, 3, 2, 1, 0],
    }
}

/// Key-scan index -> Hz label (official `dd` array).
pub fn key_scan_label(idx: u8) -> &'static str {
    match idx {
        0 => "125Hz",
        1 => "250Hz",
        2 => "500Hz",
        3 => "1000Hz",
        4 => "2000Hz",
        5 => "4000Hz",
        6 => "8000Hz",
        _ => "?",
    }
}

pub const KEY_SCAN_ALLOWED: [u8; 4] = [3, 4, 5, 6];

/// LV scale (VT0 Air MAX / PAW3950U family) and MV scale (PAW3398 legacy).
pub const LOD_LV: [f32; 11] = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7];
pub const LOD_MV: [f32; 11] = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0];

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn vv_table_matches_bundle() {
        assert_eq!(allowed_presets(8), &[1, 0]);
        assert_eq!(allowed_presets(2), &[2, 1, 0]);
        assert_eq!(allowed_presets(1), &[5, 4, 3, 2, 1]);
        assert_eq!(allowed_presets(129), &[5, 4, 3]);
    }
    #[test]
    fn ev_table_matches_bundle() {
        assert_eq!(sensor_preset(5), "frenzy");
        assert_eq!(sensor_preset(0), "office");
        assert_eq!(sensor_value("hypercore"), Some(3));
    }
    #[test]
    fn polling_roundtrip() {
        for (raw, label) in [(8, "125Hz"), (1, "1000Hz"), (129, "8000Hz")] {
            assert_eq!(polling_label(raw), label);
            assert_eq!(polling_raw(label), Some(raw));
        }
    }
}
