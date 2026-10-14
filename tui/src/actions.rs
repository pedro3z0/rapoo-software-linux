//! Key handling: reference-style navigation + inline adjust with confirm.
//!
//! Editing model follows the monsgeek TUI: Left/Right (h/l) cycle or step
//! the selected value immediately -> centered y/n confirm -> `rapoo set`.
//! Enter opens a text edit (status-bar editor) for exact values.
use crate::app::{App, Mode, PendingAction, Tab};
use crate::model;
use crate::proto;
use crate::rows::Field;
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

pub fn on_key(app: &mut App, key: KeyEvent) {
    match app.mode.clone() {
        Mode::Help => {
            // Any key closes the help popup (hint says so).
            app.mode = Mode::Normal;
        }
        Mode::Editing { field, mut value, label } => {
            match key.code {
                KeyCode::Esc => app.mode = Mode::Normal,
                KeyCode::Enter => finish_edit(app, &field, value.trim(), &label),
                KeyCode::Backspace => { value.pop(); app.mode = Mode::Editing { field, value, label }; }
                KeyCode::Char(c) => { value.push(c); app.mode = Mode::Editing { field, value, label }; }
                _ => {}
            }
        }
        Mode::Confirm { action, .. } => match key.code {
            KeyCode::Char('y') | KeyCode::Char('Y') | KeyCode::Enter => run_action(app, action),
            KeyCode::Char('n') | KeyCode::Char('N') | KeyCode::Esc => app.mode = Mode::Normal,
            _ => {}
        },
        Mode::Message { .. } => app.mode = Mode::Normal,
        Mode::Normal => normal_key(app, key),
    }
}

fn normal_key(app: &mut App, key: KeyEvent) {
    match key.code {
        KeyCode::Char('q') | KeyCode::Esc => app.should_quit = true,
        KeyCode::Tab => app.next_tab(),
        KeyCode::BackTab => app.prev_tab(),
        KeyCode::Down | KeyCode::Char('j') => app.move_cursor(1),
        KeyCode::Up | KeyCode::Char('k') => app.move_cursor(-1),
        KeyCode::Char(c @ '1'..='8') => app.goto_tab((c as u8 - b'1') as usize),
        KeyCode::Left | KeyCode::Char('h') => adjust(app, -1),
        KeyCode::Right | KeyCode::Char('l') => adjust(app, 1),
        KeyCode::Enter => activate(app),
        KeyCode::Char(' ') => toggle(app),
        KeyCode::Char('R') => { app.refresh_all(); app.last_ok = Some("refreshed".into()); }
        KeyCode::Char('?') | KeyCode::F(1) => app.mode = Mode::Help,
        KeyCode::Char('s') => switch_stage(app),
        KeyCode::Char('p') => save_preset_now(app),
        KeyCode::Char('b') => backup_now(app),
        KeyCode::Char('X') => restore_now(app),
        KeyCode::Char('w') => raw_now(app),
        KeyCode::Char('r') if key.modifiers.contains(KeyModifiers::CONTROL) => {
            app.refresh_all();
        }
        _ => {}
    }
}

/// Enter on the selected row: edit, run action, or apply preset.
fn activate(app: &mut App) {
    let Some(row) = app.row_at(app.cursor) else { return };
    match row.field {
        Field::None => {}
        Field::Preset(i) => {
            if let Some(p) = app.presets.get(i) {
                let msg = format!("Apply preset '{}'?\n{}\n\n[y]es / [n]o", p.name, p.desc);
                app.mode = Mode::Confirm { message: msg, action: PendingAction::ApplyPreset(i) };
            }
        }
        Field::PairQuery => {
            match app.bridge.pair_query() {
                Ok(v) => app.mode = Mode::Message { text: format!("pair query: {v}") },
                Err(e) => app.mode = Mode::Message { text: format!("pair query failed: {e:#}") },
            }
        }
        Field::RawRead => raw_now(app),
        Field::ActionSavePreset => save_preset_now(app),
        Field::MotionSync | Field::Glass | Field::Linear | Field::Ripple
        | Field::LowBat | Field::DcSwitch | Field::RfBoost => adjust(app, 1),
        f => open_edit(app, &f, &row.value, row.label.trim()),
    }
}

fn open_edit(app: &mut App, field: &Field, current: &str, label: &str) {
    let fkey = match field {
        Field::DpiValue(i) => format!("dpi:{i}"),
        Field::ActiveStage => "stage".into(),
        Field::Polling => "polling".into(),
        Field::SensorPreset => "sensor".into(),
        Field::KeyScan => "keyscan".into(),
        Field::Lod => "lod".into(),
        Field::Angle => "angle".into(),
        Field::RfProto => "rfproto".into(),
        Field::Sleep => "sleep".into(),
        Field::DebouncePress => "debpress".into(),
        Field::DebounceRelease => "debrel".into(),
        _ => return,
    };
    // strip units for editing
    let init: String = current
        .replace(" DPI", "")
        .replace(" deg", "")
        .replace(" min", "")
        .replace(" mm", "")
        .replace("stage ", "")
        .replace("/7", "")
        .replace("stage", "")
        .trim()
        .to_string();
    app.mode = Mode::Editing { field: fkey, value: init, label: label.to_string() };
}

/// Left/Right: cycle or step the value, then ask y/n.
fn adjust(app: &mut App, dir: i32) {
    let Some(row) = app.row_at(app.cursor) else { return };
    let prof = app.bridge.profile.to_string();
    let args: Option<Vec<String>> = (|| -> Option<Vec<String>> { match row.field {
        Field::DpiValue(i) => {
            let cur = app.settings.as_ref().and_then(|s| s.dpi_x.get(i).copied()).unwrap_or(1600) as i64;
            let new = (cur + dir as i64 * 50).clamp(50, 30000);
            model::check_dpi(new).ok()?;
            Some(vec!["--dpi".into(), new.to_string(), "--stage".into(), (i + 1).to_string(), "--profile".into(), prof])
        }
        Field::ActiveStage => {
            let cur = app.settings.as_ref().map(|s| s.current_dpi_stage as i64).unwrap_or(0);
            let new = (cur + dir as i64).rem_euclid(7);
            Some(vec!["--stage".into(), (new + 1).to_string(), "--profile".into(), prof])
        }
        Field::Polling => {
            let cur = app.settings.as_ref().map(|s| s.polling_label.clone()).unwrap_or_default();
            let labels = proto::POLLING_LABELS;
            let idx = labels.iter().position(|l| *l == cur).unwrap_or(3) as i32;
            let next = labels[(idx + dir).rem_euclid(labels.len() as i32) as usize];
            Some(vec!["--polling".into(), next.into(), "--profile".into(), prof])
        }
        Field::SensorPreset => {
            let s = app.settings.as_ref()?;
            // VV-allowed presets for current polling, in descending value order.
            let mut allowed: Vec<u8> = proto::allowed_presets(s.polling_raw).to_vec();
            allowed.sort_unstable_by(|a, b| b.cmp(a));
            let cur = proto::sensor_value(&s.sensor_preset).unwrap_or(0);
            let idx = allowed.iter().position(|v| *v == cur).unwrap_or(0) as i32;
            let next = allowed[(idx + dir).rem_euclid(allowed.len() as i32) as usize];
            Some(vec!["--sensor-mode".into(), proto::sensor_preset(next).into(), "--profile".into(), prof])
        }
        Field::KeyScan => {
            let cur = app.settings.as_ref().map(|s| s.key_scan_idx).unwrap_or(3);
            let idx = proto::KEY_SCAN_ALLOWED.iter().position(|v| *v == cur).unwrap_or(0) as i32;
            let next = proto::KEY_SCAN_ALLOWED[(idx + dir).rem_euclid(4) as usize];
            Some(vec!["--key-scan".into(), proto::key_scan_label(next).into(), "--profile".into(), prof])
        }
        Field::Lod => {
            let cur = app.settings.as_ref().map(|s| s.lod_index).unwrap_or(1);
            let new = (cur as i32 + dir).clamp(1, 11) as u8;
            let mm = proto::LOD_LV[(new - 1) as usize];
            Some(vec!["--lod".into(), format!("{mm:.1}"), "--profile".into(), prof])
        }
        Field::Angle => {
            let cur = app.settings.as_ref().map(|s| s.angle as i64).unwrap_or(0);
            let new = (cur + dir as i64).clamp(-30, 30);
            model::check_angle(new).ok()?;
            Some(vec!["--angle".into(), new.to_string(), "--profile".into(), prof])
        }
        Field::MotionSync => {
            let cur = app.settings.as_ref().map(|s| s.motion).unwrap_or(false);
            Some(vec!["--motion-sync".into(), if cur { "off" } else { "on" }.into(), "--profile".into(), prof])
        }
        Field::Glass => {
            let cur = app.settings.as_ref().map(|s| s.glass).unwrap_or(false);
            Some(vec!["--glass".into(), if cur { "off" } else { "on" }.into(), "--profile".into(), prof])
        }
        Field::Linear => {
            let cur = app.settings.as_ref()?.linear;
            Some(vec!["--linear-correction".into(), if cur { "off" } else { "on" }.into(), "--profile".into(), prof])
        }
        Field::Ripple => {
            let cur = app.settings.as_ref()?.ripple;
            Some(vec!["--ripple-correction".into(), if cur { "off" } else { "on" }.into(), "--profile".into(), prof])
        }
        Field::DebouncePress => {
            let cur = app.settings.as_ref()?.debounce_press as i64;
            let new = (cur + dir as i64).clamp(0, 32);
            Some(vec!["--debounce-press".into(), new.to_string(), "--profile".into(), prof])
        }
        Field::DebounceRelease => {
            let cur = app.settings.as_ref()?.debounce_release as i64;
            let new = (cur + dir as i64).clamp(0, 32);
            Some(vec!["--debounce-release".into(), new.to_string(), "--profile".into(), prof])
        }
        Field::RfBoost => {
            let cur = app.settings.as_ref().map(|s| s.rf_boost).unwrap_or(true);
            Some(vec!["--rf-boost".into(), if cur { "adaptive" } else { "maximum" }.into(), "--profile".into(), prof])
        }
        Field::RfProto => {
            let cur = app.settings.as_ref().map(|s| s.rf_proto_raw).unwrap_or(0);
            let next = if cur == 0 { "initial" } else { "turbo" };
            Some(vec!["--rf-protocol".into(), next.into()])
        }
        Field::Sleep => {
            let cur = app.settings.as_ref().map(|s| s.sleep_min as i64).unwrap_or(10);
            let new = (cur + dir as i64).clamp(1, 60);
            model::check_sleep(new).ok()?;
            Some(vec!["--sleep".into(), new.to_string(), "--profile".into(), prof])
        }
        Field::LowBat => {
            let cur = app.settings.as_ref().map(|s| s.low_bat_light).unwrap_or(false);
            Some(vec!["--low-battery-light".into(), if cur { "off" } else { "on" }.into(), "--profile".into(), prof])
        }
        Field::DcSwitch => {
            let cur = app.settings.as_ref().map(|s| s.dc_switch).unwrap_or(false);
            Some(vec!["--dc-switch".into(), if cur { "off" } else { "on" }.into(), "--profile".into(), prof])
        }
        _ => None,
    } })();
    if let Some(a) = args { apply_set_now(app, a); }
}

fn toggle(app: &mut App) { adjust(app, 1); }

fn switch_stage(app: &mut App) {
    if app.tab != Tab::Dpi { return; }
    if let Some(row) = app.row_at(app.cursor) {
        if let Field::DpiValue(i) = row.field {
            let args = vec!["--stage".into(), (i + 1).to_string(), "--profile".into(), app.bridge.profile.to_string()];
            apply_set_now(app, args);
        }
    }
}

fn finish_edit(app: &mut App, field: &str, value: &str, label: &str) {
    let prof = app.bridge.profile.to_string();
    let args: Vec<String> = match field {
        f if f.starts_with("dpi:") => {
            let idx: i64 = f[4..].parse().unwrap_or(0);
            let dpi: i64 = value.parse().unwrap_or(-1);
            if let Err(e) = model::check_dpi(dpi) { app.mode = Mode::Message { text: e.to_string() }; return; }
            vec!["--dpi".into(), dpi.to_string(), "--stage".into(), (idx + 1).to_string(), "--profile".into(), prof]
        }
        "stage" => {
            let st: i64 = value.parse().unwrap_or(-1);
            if let Err(e) = model::check_stage(st - 1) { app.mode = Mode::Message { text: e.to_string() }; return; }
            vec!["--stage".into(), st.to_string(), "--profile".into(), prof]
        }
        "polling" => {
            if let Err(e) = model::check_polling(value) { app.mode = Mode::Message { text: e.to_string() }; return; }
            vec!["--polling".into(), value.into(), "--profile".into(), prof]
        }
        "sensor" => {
            let poll = app.settings.as_ref().map(|s| s.polling_raw).unwrap_or(1);
            if let Err(e) = model::check_sensor_preset(value, poll) { app.mode = Mode::Message { text: e.to_string() }; return; }
            vec!["--sensor-mode".into(), value.into(), "--profile".into(), prof]
        }
        "keyscan" => vec!["--key-scan".into(), value.into(), "--profile".into(), prof],
        "lod" => vec!["--lod".into(), value.into(), "--profile".into(), prof],
        "angle" => {
            let a: i64 = value.parse().unwrap_or(999);
            if let Err(e) = model::check_angle(a) { app.mode = Mode::Message { text: e.to_string() }; return; }
            vec!["--angle".into(), a.to_string(), "--profile".into(), prof]
        }
        "rfproto" => vec!["--rf-protocol".into(), value.into()],
        "sleep" => {
            let m: i64 = value.parse().unwrap_or(-1);
            if let Err(e) = model::check_sleep(m) { app.mode = Mode::Message { text: e.to_string() }; return; }
            vec!["--sleep".into(), m.to_string(), "--profile".into(), prof]
        }
        "debpress" => {
            let m: i64 = value.parse().unwrap_or(-1);
            if let Err(e) = model::check_debounce(m) { app.mode = Mode::Message { text: e.to_string() }; return; }
            vec!["--debounce-press".into(), m.to_string(), "--profile".into(), prof]
        }
        "debrel" => {
            let m: i64 = value.parse().unwrap_or(-1);
            if let Err(e) = model::check_debounce(m) { app.mode = Mode::Message { text: e.to_string() }; return; }
            vec!["--debounce-release".into(), m.to_string(), "--profile".into(), prof]
        }
        _ => { app.mode = Mode::Normal; return; }
    };
    let _ = label;
    apply_set_now(app, args);
}

/// Write immediately, show the device's reply in the status bar, refresh.
fn apply_set_now(app: &mut App, args: Vec<String>) {
    let refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
    match app.bridge.set(&refs) {
        Ok(out) => {
            app.last_ok = Some(out.lines().next().unwrap_or("applied").to_string());
            app.push_log(format!("set ok: {}", args.join(" ")));
            app.refresh_settings();
        }
        Err(e) => app.mode = Mode::Message { text: format!("set failed: {e:#}") },
    }
}

fn backup_now(app: &mut App) {
    let path = format!("/tmp/rapoo-tui-backup-{}.json", app.bridge.profile);
    match app.bridge.backup(&path) {
        Ok(_) => app.last_ok = Some(format!("backup -> {path}")),
        Err(e) => app.mode = Mode::Message { text: format!("backup failed: {e:#}") },
    }
}

fn restore_now(app: &mut App) {
    let path = format!("/tmp/rapoo-tui-backup-{}.json", app.bridge.profile);
    if !std::path::Path::new(&path).is_file() {
        app.mode = Mode::Message { text: format!("no backup at {path} (press b first)") };
        return;
    }
    app.mode = Mode::Confirm { message: format!("Restore from\n{path} ?\n\n[y]es / [n]o"), action: PendingAction::Restore(path) };
}

fn save_preset_now(app: &mut App) {
    if let Some(s) = &app.settings {
        let snap = s.raw.clone();
        match crate::presets::save_preset("tui-snapshot", "saved from rapoo-tui", &snap) {
            Ok(p) => {
                app.last_ok = Some(format!("saved {}", p.display()));
                app.presets = crate::presets::list_presets();
            }
            Err(e) => app.mode = Mode::Message { text: format!("save failed: {e:#}") },
        }
    }
}

fn raw_now(app: &mut App) {
    match app.bridge.raw("640", "8") {
        Ok(v) => app.mode = Mode::Message { text: format!("raw 640/8: {v}") },
        Err(e) => app.mode = Mode::Message { text: format!("raw failed: {e:#}") },
    }
}

fn run_action(app: &mut App, action: PendingAction) {
    match action {
        PendingAction::Restore(path) => {
            match app.bridge.restore(&path) {
                Ok(_) => app.last_ok = Some(format!("restore <- {path}")),
                Err(e) => { app.mode = Mode::Message { text: format!("restore failed: {e:#}") }; return; }
            }
            app.mode = Mode::Normal;
            app.refresh_all();
        }
        PendingAction::ApplyPreset(i) => {
            app.mode = Mode::Normal;
            if let Some(p) = app.presets.get(i).cloned() { apply_preset(app, &p); }
        }
    }
}

fn apply_preset(app: &mut App, p: &crate::presets::Preset) {
    let s = &p.settings;
    let mut args: Vec<String> = vec![];
    let mut push = |k: &str, v: String| { args.push(k.to_string()); args.push(v); };
    if let Some(v) = s.get("polling").and_then(|v| v.as_str()) { push("--polling", v.to_string()); }
    if let Some(v) = s.get("sensor_mode").and_then(|v| v.as_str()) { push("--sensor-mode", v.to_string()); }
    if let Some(v) = s.get("key_scan") { push("--key-scan", v.to_string()); }
    if let Some(v) = s.get("sleep") { push("--sleep", v.to_string()); }
    if let Some(v) = s.get("lod_index") { push("--lod", v.to_string()); }
    if let Some(v) = s.get("rf_boost").and_then(|v| v.as_str()) { push("--rf-boost", v.to_string()); }
    if args.is_empty() {
        app.mode = Mode::Message { text: "preset has no CLI-mappable keys".into() };
        return;
    }
    let refs: Vec<&str> = args.iter().map(|x| x.as_str()).collect();
    match app.bridge.set(&refs) {
        Ok(_) => { app.last_ok = Some(format!("preset '{}' applied", p.name)); app.refresh_all(); }
        Err(e) => app.mode = Mode::Message { text: format!("preset failed: {e:#}") },
    }
}
