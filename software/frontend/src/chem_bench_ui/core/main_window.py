from __future__ import annotations

from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMdiArea, QMdiSubWindow,
    QPushButton, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from ..discovery import DiscoveredServer
from .. import themes
from .server_browser import ServerBrowserDialog
from .device_registry import panel_for
from .experiment_panel import ExperimentPanel
from .csv_viewer import CsvViewerPanel
from .experiment_notes import ExperimentNotesPanel


class _CoreSubWindow(QMdiSubWindow):
    """MDI subwindow that hides (not deletes) on close and unchecks its menu action."""

    def __init__(self, action: QAction, on_close) -> None:
        super().__init__()
        self._action = action
        self._on_close = on_close

    def closeEvent(self, event) -> None:
        self._action.setChecked(False)
        self._on_close()
        self.hide()
        event.ignore()


_CORE_PANELS: list[tuple[str, type]] = [
    ("Experiment Runner", ExperimentPanel),
    ("CSV Viewer",        CsvViewerPanel),
    ("Experiment Notes",  ExperimentNotesPanel),
]


class _Workspace:
    """State for one workspace tab."""

    def __init__(
        self,
        widget:      QStackedWidget,
        mdi:         QMdiArea,
        empty_title: QLabel,
        empty_hint:  QLabel,
    ) -> None:
        self.widget      = widget        # the tab's content widget (= stack)
        self.mdi         = mdi
        self.empty_title = empty_title
        self.empty_hint  = empty_hint
        self.core_subs:  dict[str, _CoreSubWindow] = {}
        self.core_open:  set[str] = set()


class MainWindow(QMainWindow):
    def __init__(self, theme_name: str = "dark") -> None:
        super().__init__()
        self._theme_name = theme_name
        self._t = themes.get(theme_name)

        self.setWindowTitle("Rxn Bench")
        self.setMinimumSize(1024, 700)
        self.resize(1280, 820)

        self._win_actions:    dict[str, QAction] = {}
        self._workspaces:     list[_Workspace] = []
        self._current_ws_idx: int = 0
        self._close_btns:     list[QPushButton] = []

        self._build_menu()
        self._build_central()

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def _ws(self) -> _Workspace:
        return self._workspaces[self._current_ws_idx]

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        quit_act = file_menu.addAction("Quit")
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)

        settings_menu = self.menuBar().addMenu("Settings")
        theme_menu = settings_menu.addMenu("Theme")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        for name, label in [("dark", "Dark"), ("light", "Light")]:
            act = theme_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(name == self._theme_name)
            act.setData(name)
            act.triggered.connect(lambda checked, n=name: self._set_theme(n))
            self._theme_group.addAction(act)

        view_menu = self.menuBar().addMenu("View")
        for name, _ in _CORE_PANELS:
            act = view_menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(False)
            act.triggered.connect(
                lambda checked, n=name: self._toggle_core_panel(n, checked)
            )
            self._win_actions[name] = act

    def _set_theme(self, name: str) -> None:
        if name == self._theme_name:
            return
        self._theme_name = name
        self._t = themes.get(name)
        t = self._t

        QApplication.instance().setStyleSheet(themes.build_qss(t))

        for ws in self._workspaces:
            ws.mdi.setBackground(QBrush(QColor(t["bg_surface"])))
            ws.empty_title.setStyleSheet(
                f"color: {t['text']}; font-size: 14pt; font-weight: bold;"
            )
            ws.empty_hint.setStyleSheet(f"color: {t['text_muted']};")
            for sub in ws.mdi.subWindowList():
                panel = sub.widget()
                if panel and hasattr(panel, "set_theme"):
                    panel.set_theme(t)

        if hasattr(self, "_browser"):
            self._browser.set_theme(t)

        if hasattr(self, "_add_ws_btn"):
            self._style_add_ws_btn()

        style = self._close_btn_style()
        for btn in self._close_btns:
            try:
                btn.setStyleSheet(style)
            except RuntimeError:
                pass

    def _close_btn_style(self) -> str:
        t = self._t
        return f"""
            QPushButton {{
                font-size: 13px;
                font-weight: bold;
                color: {t['text_muted']};
                background: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton:hover {{
                color: {t['text']};
                background: {t['bg_hover']};
                border-color: {t['border']};
            }}
            QPushButton:pressed {{
                background: {t['border']};
            }}
        """

    def _make_close_btn(self, ws: _Workspace) -> QPushButton:
        btn = QPushButton("×")
        btn.setFixedSize(18, 18)
        btn.setToolTip("Close workspace")
        btn.setStyleSheet(self._close_btn_style())
        btn.clicked.connect(lambda: self._close_workspace_for(ws))
        self._close_btns.append(btn)
        return btn

    def _close_workspace_for(self, ws: _Workspace) -> None:
        if len(self._workspaces) <= 1:
            return
        idx = self._main_tabs.indexOf(ws.widget)
        if idx >= 0:
            self._close_workspace(idx)

    def _style_add_ws_btn(self) -> None:
        t = self._t
        self._add_ws_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 16px;
                font-weight: bold;
                background: {t['bg_raised']};
                color: {t['text']};
                border: 1px solid {t['border']};
                border-radius: 5px;
            }}
            QPushButton:hover   {{ background: {t['accent']}; color: {t['accent_text']};
                                   border-color: {t['accent']}; }}
            QPushButton:pressed {{ background: {t['accent_dim']}; color: {t['accent_text']};
                                   border-color: {t['accent_dim']}; }}
        """)

    # ------------------------------------------------------------------
    # Central widget: tab bar with multiple workspaces + Add Device
    # ------------------------------------------------------------------

    def _build_central(self) -> None:
        self._main_tabs = QTabWidget()
        self._main_tabs.setTabsClosable(False)
        self._main_tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self._main_tabs)

        # First workspace tab
        ws = self._make_workspace()
        self._workspaces.append(ws)
        self._main_tabs.addTab(ws.widget, "Workspace 1")
        self._main_tabs.tabBar().setTabButton(
            0, self._main_tabs.tabBar().ButtonPosition.RightSide,
            self._make_close_btn(ws),
        )

        # + Add Device tab (permanent, no close button)
        add_dev_page = self._build_add_device()
        self._main_tabs.addTab(add_dev_page, "+ Add Device")

        # Corner "+" button to add new workspaces
        self._add_ws_btn = QPushButton("+")
        self._add_ws_btn.setToolTip("New workspace")
        self._add_ws_btn.setFixedSize(32, 26)
        self._add_ws_btn.clicked.connect(self._add_workspace)
        self._style_add_ws_btn()

        corner = QWidget()
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(4, 4, 6, 4)
        cl.addWidget(self._add_ws_btn)
        self._main_tabs.setCornerWidget(corner, Qt.TopRightCorner)

    def _make_workspace(self) -> _Workspace:
        stack = QStackedWidget()

        # Page 0 — empty state
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.addStretch()
        title = QLabel("No devices connected.")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {self._t['text']}; font-size: 14pt; font-weight: bold;"
        )
        hint = QLabel(
            "Open the + Add Device tab to discover and connect to SiLA servers."
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {self._t['text_muted']};")
        el.addWidget(title)
        el.addSpacing(8)
        el.addWidget(hint)
        el.addStretch()
        stack.addWidget(empty)

        # Page 1 — MDI canvas
        mdi = QMdiArea()
        mdi.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        mdi.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        mdi.setBackground(QBrush(QColor(self._t["bg_surface"])))
        stack.addWidget(mdi)

        ws = _Workspace(widget=stack, mdi=mdi, empty_title=title, empty_hint=hint)
        mdi.subWindowActivated.connect(
            lambda sub, w=ws: self._on_mdi_activated(sub, w)
        )
        return ws

    def _build_add_device(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._browser = ServerBrowserDialog(theme_name=self._theme_name, parent=page)
        self._browser.device_requested.connect(self._on_device_requested)
        layout.addWidget(self._browser)
        return page

    def _add_workspace(self) -> None:
        ws = self._make_workspace()
        self._workspaces.append(ws)
        n = len(self._workspaces)
        insert_idx = self._main_tabs.count() - 1  # before "+ Add Device"
        self._main_tabs.insertTab(insert_idx, ws.widget, f"Workspace {n}")
        self._main_tabs.tabBar().setTabButton(
            insert_idx, self._main_tabs.tabBar().ButtonPosition.RightSide,
            self._make_close_btn(ws),
        )
        self._main_tabs.setCurrentIndex(insert_idx)
        for name, _ in _CORE_PANELS:
            self._win_actions[name].setChecked(False)

    def _on_tab_changed(self, idx: int) -> None:
        add_dev_idx = self._main_tabs.count() - 1
        if idx == add_dev_idx or idx >= len(self._workspaces):
            return  # "+ Add Device" or out-of-range during construction
        self._current_ws_idx = idx
        # Sync View menu checked states with the newly active workspace
        for name, _ in _CORE_PANELS:
            self._win_actions[name].setChecked(name in self._workspaces[idx].core_open)

    def _close_workspace(self, tab_idx: int) -> None:
        ws = self._workspaces[tab_idx]

        # Block MDI subwindow destroyed signals before deletion cascade
        for sub in ws.mdi.subWindowList():
            sub.blockSignals(True)
            uuid = sub.property("server_uuid")
            if uuid:
                self._browser.set_device_connected(uuid, False)

        # Uncheck View menu actions for panels in this workspace
        for name in list(ws.core_open):
            self._win_actions[name].setChecked(False)

        # Remove from list and fix current index
        self._workspaces.pop(tab_idx)
        if self._current_ws_idx >= len(self._workspaces):
            self._current_ws_idx = len(self._workspaces) - 1

        # Remove close button reference before Qt deletes it with the tab
        bar = self._main_tabs.tabBar()
        btn = bar.tabButton(tab_idx, bar.ButtonPosition.RightSide)
        if btn in self._close_btns:
            self._close_btns.remove(btn)

        self._main_tabs.removeTab(tab_idx)

        # Renumber remaining workspace tabs so they're always 1, 2, 3…
        for i in range(len(self._workspaces)):
            self._main_tabs.setTabText(i, f"Workspace {i + 1}")

        self._update_workspace_stack()

    # ------------------------------------------------------------------
    # Core panel management (View menu)
    # ------------------------------------------------------------------

    def _toggle_core_panel(self, name: str, checked: bool) -> None:
        if checked:
            self._show_core_panel(name)
        else:
            ws = self._ws
            ws.core_open.discard(name)
            sub = ws.core_subs.get(name)
            if sub is not None:
                sub.hide()
            self._update_workspace_stack()

    def _show_core_panel(self, name: str) -> None:
        ws = self._ws
        if name not in ws.core_subs:
            cls = dict(_CORE_PANELS)[name]
            panel = cls(self._t)
            act = self._win_actions[name]
            sub = _CoreSubWindow(
                action=act,
                on_close=partial(self._on_core_panel_closed, name, ws),
            )
            sub.setWidget(panel)
            sub.setWindowTitle(name)
            sub.setProperty("panel_name", name)
            size = getattr(panel, "preferred_mdi_size", (680, 480))
            sub.resize(*size)
            ws.mdi.addSubWindow(sub)
            ws.core_subs[name] = sub

        ws.core_open.add(name)
        self._win_actions[name].setChecked(True)
        sub = ws.core_subs[name]
        sub.show()
        ws.mdi.setActiveSubWindow(sub)
        ws.widget.setCurrentIndex(1)
        self._main_tabs.setCurrentIndex(self._current_ws_idx)

    def _on_core_panel_closed(self, name: str, ws: _Workspace) -> None:
        ws.core_open.discard(name)
        if ws is self._ws:
            self._update_workspace_stack()

    # ------------------------------------------------------------------
    # Device panel management
    # ------------------------------------------------------------------

    def _on_device_requested(self, server: DiscoveredServer) -> None:
        ws = self._ws
        # Check if already open in the current workspace
        for sub in ws.mdi.subWindowList():
            if sub.property("server_uuid") == server.uuid:
                ws.mdi.setActiveSubWindow(sub)
                self._main_tabs.setCurrentIndex(self._current_ws_idx)
                return

        panel = panel_for(server, self._t)
        sub = QMdiSubWindow()
        sub.setWidget(panel)
        sub.setWindowTitle(server.name)
        sub.setProperty("server_uuid", server.uuid)
        sub.setAttribute(Qt.WA_DeleteOnClose)
        w, h = getattr(panel, "preferred_mdi_size", (720, 520))
        sub.resize(w, h)
        ws.mdi.addSubWindow(sub)
        sub.setAttribute(Qt.WA_OpaquePaintEvent)
        sub.destroyed.connect(partial(self._on_device_closed, server.uuid, ws))
        sub.show()

        self._browser.set_device_connected(server.uuid, True)
        ws.widget.setCurrentIndex(1)
        self._main_tabs.setCurrentIndex(self._current_ws_idx)

    def _on_device_closed(self, uuid: str, ws: _Workspace) -> None:
        self._browser.set_device_connected(uuid, False)
        if ws is self._ws:
            self._update_workspace_stack()

    def _update_workspace_stack(self) -> None:
        ws = self._ws
        has_device = any(sub.property("server_uuid") for sub in ws.mdi.subWindowList())
        ws.widget.setCurrentIndex(1 if (has_device or ws.core_open) else 0)

    def _on_mdi_activated(self, sub: QMdiSubWindow | None, ws: _Workspace) -> None:
        if sub is None and ws is self._ws:
            self._update_workspace_stack()
