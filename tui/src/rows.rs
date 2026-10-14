//! Human-readable rows per tab.
use crate::app::App;

pub fn rows(app: &App) -> Vec<(String, String)> {
    match app.tab {
        crate::app::Tab::Dashboard => dashboard(app),
        crate::app::Tab::Dpi => dpi(app),
        crate::app::Tab::Performance => perf(app),
        crate::app::Tab::Sensor => sensor(app),
        crate::app::Tab::Wireless => wireless(app),
        crate::app::Tab::Power => power(app),
        crate::app::Tab::Presets => presets(app),
        crate::app::Tab::Diag => diag(app),
    }
}

fn dashboard(app: &App) -> Vec<(String, String)> {
    let mut r = vec![];
    if let Some(s) = &app.settings {
        r.push(("Model/link".into(), format!("polling {} | key-scan {}", s.polling_label, s.key_scan_label)));
        r.push(("DPI".into(), format!("stage {}/7 = {} DPI", s.current_dpi_stage + 1, s.dpi_x.get(s.current_dpi_stage as usize).copied().unwrap_or(0))));
        r.push(("Sensor preset".into(), format!("{} {:?}", s.sensor_preset, s.sensor_slots)));
        r.push(("LOD/angle".into(), format!("{} / {} deg", s.lod_label, s.angle)));
        r.push(("RF/sleep".into(), format!("{}+{}/{}min", if s.rf_boost {"Maximum"} else {"Adaptive"}, s.rf_proto_label, s.sleep_min)));
    } else { r.push(("Settings".into(), "not loaded (R to refresh)".into())); }
    if let Some(st) = &app.status {
        let bat = st.get("battery_percent").map(|v| v.to_string()).unwrap_or("?".into());
        let conn = st.get("connect_type").map(|v| v.to_string()).unwrap_or("?".into());
        r.push(("Live battery/conn".into(), format!("{bat}% via {conn}")));
    } else { r.push(("Live status".into(), "no report yet (move mouse, R)".into())); }
    r
}

fn dpi(app: &App) -> Vec<(String, String)> {
    let mut r = vec![];
    if let Some(s) = &app.settings {
        for i in 0..7 {
            let x = s.dpi_x.get(i).copied().unwrap_or(0);
            let y = s.dpi_y.get(i).copied().unwrap_or(0);
            let mark = if i as u8 == s.current_dpi_stage { "[*]" } else { "[ ]" };
            let xy = if x == y { format!("{x}") } else { format!("{x}x{y}") };
            r.push((format!("{mark} Stage {}", i + 1), format!("{xy} DPI")));
        }
        r.push(("Active stage".into(), format!("{} (s=switch)", s.current_dpi_stage + 1)));
        r.push(("Edit".into(), "Enter on stage=set DPI value".into()));
    } else { r.push(("DPI".into(), "not loaded".into())); }
    r
}

fn perf(app: &App) -> Vec<(String, String)> {
    if let Some(s) = &app.settings {
        let (title, excerpt, _) = crate::proto::sensor_info(&s.sensor_preset);
        vec![
            ("Polling rate".into(), format!("{} (raw {})", s.polling_label, s.polling_raw)),
            ("Sensor preset".into(), format!("{} - {title}: {excerpt}", s.sensor_preset)),
            ("Preset slots[7]".into(), format!("{:?}", s.sensor_slots)),
            ("Key-scan rate".into(), format!("{} (idx {})", s.key_scan_label, s.key_scan_idx)),
            ("Hint".into(), "Enter=edit s=apply".into()),
        ]
    } else { vec![("Performance".into(), "not loaded".into())] }
}

fn sensor(app: &App) -> Vec<(String, String)> {
    if let Some(s) = &app.settings {
        vec![
            ("Lift-off (LOD)".into(), format!("{} (idx {})", s.lod_label, s.lod_index)),
            ("Sensor angle".into(), format!("{} deg", s.angle)),
            ("Motion sync".into(), onoff(s.motion)),
            ("Glass tracking".into(), onoff(s.glass)),
            ("Linear correction".into(), onoff(s.linear)),
            ("Ripple correction".into(), onoff(s.ripple)),
            ("Debounce p/r".into(), format!("{}/{} ms", s.debounce_press, s.debounce_release)),
        ]
    } else { vec![("Sensor".into(), "not loaded".into())] }
}

fn wireless(app: &App) -> Vec<(String, String)> {
    if let Some(s) = &app.settings {
        vec![
            ("RF boost".into(), if s.rf_boost { "maximum".into() } else { "adaptive".into() }),
            ("RF protocol".into(), s.rf_proto_label.clone()),
            ("Note".into(), "global 96: 0=turbo 2=initial".into()),
        ]
    } else { vec![("Wireless".into(), "not loaded".into())] }
}

fn power(app: &App) -> Vec<(String, String)> {
    if let Some(s) = &app.settings {
        vec![
            ("Sleep timeout".into(), format!("{} min", s.sleep_min)),
            ("Low-battery light".into(), onoff(s.low_bat_light)),
            ("DC switch (?)".into(), format!("{} (undocumented)", onoff(s.dc_switch))),
            ("Hint".into(), "Space=toggle Enter=edit sleep".into()),
        ]
    } else { vec![("Power".into(), "not loaded".into())] }
}

fn presets(app: &App) -> Vec<(String, String)> {
    let mut r: Vec<(String, String)> = app.presets.iter().map(|p| (p.name.clone(), p.desc.clone())).collect();
    if r.is_empty() { r.push(("(no presets)".into(), "~/.config/rapoo/presets/".into())); }
    r.push(("Save current".into(), "p = save preset".into()));
    r.push(("Apply".into(), "Enter = diff+apply".into()));
    r
}

fn diag(app: &App) -> Vec<(String, String)> {
    vec![
        ("Devices".into(), app.list_text.lines().next().unwrap_or("").chars().take(60).collect()),
        ("Pair query".into(), "Enter = read-only query".into()),
        ("Raw read".into(), "w = raw 640/8".into()),
        ("Offset hint".into(), "RAPOO_DATA_OFFSET=4|5|6".into()),
        ("Log".into(), app.log.last().cloned().unwrap_or_default().chars().take(80).collect()),
    ]
}

fn onoff(b: bool) -> String { if b { "on".into() } else { "off".into() } }
