mod actions;
mod app;
mod bridge;
mod model;
mod presets;
mod proto;
mod rows;
mod ui;

use anyhow::Result;
use app::{App, Mode};
use bridge::Bridge;
use crossterm::{event::{self, Event}, execute, terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen}};
use ratatui::{backend::CrosstermBackend, Terminal};
use std::io::{self, IsTerminal, Write};
use std::time::Duration;

fn parse_args() -> (u8, f64) {
    let mut profile: u8 = 0;
    let mut timeout = 10.0;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--profile" => profile = it.next().and_then(|v| v.parse().ok()).unwrap_or(0),
            "--timeout" => timeout = it.next().and_then(|v| v.parse().ok()).unwrap_or(10.0),
            "--help" | "-h" => {
                println!("rapoo-tui [--profile 0-7] [--timeout SECS]");
                println!("Frontend over the `rapoo` Python CLI (subprocess --json).");
                std::process::exit(0);
            }
            _ => {}
        }
    }
    (profile, timeout)
}

fn main() -> Result<()> {
    let (profile, timeout) = parse_args();
    if !io::stdout().is_terminal() {
        eprintln!("rapoo-tui needs a TTY. Use `rapoo get/status` instead.");
        return Ok(());
    }
    let mut b = Bridge::detect();
    b.profile = profile.min(7);
    b.timeout_s = timeout;
    let mut app = App::new(b);

    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut term = Terminal::new(backend)?;

    // first frame immediately, then load device state
    app.mode = Mode::Message { text: "loading device state (list/get/status)...".into() };
    term.draw(|f| ui::draw(f, &app))?;
    app.refresh_all();
    app.mode = Mode::Normal;

    loop {
        term.draw(|f| ui::draw(f, &app))?;
        if app.should_quit { break; }
        if event::poll(Duration::from_millis(200))? {
            if let Event::Key(k) = event::read()? {
                actions::on_key(&mut app, k);
            }
        }
    }
    disable_raw_mode()?;
    execute!(term.backend_mut(), LeaveAlternateScreen)?;
    io::stdout().flush()?;
    Ok(())
}
