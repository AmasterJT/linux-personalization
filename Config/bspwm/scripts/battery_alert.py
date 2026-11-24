#!/usr/bin/env python3
"""Persistent, acknowledge-only low battery alerts for the BSPWM session."""

import fcntl
import os
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402


RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/runtime-{os.getuid()}"))
LOCK_FILE = RUNTIME_DIR / "linux-personalization-battery-alert.lock"
THRESHOLDS = (20, 10, 5)
BATTERY = next(iter(Path("/sys/class/power_supply").glob("BAT*")), None)

CSS = b"""
#alert { background: #171922; color: #f4f4f6; border-radius: 15px;
  border: 2px solid #e6b922; font-family: "Noto Sans"; }
#alert.warning { border-color: #e6b922; } #alert.urgent { border-color: #f08a24; }
#alert.critical { border-color: #ef4444; }
#card { padding: 24px; } #icon { font: 34pt "Hack Nerd Font"; }
#title { font-size: 16pt; font-weight: 700; } #detail { color: #b5bac8; font-size: 10pt; }
button { background: #f16e44; color: white; border: none; border-radius: 9px; padding: 9px 24px; }
"""


class Alert(Gtk.Window):
    def __init__(self, level: int, threshold: int) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_wmclass("bspwm-battery-alert", "BspwmBatteryAlert")
        self.set_title("Batería baja")
        self.set_name("alert")
        self.get_style_context().add_class("critical" if threshold <= 5 else "urgent" if threshold <= 10 else "warning")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_size_request(430, -1)
        provider = Gtk.CssProvider(); provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); card.set_name("card")
        icon = Gtk.Label(label="󰂃" if threshold <= 5 else "󰁺"); icon.set_name("icon")
        title = Gtk.Label(label=f"Batería al {level}%"); title.set_name("title")
        detail = Gtk.Label(label="Conecta el cargador para evitar que el equipo se apague.")
        detail.set_name("detail"); detail.set_line_wrap(True)
        close = Gtk.Button(label="Entendido"); close.connect("clicked", lambda *_: self.destroy())
        card.pack_start(icon, False, False, 0); card.pack_start(title, False, False, 0)
        card.pack_start(detail, False, False, 0); card.pack_start(close, False, False, 4)
        self.add(card)


class Watcher:
    def __init__(self) -> None:
        self.shown: set[int] = set()
        self.windows: list[Alert] = []
        GLib.timeout_add_seconds(8, self.check)
        self.check()

    def check(self) -> bool:
        if BATTERY is None:
            return True
        try:
            level = int((BATTERY / "capacity").read_text().strip())
            status = (BATTERY / "status").read_text().strip().casefold()
        except (OSError, ValueError):
            return True
        if status in {"charging", "full", "not charging"}:
            self.shown.clear()
            return True
        for threshold in THRESHOLDS:
            if level <= threshold and threshold not in self.shown:
                self.shown.add(threshold)
                window = Alert(level, threshold)
                window.connect("destroy", lambda item, win=window: self.windows.remove(win) if win in self.windows else None)
                self.windows.append(window)
                window.show_all(); window.present()
        return True


def main() -> int:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = LOCK_FILE.open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    Watcher()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
