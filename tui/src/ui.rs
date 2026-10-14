//! ratatui rendering.
use crate::app::{App, Mode, Tab};
use crate::rows;
use ratatui::{layout::{Constraint, Direction, Layout}, style::{Color, Modifier, Style}, text::{Line, Span}, widgets::{Block, Borders, List, ListItem, Paragraph}};

pub fn draw(f: &mut ratatui::Frame, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(8), Constraint::Length(3), Constraint::Length(3)])
        .split(f.area());
    // header
    let bat = app.status.as_ref().and_then(|s| s.get("battery_percent")).map(|v| v.to_string()).unwrap_or("?".into());
    let header = Paragraph::new(vec![
        Line::from(vec![
            Span::styled(" rapoo-tui ", Style::default().fg(Color::Black).bg(Color::Green).add_modifier(Modifier::BOLD)),
            Span::raw(format!("  profile {}  battery {}%  [{}]", app.bridge.profile, bat, app.bridge.rapoo_bin)),
        ]),
        Line::from(tabs_line(app)),
    ])
    .block(Block::default().borders(Borders::ALL));
    f.render_widget(header, chunks[0]);
    // body rows
    let items: Vec<ListItem> = rows::rows(app).into_iter().enumerate().map(|(i, (k, v))| {
        let st = if i == app.cursor { Style::default().bg(Color::DarkGray).add_modifier(Modifier::BOLD) } else { Style::default() };
        ListItem::new(Line::from(vec![
            Span::styled(format!(" {k:22} "), st),
            Span::styled(v, st),
        ]))
    }).collect();
    let title = format!(" {} ", app.tab.title());
    let list = List::new(items).block(Block::default().borders(Borders::ALL).title(title));
    f.render_widget(list, chunks[1]);
    // status
    let msg = if let Some(e) = &app.last_error { format!("ERR: {}", e.lines().next().unwrap_or("")) }
    else if let Some(o) = &app.last_ok { format!("OK: {o}") }
    else { "R refresh | Enter edit | Space toggle | s/b/p/w | q quit".into() };
    f.render_widget(Paragraph::new(msg).block(Block::default().borders(Borders::ALL).title(" status ")), chunks[2]);
    // mode line
    let mode_txt = match &app.mode {
        Mode::Normal => "-- NORMAL --  Tab/1-8 tabs  Up/Down move".to_string(),
        Mode::Editing { field, value } => format!("EDIT {field}: {value}_ (Enter ok, Esc cancel)"),
        Mode::Confirm { message, .. } => message.to_string(),
        Mode::Message { text } => format!("{text}  (any key)"),
    };
    f.render_widget(Paragraph::new(mode_txt), chunks[3]);
}

fn tabs_line(app: &App) -> Vec<Span<'static>> {
    let mut v = vec![];
    for t in Tab::ALL {
        let s = if t == app.tab {
            Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD)
        } else { Style::default().fg(Color::Gray) };
        v.push(Span::styled(format!(" {} ", t.title()), s));
    }
    v
}
