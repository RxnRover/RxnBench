"""
App-wide color themes for Rxn Bench UI.

All color decisions live here. To adjust the palette change these values;
nothing else needs to touch hex codes.

Primary brand colors: orange (#f97316) and blue (#3b82f6).
"""

# Dark theme (default) - dark navy bg, orange + blue accents
DARK = {
    # Base surfaces
    "bg":           "#0f1117",
    "bg_surface":   "#161b27",
    "bg_raised":    "#1c2333",
    "bg_hover":     "#222840",

    # Borders
    "border":       "#2a3050",
    "border_focus": "#f97316",

    # Text
    "text":         "#e2e8f0",
    "text_muted":   "#64748b",
    "text_dim":     "#475569",

    # Primary accent (orange)
    "accent":       "#f97316",
    "accent_dim":   "#7c3800",
    "accent_text":  "#fff7ed",

    # Secondary accent (blue)
    "accent2":      "#3b82f6",
    "accent2_dim":  "#1e3a5f",
    "accent2_text": "#eff6ff",

    # Semantic
    "success":      "#22c55e",
    "warning":      "#f97316",
    "error":        "#ef4444",
    "error_bg":     "#7f1d1d",
    "error_text":   "#fca5a5",
    "error_border": "#ef4444",

    # UI widgets
    "btn_bg":       "#1c2333",
    "btn_hover":    "#222840",
    "btn_pressed":  "#0f1117",
    "dot_ok":       "#22c55e",
    "dot_warn":     "#f97316",
    "dot_err":      "#ef4444",

    # Device panel / widget surfaces (slightly raised above the MDI canvas)
    "widget_bg":    "#1c2333",

    # Server cards
    "card_bg":      "#1c2333",
    "card_border":  "#3a4570",

    # Grid / canvas
    "grid_bg":       "#0a0d14",
    "grid_line":     "#1a2035",
    "grid_border":   "#3a3a5c",
    "grid_rail":     "#1e3a5f",
    "grid_carriage": "#3a4570",
    "grid_text":     "#555555",
    "grid_pos":      "#f97316",
    "grid_tip":      "#fb923c",
    "grid_foot":     "#3b82f6",
    "grid_foot_fill_alpha": 40,
}

# Light theme - white bg, same orange/blue accents
LIGHT = {
    "bg":           "#f8fafc",
    "bg_surface":   "#f1f5f9",
    "bg_raised":    "#e2e8f0",
    "bg_hover":     "#cbd5e1",

    "border":       "#cbd5e1",
    "border_focus": "#f97316",

    "text":         "#0f172a",
    "text_muted":   "#64748b",
    "text_dim":     "#94a3b8",

    "accent":       "#f97316",
    "accent_dim":   "#c2560a",
    "accent_text":  "#ffffff",

    "accent2":      "#2563eb",
    "accent2_dim":  "#bfdbfe",
    "accent2_text": "#1e3a8a",

    "success":      "#16a34a",
    "warning":      "#f97316",
    "error":        "#dc2626",
    "error_bg":     "#fee2e2",
    "error_text":   "#7f1d1d",
    "error_border": "#ef4444",

    "btn_bg":       "#e2e8f0",
    "btn_hover":    "#cbd5e1",
    "btn_pressed":  "#94a3b8",
    "dot_ok":       "#16a34a",
    "dot_warn":     "#f97316",
    "dot_err":      "#dc2626",

    # Device panel / widget surfaces (lighter than the MDI canvas in light mode)
    "widget_bg":    "#ffffff",

    # Server cards
    "card_bg":      "#ffffff",
    "card_border":  "#94a3b8",

    "grid_bg":       "#f1f5f9",
    "grid_line":     "#cbd5e1",
    "grid_border":   "#94a3b8",
    "grid_rail":     "#bfdbfe",
    "grid_carriage": "#93c5fd",
    "grid_text":     "#64748b",
    "grid_pos":      "#ea6c00",
    "grid_tip":      "#f97316",
    "grid_foot":     "#2563eb",
    "grid_foot_fill_alpha": 30,
}

_THEMES = {"dark": DARK, "light": LIGHT}


def get(name: str) -> dict:
    """Return a theme dict by name, defaulting to DARK."""
    return _THEMES.get(name, DARK)


def _x_icon(color: str) -> str:
    """Return a CSS url() value containing an inline SVG x for QTabBar close buttons."""
    c = color.replace('#', '%23')
    return (
        "url(\"data:image/svg+xml,"
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 10'>"
        "<path d='M2.5 2.5 L7.5 7.5 M7.5 2.5 L2.5 7.5' "
        "stroke='" + c + "' stroke-width='1.6' stroke-linecap='round'/>"
        "</svg>\")"
    )


def build_qss(t: dict) -> str:
    """Build a QSS stylesheet string from a theme dict."""
    return f"""
        QMainWindow, QWidget {{
            background: {t['bg']};
            color: {t['text']};
            font-family: "Segoe UI", "Inter", sans-serif;
        }}
        QTabWidget::pane {{
            border: 1px solid {t['border']};
            background: {t['bg_surface']};
        }}
        QTabBar::tab {{
            background: {t['bg_surface']};
            color: {t['text_muted']};
            padding: 6px 16px;
            border: 1px solid {t['border']};
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}
        QTabBar::tab:selected {{
            background: {t['bg_raised']};
            color: {t['text']};
            border-bottom: 2px solid {t['accent']};
        }}
        QTabBar::tab:hover {{ background: {t['bg_hover']}; }}
        QGroupBox {{
            border: 1px solid {t['border']};
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 4px;
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            color: {t['text_muted']};
        }}
        QPushButton {{
            background: {t['btn_bg']};
            color: {t['text']};
            border: 1px solid {t['border']};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        QPushButton:hover   {{ background: {t['btn_hover']}; }}
        QPushButton:pressed {{ background: {t['btn_pressed']}; }}
        QPushButton:disabled {{
            color: {t['text_dim']};
            background: {t['bg_surface']};
            border-color: {t['border']};
        }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            background: {t['bg_raised']};
            color: {t['text']};
            border: 1px solid {t['border']};
            border-radius: 3px;
            padding: 2px 6px;
        }}
        QLineEdit:focus, QComboBox:focus {{
            border-color: {t['border_focus']};
        }}
        QComboBox::drop-down {{ border: none; }}
        QScrollBar:vertical {{
            background: {t['bg_surface']};
            width: 8px;
        }}
        QScrollBar::handle:vertical {{
            background: {t['border']};
            border-radius: 4px;
        }}
        QLabel {{ background: transparent; }}
        QMdiSubWindow {{
            background: {t['widget_bg']};
            border: 2px solid {t['border']};
        }}
        QMdiArea {{
            border: none;
        }}
        QMenuBar {{
            background: {t['bg_surface']};
            color: {t['text']};
            border-bottom: 1px solid {t['border']};
        }}
        QMenuBar::item:selected {{ background: {t['bg_hover']}; }}
        QMenu {{
            background: {t['bg_raised']};
            color: {t['text']};
            border: 1px solid {t['border']};
        }}
        QMenu::item:selected {{ background: {t['bg_hover']}; }}
    """
