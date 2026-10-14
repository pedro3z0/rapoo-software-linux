//! App state: tabs, selection, cached settings/status, edit + confirm flows.

use crate::bridge::Bridge;
use crate::model::Settings;
use serde_json::Value;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tab {
    Dashboard, Dpi, Performance, Sensor, Wireless, Power, Presets, Diag,
}

impl Tab {
    pub const ALL: [Tab; 8] = [
        Tab::Dashboard, Tab::Dpi, Tab::Performance, Tab::Sensor,
        Tab::Wireless, Tab::Power, Tab::Presets, Tab::Diag,
    ];
    pub fn title(self) -> &'static str {
        match self {
            Tab::Dashboard => "1 Dashboard",
            Tab::Dpi => "2 DPI",
            Tab::Performance => "3 Performance",
            Tab::Sensor => "4 Sensor",
            Tab::Wireless => "5 Wireless",
            Tab::Power => "6 Power",
            Tab::Presets => "7 Presets",
            Tab::Diag => "8 Diag",
        }
    }
    pub fn rows(self, app: &App) -> usize {
        match self {
            Tab::Dashboard => 6,
            Tab::Dpi => 9,
            Tab::Performance => 5,
            Tab::Sensor => 7,
            Tab::Wireless => 3,
            Tab::Power => 4,
            Tab::Presets => app.presets.len().max(1) + 2,
            Tab::Diag => 5,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Mode {
    Normal,
    Editing { field: String, value: String },
    Confirm { message: String, action: PendingAction },
    Message { text: String },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PendingAction {
    Set(Vec<String>),
    Backup(String),
    Restore(String),
    ApplyPreset(usize),
    Quit,
}

pub struct App {
    pub bridge: Bridge,
    pub tab: Tab,
    pub cursor: usize,
    pub mode: Mode,
    pub settings: Option<Settings>,
    pub status: Option<Value>,
    pub list_text: String,
    pub last_error: Option<String>,
    pub last_ok: Option<String>,
    pub presets: Vec<crate::presets::Preset>,
    pub log: Vec<String>,
    pub should_quit: bool,
}

impl App {
    pub fn new(bridge: Bridge) -> Self {
        let presets = crate::presets::list_presets();
        App { bridge, tab: Tab::Dashboard, cursor: 0, mode: Mode::Normal,
            settings: None, status: None, list_text: String::new(),
            last_error: None, last_ok: None, presets, log: vec![], should_quit: false }
    }
    pub fn push_log(&mut self, s: impl Into<String>) {
        self.log.push(s.into());
        if self.log.len() > 200 { self.log.remove(0); }
    }
    pub fn refresh_all(&mut self) {
        self.last_error = None;
        self.last_ok = None;
        match self.bridge.list_text() {
            Ok(t) => self.list_text = t,
            Err(e) => { self.last_error = Some(format!("list: {e:#}")); self.push_log(format!("list failed: {e:#}")); }
        }
        match self.bridge.get() {
            Ok(v) => { self.settings = Some(Settings::from_json(&v)); self.push_log("get ok"); }
            Err(e) => { self.last_error = Some(format!("get: {e:#}")); self.push_log(format!("get failed: {e:#}")); }
        }
        match self.bridge.status() {
            Ok(v) => { self.status = Some(v); self.push_log("status ok"); }
            Err(e) => { self.push_log(format!("status: {e:#}")); }
        }
        self.presets = crate::presets::list_presets();
    }
    pub fn next_tab(&mut self) {
        let i = Tab::ALL.iter().position(|t| *t == self.tab).unwrap_or(0);
        self.tab = Tab::ALL[(i + 1) % Tab::ALL.len()];
        self.cursor = 0;
    }
    pub fn prev_tab(&mut self) {
        let i = Tab::ALL.iter().position(|t| *t == self.tab).unwrap_or(0);
        self.tab = Tab::ALL[(i + Tab::ALL.len() - 1) % Tab::ALL.len()];
        self.cursor = 0;
    }
    pub fn goto_tab(&mut self, n: usize) {
        if n < Tab::ALL.len() { self.tab = Tab::ALL[n]; self.cursor = 0; }
    }
    pub fn move_cursor(&mut self, delta: i32) {
        let n = self.tab.rows(self).max(1) as i32;
        self.cursor = (self.cursor as i32 + delta).rem_euclid(n) as usize;
    }
}
