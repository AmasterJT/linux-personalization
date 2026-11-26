#!/usr/bin/env python3
"""Compact brightness slider anchored below the Polybar controls."""

import fcntl
import os
from pathlib import Path
import signal
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from brightness_control import backend, get_value, set_value
from popup_behavior import install_click_outside, popup_size, present_at


RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/runtime-{os.getuid()}"))
LOCK_FILE = RUNTIME_DIR / "linux-personalization-brightness.lock"

CSS = b"""
#brightness-window { background: #171922; border: 1px solid rgba(255,255,255,0.08);
  border-radius: 14px; color: #e5e7ef; font-family: "Noto Sans"; font-size: 10pt; }
#card { padding: 16px; } #title { color: #f1f2f7; font-size: 12pt; font-weight: 700; }
#subtitle { color: #a1a6b5; font-size: 9pt; } #value { font-size: 11pt; font-weight: 700; }
#icon { color: #f6cf59; font: 19pt "Hack Nerd Font"; }
scale trough { min-height: 6px; border-radius: 3px; background: #343846; }
scale highlight { min-height: 6px; border-radius: 3px; background: #f6cf59; }
scale slider { min-width: 18px; min-height: 18px; margin: -7px;
  border-radius: 9px; background: #f4f4f4; border: none; }
"""


class BrightnessPopup(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.timer: int | None = None
        self.set_title("Brillo BSPWM")
        self.set_name("brightness-window")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_size_request(380, -1)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.set_name("card")
        self.add(card)
        title = Gtk.Label(label="Brillo de pantalla", xalign=0)
        title.set_name("title")
        card.pack_start(title, False, False, 0)
        subtitle_text = "Control de hardware" if backend() == "hardware" else "Control visual XRandR"
        subtitle = Gtk.Label(label=subtitle_text, xalign=0)
        subtitle.set_name("subtitle")
        card.pack_start(subtitle, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon = Gtk.Label(label="󰃠")
        icon.set_name("icon")
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 100, 1)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.set_value(get_value())
        self.scale.connect("value-changed", self._changed)
        self.value = Gtk.Label(label=f"{round(self.scale.get_value())}%")
        self.value.set_name("value")
        row.pack_start(icon, False, False, 0)
        row.pack_start(self.scale, True, True, 0)
        row.pack_end(self.value, False, False, 0)
        card.pack_start(row, False, False, 0)
        self.connect("key-press-event", self._key)
        install_click_outside(self)
        self.connect("delete-event", lambda *_args: Gtk.main_quit())

    def _changed(self, scale: Gtk.Scale) -> None:
        self.value.set_text(f"{round(scale.get_value())}%")
        if self.timer is not None:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add(60, self._apply)

    def _apply(self) -> bool:
        self.timer = None
        set_value(round(self.scale.get_value()))
        return False

    def _key(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        return False


def position(window: Gtk.Window, monitor: Gdk.Rectangle) -> tuple[int, int]:
    width, height = popup_size(window)
    try:
        ids = subprocess.check_output(
            ["xdotool", "search", "--name", "^polybar-systemConfig_"], text=True,
            stderr=subprocess.DEVNULL,
        ).splitlines()
        data = subprocess.check_output(
            ["xdotool", "getwindowgeometry", "--shell", ids[-1]], text=True,
            stderr=subprocess.DEVNULL,
        )
        values = dict(line.split("=", 1) for line in data.splitlines() if "=" in line)
        x = int(values["X"]) + int(values["WIDTH"]) - width
        y = int(values["Y"]) + int(values["HEIGHT"]) + 8
    except (FileNotFoundError, IndexError, KeyError, ValueError, subprocess.SubprocessError):
        x, y = monitor.x + monitor.width - width - 65, monitor.y + 48
    return max(monitor.x + 8, x), min(y, monitor.y + monitor.height - height - 8)


def main() -> int:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = LOCK_FILE.open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.seek(0)
        try:
            os.kill(int(lock.read().strip()), signal.SIGTERM)
        except (ValueError, ProcessLookupError, PermissionError):
            pass
        return 0
    lock.seek(0); lock.truncate(); lock.write(str(os.getpid())); lock.flush()
    window = BrightnessPopup()
    display = Gdk.Display.get_default()
    present_at(window, *position(window, display.get_primary_monitor().get_geometry()))
    Gtk.main()
    if window.timer is not None:
        GLib.source_remove(window.timer)
        window._apply()
    window.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
