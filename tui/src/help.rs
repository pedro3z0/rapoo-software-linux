//! Self-documenting help popup (`?` / F1), modeled on the monsgeek keybind table.

use ratatui::{
    layout::Alignment,
    style::{Color, Modifier, Style},
    text::Line,
    widgets::{Block, Borders, Clear, Paragraph},
    Frame,
};

/// Single source of truth: what the TUI actually does.
pub const KEYS: &[(&str, &str)] = &[
    ("q / Esc", "Quit"),
    ("Tab / Shift+Tab, 1-8", "Switch tabs"),
    ("Up/Down or j/k", "Move selection"),
    ("Left/Right or h/l", "Cycle / step value - applies immediately"),
    ("Enter", "Edit exact value in the status bar, applies on Enter"),
    ("Space", "Toggle on/off rows (same as Right)"),
    ("s", "DPI tab: switch active stage to selected row"),
    ("R", "Refresh device (list + get + status)"),
    ("p", "Save current settings as named preset"),
    ("b", "Backup to /tmp (instant)"),
    ("X", "Restore that backup (asks y/n)"),
    ("w", "Raw read offset 640 (diagnostics)"),
    ("? / F1", "Toggle this help (any key closes)"),
    ("y/n", "Only for preset apply + restore popups"),
];

pub fn render(f: &mut Frame, area: ratatui::layout::Rect) {
    let h = (KEYS.len() + 3) as u16;
    let popup = crate::ui::centered(area, 66, h);
    f.render_widget(Clear, popup);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan))
        .title(" Help ")
        .title_style(Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD));
    let lines: Vec<Line> = KEYS
        .iter()
        .map(|(k, d)| {
            Line::from(vec![
                ratatui::text::Span::styled(format!(" {k:<24}"), Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD)),
                ratatui::text::Span::styled(d.to_string(), Style::default().fg(Color::White)),
            ])
        })
        .chain([Line::styled(
            " any key closes ",
            Style::default().fg(Color::DarkGray),
        )])
        .collect();
    f.render_widget(
        Paragraph::new(lines)
            .block(block)
            .alignment(Alignment::Left),
        popup,
    );
}
