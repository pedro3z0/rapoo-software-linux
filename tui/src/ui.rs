//! ratatui rendering — follows the monsgeek reference skeleton:
//! 1-line centered title | 1-line tabs | bordered content list | 1-line status.
//! Editing happens in the status bar; confirms/help are centered popups.

use crate::app::{App, Mode, Tab};
use crate::rows;
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, List, ListItem, Paragraph, Tabs},
    Frame,
};

pub fn draw(f: &mut Frame, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), // title
            Constraint::Length(1), // tabs
            Constraint::Min(10),   // content
            Constraint::Length(1), // status
        ])
        .split(f.area());

    // --- Title row: centered cyan bold + right profile chip (reference style) ---
    let model = rows::device_name(&app.list_text);
    let title_text = if model == "not found" {
        "Rapoo Gaming Mouse - Configuration Tool".to_string()
    } else {
        format!("{model} - Rapoo Configuration Tool")
    };
    let profile_text = format!(" Profile {}/8 ", app.bridge.profile + 1);
    let title_row = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Min(10), Constraint::Length(profile_text.len() as u16)])
        .split(chunks[0]);
    f.render_widget(
        Paragraph::new(title_text)
            .style(Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD))
            .alignment(ratatui::layout::Alignment::Center),
        title_row[0],
    );
    f.render_widget(
        Paragraph::new(profile_text)
            .style(Style::default().fg(Color::Magenta))
            .alignment(ratatui::layout::Alignment::Right),
        title_row[1],
    );

    // --- Tab row: ratatui Tabs + right-aligned nav hint ---
    let tab_hint = " Tab: next  1-8: jump ";
    let tab_row = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Min(10), Constraint::Length(tab_hint.len() as u16)])
        .split(chunks[1]);
    let titles: Vec<&str> = Tab::ALL.iter().map(|t| t.title()).collect();
    let selected = Tab::ALL.iter().position(|t| *t == app.tab).unwrap_or(0);
    f.render_widget(
        Tabs::new(titles)
            .select(selected)
            .style(Style::default().fg(Color::White))
            .highlight_style(Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD))
            .divider("\u{2502}"),
        tab_row[0],
    );
    f.render_widget(
        Paragraph::new(tab_hint)
            .style(Style::default().fg(Color::DarkGray))
            .alignment(ratatui::layout::Alignment::Right),
        tab_row[1],
    );

    // --- Content: bordered list, key hints in the block title ---
    render_content(f, app, chunks[2]);

    // --- Status bar (also the inline editor, reference style) ---
    render_status(f, app, chunks[3]);

    // --- Popups ---
    if app.mode == Mode::Help {
        crate::help::render(f, f.area());
    }
    if let Mode::Confirm { message, .. } = &app.mode {
        render_confirm(f, message);
    }
}

fn render_status(f: &mut Frame, app: &App, area: Rect) {
    // Contextual line: inline editor > message > normal status (reference style).
    let line: Line = match &app.mode {
        Mode::Editing { field, value, label } => Line::from(vec![
            Span::styled(format!(" {label} [{field}]: {value}_"), Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::styled("   Enter: apply  Esc: cancel", Style::default().fg(Color::DarkGray)),
        ]),
        Mode::Message { text } => Line::from(Span::styled(format!(" {text}"), Style::default().fg(Color::Red))),
        _ => {
            let connected = app.settings.is_some();
            let spans = vec![
                Span::styled(
                    format!(" [{}]", if connected { "Connected" } else { "Disconnected" }),
                    Style::default().fg(if connected { Color::Green } else { Color::Red }),
                ),
                battery_span(app),
                Span::styled(
                    format!("|{}", app.settings.as_ref().map(|s| s.polling_label.clone()).unwrap_or_default()),
                    Style::default().fg(Color::Yellow),
                ),
                Span::raw("] "),
                feedback_span(app),
            ];
            Line::from(spans)
        }
    };
    f.render_widget(Paragraph::new(line), area);
}

fn battery_span(app: &App) -> Span<'static> {
    let bat = app.status.as_ref().and_then(|s| s.get("battery_percent").and_then(|v| v.as_u64()));
    match bat {
        Some(p) => {
            let icon = if p > 75 { "\u{2588}" } else if p > 50 { "\u{2586}" } else if p > 25 { "\u{2583}" } else { "\u{2581}" };
            let color = if p > 25 { Color::Green } else { Color::Red };
            Span::styled(format!(" {p}%{icon} "), Style::default().fg(color))
        }
        None => Span::styled(" ?% ", Style::default().fg(Color::DarkGray)),
    }
}

fn feedback_span(app: &App) -> Span<'static> {
    if let Some(e) = &app.last_error {
        Span::styled(truncate(e, 90), Style::default().fg(Color::Red))
    } else if let Some(o) = &app.last_ok {
        Span::styled(format!("{o} | "), Style::default().fg(Color::Green))
    } else {
        Span::styled("?:Help  q:Quit", Style::default().fg(Color::DarkGray))
    }
}

fn truncate(s: &str, n: usize) -> String {
    let first = s.lines().next().unwrap_or("");
    if first.chars().count() > n {
        first.chars().take(n.saturating_sub(1)).collect::<String>() + "~"
    } else {
        first.to_string()
    }
}

fn render_confirm(f: &mut Frame, message: &str) {
    let area = centered(f.area(), 64, 9);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Yellow))
        .title(" Confirm ")
        .title_style(Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD));
    f.render_widget(Clear, area);
    f.render_widget(
        Paragraph::new(message.to_string()).block(block).wrap(ratatui::widgets::Wrap { trim: false }),
        area,
    );
}

/// Centered rect with given size, clamped to the frame.
pub fn centered(area: Rect, w: u16, h: u16) -> Rect {
    let w = w.min(area.width.saturating_sub(2)).max(10);
    let h = h.min(area.height.saturating_sub(2)).max(3);
    Rect::new(
        area.x + area.width.saturating_sub(w) / 2,
        area.y + area.height.saturating_sub(h) / 2,
        w,
        h,
    )
}

fn render_content(f: &mut Frame, app: &App, area: Rect) {
    let rs = rows::rows(app);
    let items: Vec<ListItem> = rs.iter().map(|row| {
        if row.value.is_empty() && row.label.trim().is_empty() {
            return ListItem::new(Line::from(""));
        }
        let mut spans = vec![Span::raw(row.label.clone())];
        let editable = row.field != rows::Field::None;
        if editable {
            spans.push(Span::styled(
                format!("< {} >", row.value),
                Style::default().fg(row.fg).add_modifier(Modifier::BOLD),
            ));
        } else {
            spans.push(Span::styled(row.value.clone(), Style::default().fg(row.fg)));
        }
        if !row.hint.is_empty() {
            spans.push(Span::styled(row.hint.to_string(), Style::default().fg(Color::DarkGray)));
        }
        ListItem::new(Line::from(spans))
    }).collect();

    let title = format!(" {} [{}] ", app.tab.title(), app.tab.hints());
    let list = List::new(items)
        .block(Block::default().borders(Borders::ALL).title(title))
        .highlight_style(Style::default().bg(Color::DarkGray).add_modifier(Modifier::BOLD))
        .highlight_symbol("> ");
    let mut state = ratatui::widgets::ListState::default();
    let max = rs.len().saturating_sub(1);
    state.select(Some(app.cursor.min(max)));
    f.render_stateful_widget(list, area, &mut state);
}
