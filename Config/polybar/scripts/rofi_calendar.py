#!/usr/bin/env python3
"""Compact GTK calendar popup matching the dark card used by GNOME."""

import datetime as dt
import fcntl
import os
from pathlib import Path
import signal
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from popup_behavior import install_click_outside


MONTHS = (
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)
WEEKDAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/runtime-{os.getuid()}"))
LOCK_FILE = RUNTIME_DIR / "linux-personalization-calendar.lock"
BAR_WINDOW_NAME = "^polybar-primary_"

CSS = b"""
#calendar-window {
  background-color: #171922;
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 14px;
  color: #d7dae5;
  font-family: "Noto Sans";
  font-size: 10pt;
}
#calendar-card { padding: 13px 14px 14px; }
#month-title { color: #f1f2f7; font-size: 11pt; font-weight: 700; }
.nav-button {
  background: transparent; border: none; box-shadow: none;
  color: #a1a6b5; min-width: 30px; min-height: 28px; padding: 0;
  font-size: 13pt;
}
.nav-button:hover { background: #242735; color: #ffffff; border-radius: 14px; }
.weekday { color: #9297a6; font-size: 8.5pt; font-weight: 600; }
.day-button {
  background: transparent; border: none; box-shadow: none;
  color: #d8dae3; font-size: 9.5pt; font-weight: 500;
  min-width: 36px; min-height: 34px; padding: 0;
}
.day-button:hover { background: #242735; color: #ffffff; border-radius: 17px; }
.outside { color: #666b7b; }
.today { background: #3a3f54; color: #ffffff; border-radius: 17px; font-weight: 700; }
"""


class CalendarPopup(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.today = dt.date.today()
        self.year, self.month = self.today.year, self.today.month
        self.set_title("Calendario BSPWM")
        self.set_name("calendar-window")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(True)
        self.set_focus_on_map(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        self.card.set_name("calendar-card")
        self.add(self.card)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.previous_button = self._nav_button("‹", -1)
        self.next_button = self._nav_button("›", 1)
        self.title = Gtk.Label()
        self.title.set_name("month-title")
        self.title.set_hexpand(True)
        header.pack_start(self.previous_button, False, False, 0)
        header.pack_start(self.title, True, True, 0)
        header.pack_end(self.next_button, False, False, 0)
        self.card.pack_start(header, False, False, 0)

        weekdays = Gtk.Grid(column_homogeneous=True, column_spacing=2)
        for column, name in enumerate(WEEKDAYS):
            label = Gtk.Label(label=name)
            label.get_style_context().add_class("weekday")
            weekdays.attach(label, column, 0, 1, 1)
        self.card.pack_start(weekdays, False, False, 0)

        self.days = Gtk.Grid(row_homogeneous=True, column_homogeneous=True,
                             row_spacing=1, column_spacing=2)
        self.card.pack_start(self.days, False, False, 0)
        self.connect("key-press-event", self._on_key)
        install_click_outside(self)
        self.connect("delete-event", lambda *_args: Gtk.main_quit())
        self.render_month()

    def _nav_button(self, label: str, delta: int) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.get_style_context().add_class("nav-button")
        button.connect("clicked", lambda *_args: self.change_month(delta))
        return button

    def change_month(self, delta: int) -> None:
        value = self.year * 12 + self.month - 1 + delta
        self.year, remainder = divmod(value, 12)
        self.month = remainder + 1
        self.render_month()

    def render_month(self) -> None:
        self.title.set_text(f"{MONTHS[self.month]} {self.year}")
        for child in self.days.get_children():
            self.days.remove(child)
        first = dt.date(self.year, self.month, 1)
        start = first - dt.timedelta(days=first.weekday())
        for index in range(42):
            date = start + dt.timedelta(days=index)
            button = Gtk.Button(label=str(date.day))
            button.set_relief(Gtk.ReliefStyle.NONE)
            context = button.get_style_context()
            context.add_class("day-button")
            if date.month != self.month:
                context.add_class("outside")
            if date == self.today:
                context.add_class("today")
            button.connect("clicked", self._day_clicked, date)
            self.days.attach(button, index % 7, index // 7, 1, 1)
        self.days.show_all()

    def _day_clicked(self, _button: Gtk.Button, date: dt.date) -> None:
        if date.month != self.month:
            self.year, self.month = date.year, date.month
            self.render_month()
        elif date == self.today:
            Gtk.main_quit()

    def _on_key(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        if event.keyval in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
            self.change_month(-1)
            return True
        if event.keyval in (Gdk.KEY_Right, Gdk.KEY_Page_Down):
            self.change_month(1)
            return True
        return False


def calendar_position(window: Gtk.Window, geometry: Gdk.Rectangle) -> tuple[int, int]:
    """Center the popup below the Polybar date window."""
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)
    popup_width, popup_height = window.get_size()

    try:
        window_ids = subprocess.check_output(
            ["xdotool", "search", "--name", BAR_WINDOW_NAME],
            text=True,
            stderr=subprocess.DEVNULL,
        ).splitlines()
        values: dict[str, int] = {}
        details = subprocess.check_output(
            ["xdotool", "getwindowgeometry", "--shell", window_ids[-1]],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for line in details.splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"X", "Y", "WIDTH", "HEIGHT"}:
                values[key] = int(value)
        x = values["X"] + (values["WIDTH"] - popup_width) // 2
        y = values["Y"] + values["HEIGHT"] + 8
    except (FileNotFoundError, IndexError, KeyError, ValueError, subprocess.SubprocessError):
        # Current right-side date position; used only if xdotool is unavailable.
        x = geometry.x + round(geometry.width * 0.81) - popup_width // 2
        y = geometry.y + 48

    x = max(geometry.x + 8, min(x, geometry.x + geometry.width - popup_width - 8))
    y = max(geometry.y + 8, min(y, geometry.y + geometry.height - popup_height - 8))
    return x, y


def main() -> int:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = LOCK_FILE.open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # A second click acts as a toggle and closes the existing calendar.
        lock.seek(0)
        try:
            os.kill(int(lock.read().strip()), signal.SIGTERM)
        except (ValueError, ProcessLookupError, PermissionError):
            pass
        return 0
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()))
    lock.flush()

    window = CalendarPopup()
    window.show_all()
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor()
    geometry = monitor.get_geometry()
    window.move(*calendar_position(window, geometry))
    window.present()
    Gtk.main()
    window.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
