"""PyInstaller entry script - app.py itself uses relative imports, which don't
resolve when a script is run directly as __main__, so this thin wrapper is
the Analysis target instead.

Set RXN_BENCH_UI_SELFTEST=1 to run a build-verification pass instead of
launching the GUI: constructs every discovered device plugin's widget (real
imports, real create_widget() call, no mock server needed) and exits nonzero
on the first failure. Catches exactly the class of bug static analysis can't
see - a plugin's dependency (first- or third-party) missing from the frozen
bundle - which only shows up once a plugin actually gets loaded, not just
when the app starts. Meant to be run against a real build (`make dist`),
headless (QT_QPA_PLATFORM=offscreen), before shipping.
"""
import os
import sys


def _selftest() -> int:
    from PySide6.QtWidgets import QApplication

    from rxn_bench_ui import devices as devpkg
    from rxn_bench_ui.discovery import DiscoveredServer
    from rxn_bench_ui.themes import get as get_theme

    app = QApplication(sys.argv)
    theme = get_theme("light")

    mods = devpkg.all_devices()
    print(f"discovered {len(mods)} device plugin(s) from {devpkg._DEVICES_DIR}")
    if not mods:
        print("FAIL: no device plugins discovered")
        return 1

    failures = []
    for mod in mods:
        name = mod.__name__.rsplit(".", 1)[-1]
        try:
            server = DiscoveredServer(
                name=f"selftest-{name}", host="127.0.0.1", port=1, features=mod.FEATURE_FRAGMENTS
            )
            widget = mod.create_widget(server, theme)
            widget.deleteLater()
            print(f"OK   {name}")
        except Exception as exc:
            print(f"FAIL {name}: {exc!r}")
            failures.append(name)

    if failures:
        print(f"FAIL: {len(failures)}/{len(mods)} device widget(s) failed to construct: {failures}")
        return 1
    print(f"OK: all {len(mods)} device widget(s) constructed successfully")
    return 0


def main():
    if os.environ.get("RXN_BENCH_UI_SELFTEST"):
        sys.exit(_selftest())
    from rxn_bench_ui.app import main as app_main

    app_main()


if __name__ == "__main__":
    main()
