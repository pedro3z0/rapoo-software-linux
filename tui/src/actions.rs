//! Key handling: navigation, edit, toggle, confirm, apply.
use crate::app::{App, Mode, PendingAction, Tab};
use crate::model;
use crossterm::event::{KeyCode, KeyEvent};

pub fn on_key(app: &mut App, key: KeyEvent) {
    match app.mode.clone() {
        Mode::Editing { field, mut value } => {
            match key.code {
                KeyCode::Esc => { app.mode = Mode::Normal; }
                KeyCode::Enter => { finish_edit(app, &field, value.trim()); }
                KeyCode::Backspace => { value.pop(); app.mode = Mode::Editing { field, value }; }
                KeyCode::Char(c) => { value.push(c); app.mode = Mode::Editing { field, value }; }
                _ => {}
            }
            return;
        }
        Mode::Confirm { action, .. } => {
            match key.code {
                KeyCode::Char('y') | KeyCode::Char('Y') | KeyCode::Enter => { run_action(app, action); }
                KeyCode::Char('n') | KeyCode::Char('N') | KeyCode::Esc => { app.mode = Mode::Normal; }
                _ => {}
            }
            return;
        }
        Mode::Message { .. } => { app.mode = Mode::Normal; return; }
        Mode::Normal => {}
    }
    match key.code {
        KeyCode::Char('q') | KeyCode::Esc => app.should_quit = true,
        KeyCode::Tab | KeyCode::Right => app.next_tab(),
        KeyCode::BackTab | KeyCode::Left => app.prev_tab(),
        KeyCode::Down | KeyCode::Char('j') => app.move_cursor(1),
        KeyCode::Up | KeyCode::Char('k') => app.move_cursor(-1),
        KeyCode::Char(c @ '1'..='8') => app.goto_tab((c as u8 - b'1') as usize),
        KeyCode::Char('R') => { app.refresh_all(); app.last_ok = Some("refreshed".into()); }
        KeyCode::Enter => start_edit(app),
        KeyCode::Char(' ') => toggle(app),
        KeyCode::Char('s') => apply_tab(app),
        KeyCode::Char('b') => backup_now(app),
        KeyCode::Char('p') => save_preset_now(app),
        KeyCode::Char('X') => restore_now(app),
        KeyCode::Char('w') => raw_now(app),
        _ => {}
    }
}

fn start_edit(app: &mut App) {
    let (field, cur) = match (app.tab, app.cursor) {
        (Tab::Dpi, 0..=6) => {
            let i = app.cursor;
            let cur = app.settings.as_ref().and_then(|s| s.dpi_x.get(i).copied()).unwrap_or(1600);
            (format!("dpi:{i}"), cur.to_string())
        }
        (Tab::Dpi, 7) => {
            let cur = app.settings.as_ref().map(|s| (s.current_dpi_stage + 1).to_string()).unwrap_or("1".into());
            ("stage".into(), cur)
        }
        (Tab::Performance, 0) => {
            let cur = app.settings.as_ref().map(|s| s.polling_label.clone()).unwrap_or("1000Hz".into());
            ("polling".into(), cur)
        }
        (Tab::Performance, 1) => {
            let cur = app.settings.as_ref().map(|s| s.sensor_preset.clone()).unwrap_or("frenzy".into());
            ("sensor".into(), cur)
        }
        (Tab::Performance, 3) => {
            let cur = app.settings.as_ref().map(|s| s.key_scan_label.clone()).unwrap_or("1000Hz".into());
            ("keyscan".into(), cur)
        }
        (Tab::Sensor, 0) => {
            let cur = app.settings.as_ref().map(|s| s.lod_label.clone()).unwrap_or("1.0".into());
            ("lod".into(), cur)
        }
        (Tab::Sensor, 1) => {
            let cur = app.settings.as_ref().map(|s| s.angle.to_string()).unwrap_or("0".into());
            ("angle".into(), cur)
        }
        (Tab::Wireless, 0) => ("rfboost".into(), app.settings.as_ref().map(|s| if s.rf_boost {"maximum"} else {"adaptive"}.into()).unwrap_or("maximum".into())),
        (Tab::Wireless, 1) => ("rfproto".into(), app.settings.as_ref().map(|s| s.rf_proto_label.clone()).unwrap_or("turbo".into())),
        (Tab::Power, 0) => {
            let cur = app.settings.as_ref().map(|s| s.sleep_min.to_string()).unwrap_or("10".into());
            ("sleep".into(), cur)
        }
        (Tab::Presets, _) => {
            let n = app.presets.len();
            if app.cursor < n && !app.presets.is_empty() {
                let p = &app.presets[app.cursor];
                let msg = format!("Apply preset '{}'? (y/n)", p.name);
                app.mode = Mode::Confirm { message: msg, action: PendingAction::ApplyPreset(app.cursor) };
            }
            return;
        }
        (Tab::Diag, 1) => {
            match app.bridge.pair_query() {
                Ok(v) => app.mode = Mode::Message { text: format!("pair query: {v}") },
                Err(e) => app.mode = Mode::Message { text: format!("pair query failed: {e:#}") },
            }
            return;
        }
        _ => return,
    };
    app.mode = Mode::Editing { field, value: cur };
}

fn finish_edit(app: &mut App, field: &str, value: &str) {
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
        "keyscan" => {
            vec!["--key-scan".into(), value.into(), "--profile".into(), prof]
        }
        "lod" => vec!["--lod".into(), value.into(), "--profile".into(), prof],
        "angle" => {
            let a: i64 = value.parse().unwrap_or(999);
            if let Err(e) = model::check_angle(a) { app.mode = Mode::Message { text: e.to_string() }; return; }
            vec!["--angle".into(), a.to_string(), "--profile".into(), prof]
        }
        "rfboost" => vec!["--rf-boost".into(), value.into(), "--profile".into(), prof],
        "rfproto" => vec!["--rf-protocol".into(), value.into()],
        "sleep" => {
            let m: i64 = value.parse().unwrap_or(-1);
            if let Err(e) = model::check_sleep(m) { app.mode = Mode::Message { text: e.to_string() }; return; }
            vec!["--sleep".into(), m.to_string(), "--profile".into(), prof]
        }
        _ => { app.mode = Mode::Normal; return; }
    };
    let msg = format!("Apply rapoo set {}? (y/n)", args.join(" "));
    app.mode = Mode::Confirm { message: msg, action: PendingAction::Set(args) };
}

fn toggle(app: &mut App) {
    let prof = app.bridge.profile.to_string();
    let args: Option<Vec<String>> = match (app.tab, app.cursor) {
        (Tab::Sensor, 2) => {
            let cur = app.settings.as_ref().map(|s| s.motion).unwrap_or(false);
            Some(vec!["--motion-sync".into(), if cur {"off"} else {"on"}.into(), "--profile".into(), prof])
        }
        (Tab::Sensor, 3) => {
            let cur = app.settings.as_ref().map(|s| s.glass).unwrap_or(false);
            Some(vec!["--glass".into(), if cur {"off"} else {"on"}.into(), "--profile".into(), prof])
        }
        (Tab::Wireless, 0) => {
            let cur = app.settings.as_ref().map(|s| s.rf_boost).unwrap_or(true);
            Some(vec!["--rf-boost".into(), if cur {"adaptive"} else {"maximum"}.into(), "--profile".into(), prof])
        }
        (Tab::Power, 1) => {
            let cur = app.settings.as_ref().map(|s| s.low_bat_light).unwrap_or(false);
            Some(vec!["--low-battery-light".into(), if cur {"off"} else {"on"}.into(), "--profile".into(), prof])
        }
        (Tab::Power, 2) => {
            let cur = app.settings.as_ref().map(|s| s.dc_switch).unwrap_or(false);
            Some(vec!["--dc-switch".into(), if cur {"off"} else {"on"}.into(), "--profile".into(), prof])
        }
        _ => None,
    };
    if let Some(a) = args {
        let msg = format!("Apply rapoo set {}? (y/n)", a.join(" "));
        app.mode = Mode::Confirm { message: msg, action: PendingAction::Set(a) };
    }
}

fn apply_tab(app: &mut App) {
    // 's' on DPI active-stage row switches stage; elsewhere no-op hint.
    if app.tab == Tab::Dpi && app.cursor == 7 {
        start_edit(app);
    }
}

fn backup_now(app: &mut App) {
    let path = format!("/tmp/rapoo-tui-backup-{}.json", app.bridge.profile);
    app.mode = Mode::Confirm { message: format!("Backup to {path}? (y/n)"), action: PendingAction::Backup(path) };
}

fn restore_now(app: &mut App) {
    let path = format!("/tmp/rapoo-tui-backup-{}.json", app.bridge.profile);
    if !std::path::Path::new(&path).is_file() {
        app.mode = Mode::Message { text: format!("no backup at {path} (press b first)") };
        return;
    }
    app.mode = Mode::Confirm { message: format!("Restore from {path}? (y/n)"), action: PendingAction::Restore(path) };
}

fn save_preset_now(app: &mut App) {
    if let Some(s) = &app.settings {
        match crate::presets::save_preset("tui-snapshot", "saved from rapoo-tui", &s.raw) {
            Ok(p) => { app.last_ok = Some(format!("saved {}", p.display())); app.presets = crate::presets::list_presets(); }
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
        PendingAction::Set(args) => {
            let refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
            match app.bridge.set(&refs) {
                Ok(out) => { app.last_ok = Some(out.lines().next().unwrap_or("applied").into()); app.push_log(format!("set ok: {}", args.join(" "))); }
                Err(e) => { app.mode = Mode::Message { text: format!("set failed: {e:#}") }; return; }
            }
            app.mode = Mode::Normal;
            app.refresh_all();
        }
        PendingAction::Backup(path) => {
            match app.bridge.backup(&path) {
                Ok(_) => app.last_ok = Some(format!("backup -> {path}")),
                Err(e) => { app.mode = Mode::Message { text: format!("backup failed: {e:#}") }; return; }
            }
            app.mode = Mode::Normal;
        }
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
            if let Some(p) = app.presets.get(i).cloned() {
                apply_preset(app, &p);
            }
        }
        PendingAction::Quit => app.should_quit = true,
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
    if args.is_empty() { app.mode = Mode::Message { text: "preset has no CLI-mappable keys".into() }; return; }
    let refs2: Vec<&str> = args.iter().map(|x| x.as_str()).collect();
    match app.bridge.set(&refs2) {
        Ok(_) => { app.last_ok = Some(format!("preset '{}' applied", p.name)); app.refresh_all(); }
        Err(e) => app.mode = Mode::Message { text: format!("preset failed: {e:#}") },
    }
}
