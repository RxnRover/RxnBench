from __future__ import annotations

from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtGui import QActionGroup, QBrush, QColor
from PySide6.QtWidgets import (
    QApplication, QLabel, QMainWindow, QMdiArea, QMdiSubWindow,
    QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
)

from ..discovery import DiscoveredServer
from .. import themes
from .server_browser import ServerBrowserDialog
from .device_registry import panel_for
from .experiment_panel import ExperimentPanel


class MainWindow(QMainWindow):
    def __init__(self, theme_name: str = "dark") -> None:
        super().__init__()
        self._theme_name = theme_name
        self._t = themes.get(theme_name)

        self.setWindowTitle("Rxn Bench")
        self.setMinimumSize(1024, 700)
        self.resize(1280, 820)

        self._build_menu()
        self._build_central()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        quit_act = file_menu.addAction("Quit")
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)

        exp_menu = self.menuBar().addMenu("Experiment")
        run_act = exp_menu.addAction("Run Script…")
        run_act.setShortcut("Ctrl+R")
        run_act.triggered.connect(self._open_experiment_runner)

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

    def _set_theme(self, name: str) -> None:
        if name == self._theme_name:
            return
        self._theme_name = name
        self._t = themes.get(name)
        t = self._t

        QApplication.instance().setStyleSheet(themes.build_qss(t))
        self._mdi.setBackground(QBrush(QColor(t["bg_surface"])))

        # Re-theme empty-state labels
        if hasattr(self, "_empty_title"):
            self._empty_title.setStyleSheet(
                f"color: {t['text']}; font-size: 14pt; font-weight: bold;"
            )
        if hasattr(self, "_empty_hint"):
            self._empty_hint.setStyleSheet(f"color: {t['text_muted']};")

        # Propagate to the server browser
        if hasattr(self, "_browser"):
            self._browser.set_theme(t)

        # Propagate to all open device panels
        for sub in self._mdi.subWindowList():
            panel = sub.widget()
            if panel and hasattr(panel, "set_theme"):
                panel.set_theme(t)

    def _build_central(self) -> None:
        self._main_tabs = QTabWidget()
        self.setCentralWidget(self._main_tabs)

        self._main_tabs.addTab(self._build_workspace(), "Workspace")
        self._main_tabs.addTab(self._build_add_device(), "+ Add Device")

    def _build_workspace(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._workspace_stack = QStackedWidget()
        layout.addWidget(self._workspace_stack)

        # page 0 — empty state
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.addStretch()
        self._empty_title = QLabel("No devices connected.")
        self._empty_title.setAlignment(Qt.AlignCenter)
        self._empty_title.setStyleSheet(
            f"color: {self._t['text']}; font-size: 14pt; font-weight: bold;"
        )
        self._empty_hint = QLabel(
            "Open the + Add Device tab to discover and connect to SiLA servers."
        )
        self._empty_hint.setAlignment(Qt.AlignCenter)
        self._empty_hint.setWordWrap(True)
        self._empty_hint.setStyleSheet(f"color: {self._t['text_muted']};")
        title = self._empty_title
        hint  = self._empty_hint
        el.addWidget(title)
        el.addSpacing(8)
        el.addWidget(hint)
        el.addStretch()
        self._workspace_stack.addWidget(empty)

        # page 1 — MDI canvas
        self._mdi = QMdiArea()
        self._mdi.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._mdi.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._mdi.setBackground(QBrush(QColor(self._t['bg_surface'])))
        self._mdi.subWindowActivated.connect(self._on_mdi_activated)
        self._workspace_stack.addWidget(self._mdi)

        return page

    def _build_add_device(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._browser = ServerBrowserDialog(theme_name=self._theme_name, parent=page)
        self._browser.device_requested.connect(self._on_device_requested)
        layout.addWidget(self._browser)

        return page

    def _open_experiment_runner(self) -> None:
        # Singleton: if one is already open, just bring it forward.
        for sub in self._mdi.subWindowList():
            if sub.property("is_experiment_runner"):
                self._mdi.setActiveSubWindow(sub)
                self._workspace_stack.setCurrentIndex(1)
                self._main_tabs.setCurrentIndex(0)
                return

        panel = ExperimentPanel(self._t)
        sub = QMdiSubWindow()
        sub.setWidget(panel)
        sub.setWindowTitle("Experiment Runner")
        sub.setProperty("is_experiment_runner", True)
        sub.setAttribute(Qt.WA_DeleteOnClose)
        sub.setAttribute(Qt.WA_OpaquePaintEvent)
        w, h = ExperimentPanel.preferred_mdi_size
        sub.resize(w, h)
        self._mdi.addSubWindow(sub)
        sub.show()

        self._workspace_stack.setCurrentIndex(1)
        self._main_tabs.setCurrentIndex(0)

    def _on_device_requested(self, server: DiscoveredServer) -> None:
        for sub in self._mdi.subWindowList():
            if sub.property("server_uuid") == server.uuid:
                self._mdi.setActiveSubWindow(sub)
                self._main_tabs.setCurrentIndex(0)
                return

        panel = self._make_device_panel(server)

        sub = QMdiSubWindow()
        sub.setWidget(panel)
        sub.setWindowTitle(server.name)
        sub.setProperty("server_uuid", server.uuid)
        sub.setAttribute(Qt.WA_DeleteOnClose)
        w, h = getattr(panel, "preferred_mdi_size", (720, 520))
        sub.resize(w, h)
        self._mdi.addSubWindow(sub)
        sub.setAttribute(Qt.WA_OpaquePaintEvent)
        sub.destroyed.connect(partial(self._on_subwindow_closed, server.uuid))
        sub.show()

        self._browser.set_device_connected(server.uuid, True)
        self._workspace_stack.setCurrentIndex(1)
        self._main_tabs.setCurrentIndex(0)

    def _make_device_panel(self, server: DiscoveredServer) -> QWidget:
        return panel_for(server, self._t)

    def _on_subwindow_closed(self, uuid: str) -> None:
        self._browser.set_device_connected(uuid, False)
        if not self._mdi.subWindowList():
            self._workspace_stack.setCurrentIndex(0)

    def _on_mdi_activated(self, sub: QMdiSubWindow | None) -> None:
        if sub is None and not self._mdi.subWindowList():
            self._workspace_stack.setCurrentIndex(0)
