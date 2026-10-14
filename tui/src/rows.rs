//! Dense tab rows: fixed-width labels, colored values, edit affordances,
//! and a Field tag so input handling never matches on cursor indices.
//! Style follows the monsgeek reference: information-rich single list.

use crate::app::{App, Tab};
use ratatui::style::Color;

/// What a row does when edited / activated.
#[derive(Debug, Clone, PartialEq)]
pub enum Field {
    /// Read-only row.
    None,
    DpiValue(usize),
    ActiveStage,
    Polling,
    SensorPreset,
    KeyScan,
    Lod,
    Angle,
    MotionSync,
    Glass,
    Linear,
    Ripple,
    RfBoost,
    RfProto,
    Sleep,
    LowBat,
    DcSwitch,
    DebouncePress,
    DebounceRelease,
    Preset(usize),
    PairQuery,
    RawRead,
    ActionSavePreset,
}

#[derive(Debug, Clone)]
pub struct Row {
    pub label: String,
    pub value: String,
    pub fg: Color,
    pub field: Field,
    /// Extra DarkGray hint glued to the line, e.g. "  [d]".
    pub hint: &'static str,
}

impl Row {
    fn ro(label: &str, value: impl Into<String>, fg: Color) -> Self {
        Row { label: format!("{label:<16}"), value: value.into(), fg, field: Field::None, hint: "" }
    }
    fn ed(label: &str, value: impl Into<String>, fg: Color, field: Field) -> Self {
        Row { label: format!("{label:<16}"), value: value.into(), fg, field, hint: "" }
    }
}

fn onoff(b: bool) -> &'static str { if b { "on" } else { "off" } }

pub fn rows(app: &App) -> Vec<Row> {
    match app.tab {
        Tab::Dashboard => dashboard(app),
        Tab::Dpi => dpi(app),
        Tab::Performance => perf(app),
        Tab::Sensor => sensor(app),
        Tab::Wireless => wireless(app),
        Tab::Power => power(app),
        Tab::Presets => presets(app),
        Tab::Diag => diag(app),
    }
}

/// Reference-style overview: device + live link + every setting (~25 rows).
fn dashboard(app: &App) -> Vec<Row> {
    let mut r = vec![];
    // --- device / endpoints ---
    let endpoints: Vec<&str> = app.list_text.lines().filter(|l| l.trim_start().starts_with("- Node:")).collect();
    r.push(Row::ro("Device", crate::rows::device_name(&app.list_text), Color::Green));
    for (i, ep) in endpoints.iter().enumerate() {
        let cleaned = ep.trim_start_matches("- ").trim().trim_start_matches("Node: ");
        r.push(Row::ro(&format!("Endpoint {}", i + 1), cleaned.chars().take(70).collect::<String>(), Color::DarkGray));
    }
    // --- live status ---
    if let Some(st) = &app.status {
        let g = |k: &str| st.get(k).map(|v| match v {
            serde_json::Value::String(s) => s.clone(),
            serde_json::Value::Bool(b) => b.to_string(),
            other => other.to_string(),
        }).unwrap_or_else(|| "?".into());
        r.push(Row::ro("Link", g("connect_type"), Color::Cyan));
        r.push(Row::ro("Battery", format!("{}%  ({})", g("battery_percent"), g("battery_status")), Color::Green));
        let rssi = st.get("rf_rssi").and_then(|v| v.as_u64()).unwrap_or(0);
        let rf = st.get("rf_connected").and_then(|v| v.as_bool()).unwrap_or(false);
        r.push(Row::ro("RF link", format!("{}  rssi {}", if rf { "connected" } else { "DOWN" }, rssi), if rf { Color::Green } else { Color::Red }));
        r.push(Row::ro("USB PID", g("usb_pid"), Color::DarkGray));
        r.push(Row::ro("Live profile", g("profile"), Color::DarkGray));
    } else {
        r.push(Row::ro("Live status", "no report — move mouse, press R", Color::DarkGray));
    }
    r.push(Row::ro("", "".to_string(), Color::Reset));
    // --- settings summary ---
    if let Some(s) = &app.settings {
        let (title, _, _) = crate::proto::sensor_info(&s.sensor_preset);
        r.push(Row::ro("Polling", s.polling_label.clone(), Color::Yellow));
        r.push(Row::ro("Key scan", s.key_scan_label.clone(), Color::Yellow));
        r.push(Row::ro("Preset", format!("{} ({title})", s.sensor_preset), Color::Yellow));
        r.push(Row::ro("Preset slots", format!("{:?}", s.sensor_slots), Color::DarkGray));
        let stage = s.current_dpi_stage as usize;
        r.push(Row::ro("Active DPI", format!("stage {} = {} DPI", stage + 1, s.dpi_x.get(stage).copied().unwrap_or(0)), Color::Green));
        r.push(Row::ro("Lift-off", s.lod_label.clone(), Color::Yellow));
        r.push(Row::ro("Sensor angle", format!("{} deg", s.angle), Color::Yellow));
        r.push(Row::ro("Motion sync", onoff(s.motion), if s.motion { Color::Green } else { Color::DarkGray }));
        r.push(Row::ro("Glass track", onoff(s.glass), if s.glass { Color::Green } else { Color::DarkGray }));
        r.push(Row::ro("Linear corr.", onoff(s.linear), if s.linear { Color::Green } else { Color::DarkGray }));
        r.push(Row::ro("Ripple corr.", onoff(s.ripple), if s.ripple { Color::Green } else { Color::DarkGray }));
        r.push(Row::ro("RF strategy", if s.rf_boost { "maximum" } else { "adaptive" }, Color::Yellow));
        r.push(Row::ro("RF protocol", s.rf_proto_label.clone(), Color::Yellow));
        r.push(Row::ro("Sleep timeout", format!("{} min", s.sleep_min), Color::Yellow));
        r.push(Row::ro("Debounce", format!("{}/{} ms", s.debounce_press, s.debounce_release), Color::DarkGray));
        r.push(Row::ro("Low-batt light", onoff(s.low_bat_light), if s.low_bat_light { Color::Green } else { Color::DarkGray }));
        r.push(Row::ro("DC switch", format!("{} (undoc)", onoff(s.dc_switch)), Color::DarkGray));
    } else {
        r.push(Row::ro("Settings", "not loaded — press R", Color::Red));
    }
    r
}

pub fn device_name(list: &str) -> String {
    list.lines()
        .find(|l| l.contains("->"))
        .and_then(|l| l.split("->").nth(1))
        .map(|m| m.replace("[CONFIG INTERFACE]", "").trim().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "not found".into())
}

fn dpi(app: &App) -> Vec<Row> {
    let mut r = vec![];
    if let Some(s) = &app.settings {
        for i in 0..7 {
            let x = s.dpi_x.get(i).copied().unwrap_or(0);
            let y = s.dpi_y.get(i).copied().unwrap_or(0);
            let active = i as u8 == s.current_dpi_stage;
            let xy = if x == y { format!("{x} DPI") } else { format!("{x} x {y} DPI") };
            let label = format!("{} Stage {}", if active { "*" } else { " " }, i + 1);
            let mut row = Row::ed(&label, xy, Color::Yellow, Field::DpiValue(i));
            if active { row.fg = Color::Green; row.hint = "  <-/->: +/- 50 DPI"; }
            r.push(row);
        }
        r.push(Row { label: format!("{:<16}", "Active stage"),
            value: format!("stage {}/7", s.current_dpi_stage + 1), fg: Color::Green,
            field: Field::ActiveStage, hint: "  [s] switch" });
    } else {
        r.push(Row::ro("DPI", "not loaded — press R", Color::Red));
    }
    r
}

fn perf(app: &App) -> Vec<Row> {
    let mut r = vec![];
    if let Some(s) = &app.settings {
        let (title, excerpt, power) = crate::proto::sensor_info(&s.sensor_preset);
        let filled = crate::proto::fill_scan_rate(excerpt, &s.sensor_scan_label);
        r.push(Row::ed("Polling rate", s.polling_label.clone(), Color::Yellow, Field::Polling));
        r.push(Row::ro("  hint", "high polling needs motion flux (>=1600 CPI for 8K) + USB 3.x/XHCI".to_string(), Color::DarkGray));
        r.push(Row::ed("Sensor preset", s.sensor_preset.clone(), Color::Yellow, Field::SensorPreset));
        r.push(Row::ro(&format!("  {title}"), format!("{filled}  [{power}]"), Color::DarkGray));
        r.push(Row::ro("Preset slots", format!("125..8000Hz = {:?}", s.sensor_slots), Color::DarkGray));
        r.push(Row::ed("Key scan", s.key_scan_label.clone(), Color::Yellow, Field::KeyScan));
        r.push(Row::ro("", "".to_string(), Color::Reset));
        r.push(Row::ro("Allowed here", crate::proto::allowed_presets(s.polling_raw).iter().map(|v| crate::proto::sensor_preset(*v)).collect::<Vec<_>>().join(" / "), Color::DarkGray));
    } else {
        r.push(Row::ro("Performance", "not loaded — press R", Color::Red));
    }
    r
}

fn sensor(app: &App) -> Vec<Row> {
    let mut r = vec![];
    if let Some(s) = &app.settings {
        r.push(Row::ed("Lift-off (LOD)", s.lod_label.clone(), Color::Yellow, Field::Lod));
        let scale: Vec<String> = s.liftoff_scale.iter().map(|v| format!("{v:.1}")).collect();
        r.push(Row::ro("  scale", scale.join(" "), Color::DarkGray));
        r.push(Row::ed("Sensor angle", format!("{} deg", s.angle), Color::Yellow, Field::Angle));
        r.push(Row::ed("Motion sync", onoff(s.motion).to_string(), if s.motion { Color::Green } else { Color::DarkGray }, Field::MotionSync));
        r.push(Row::ed("Glass tracking", onoff(s.glass).to_string(), if s.glass { Color::Green } else { Color::DarkGray }, Field::Glass));
        r.push(Row::ed("Linear corr.", onoff(s.linear).to_string(), if s.linear { Color::Green } else { Color::DarkGray }, Field::Linear));
        r.push(Row::ed("Ripple corr.", onoff(s.ripple).to_string(), if s.ripple { Color::Green } else { Color::DarkGray }, Field::Ripple));
        r.push(Row::ed("Debounce press", format!("{} ms", s.debounce_press), Color::Yellow, Field::DebouncePress));
        r.push(Row::ed("Debounce release", format!("{} ms", s.debounce_release), Color::Yellow, Field::DebounceRelease));
        r.push(Row::ro("", "".to_string(), Color::Reset));
        r.push(Row::ro("Note", "motion sync: up to one interval delay · ripple: high-CPI smoothing · linear: angle snapping".to_string(), Color::DarkGray));
    } else {
        r.push(Row::ro("Sensor", "not loaded — press R", Color::Red));
    }
    r
}

fn wireless(app: &App) -> Vec<Row> {
    let mut r = vec![];
    if let Some(s) = &app.settings {
        r.push(Row::ed("RF strategy", if s.rf_boost { "maximum" } else { "adaptive" }.to_string(), Color::Yellow, Field::RfBoost));
        r.push(Row::ro("  hint", "Adaptive - auto-adjusts RF for efficiency · Maximum - full RF power".to_string(), Color::DarkGray));
        r.push(Row::ed("RF protocol", s.rf_proto_label.clone(), Color::Yellow, Field::RfProto));
        r.push(Row::ro("  hint", if s.rf_proto_raw == 0 {
            "Efficient Turbo (default) - efficient RF link"
        } else {
            "Initial - original protocol; fallback if the link is unstable"
        }.to_string(), Color::DarkGray));
        if let Some(st) = &app.status {
            let rf = st.get("rf_connected").and_then(|v| v.as_bool()).unwrap_or(false);
            let rssi = st.get("rf_rssi").and_then(|v| v.as_u64()).unwrap_or(0);
            r.push(Row::ro("RF connected", if rf { "yes" } else { "no" }, if rf { Color::Green } else { Color::Red }));
            r.push(Row::ro("RF rssi", format!("{rssi} (0-127, 7th bit = connected)"), Color::Cyan));
            r.push(Row::ro("RF type", st.get("rf_type").map(|v| v.to_string()).unwrap_or_else(|| "?".into()), Color::DarkGray));
            r.push(Row::ro("Link", st.get("connect_type").map(|v| v.to_string()).unwrap_or_else(|| "?".into()), Color::Cyan));
        }
        r.push(Row::ro("Pairing", "read-only query on Diagnostics tab; live pair disabled".to_string(), Color::DarkGray));
    } else {
        r.push(Row::ro("Wireless", "not loaded — press R", Color::Red));
    }
    r
}

fn power(app: &App) -> Vec<Row> {
    let mut r = vec![];
    if let Some(s) = &app.settings {
        r.push(Row::ed("Sleep timeout", format!("{} min", s.sleep_min), Color::Yellow, Field::Sleep));
        r.push(Row::ed("Low-batt light", onoff(s.low_bat_light).to_string(), if s.low_bat_light { Color::Green } else { Color::DarkGray }, Field::LowBat));
        r.push(Row::ed("DC switch", format!("{} (undoc)", onoff(s.dc_switch)), Color::DarkGray, Field::DcSwitch));
        if let Some(st) = &app.status {
            let bat = st.get("battery_percent").map(|v| v.to_string()).unwrap_or_else(|| "?".into());
            let bars_n = st.get("battery_percent").and_then(|v| v.as_u64()).unwrap_or(0).div_ceil(7) as usize;
            r.push(Row::ro("Battery", format!("{}%  {}", bat, "█".repeat(bars_n.min(15))), Color::Green));
            r.push(Row::ro("Battery raw", st.get("battery_status").map(|v| v.to_string()).unwrap_or_else(|| "?".into()), Color::DarkGray));
        }
        r.push(Row::ro("", "".to_string(), Color::Reset));
        r.push(Row::ro("Hint", "sleep = idle timeout before RF sleep".to_string(), Color::DarkGray));
    } else {
        r.push(Row::ro("Power", "not loaded — press R", Color::Red));
    }
    r
}

fn presets(app: &App) -> Vec<Row> {
    let mut r: Vec<Row> = app.presets.iter().enumerate().map(|(i, p)| {
        let mut row = Row::ed(&p.name, p.desc.clone(), Color::Yellow, Field::Preset(i));
        if p.name.ends_with("[builtin]") { row.fg = Color::DarkGray; }
        row
    }).collect();
    if r.is_empty() {
        r.push(Row::ro("(none)", "~/.config/rapoo/presets/".to_string(), Color::DarkGray));
    }
    r.push(Row { label: format!("{:<16}", "Save snapshot"), value: "current settings -> preset".into(),
        fg: Color::Cyan, field: Field::ActionSavePreset, hint: "  [p]" });
    r
}

fn diag(app: &App) -> Vec<Row> {
    let mut r = vec![];
    for line in app.list_text.lines().filter(|l| l.trim_start().starts_with("- Node:")) {
        let cleaned = line.trim_start_matches("- ").trim().trim_start_matches("Node: ");
        r.push(Row::ro("Endpoint", cleaned.chars().take(78).collect::<String>(), Color::DarkGray));
    }
    if r.is_empty() {
        r.push(Row::ro("Devices", "none found (check udev rule)".to_string(), Color::Red));
    }
    r.push(Row { label: format!("{:<16}", "Pair query"), value: "read-only link state".into(),
        fg: Color::Cyan, field: Field::PairQuery, hint: "  [Enter]" });
    r.push(Row { label: format!("{:<16}", "Raw read"), value: "offset 640 len 8 + payload candidates".into(),
        fg: Color::Cyan, field: Field::RawRead, hint: "  [Enter/w]" });
    r.push(Row::ro("Data offset", "auto-calibrated; force with RAPOO_DATA_OFFSET=4|5|6".to_string(), Color::DarkGray));
    r.push(Row::ro("Last log", app.log.last().cloned().unwrap_or_default().chars().take(70).collect::<String>(), Color::DarkGray));
    r
}
