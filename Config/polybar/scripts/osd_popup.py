#!/usr/bin/env python3
"""Transient volume/brightness OSD used by BSPWM multimedia keys."""

from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import sys
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from audio_control import (
    DEFAULT_MAXIMUM, change_volume, sink_icon, source_icon, toggle_mute, volume_state,
)
from brightness_control import get_value as get_brightness
from brightness_control import set_value as set_brightness
from volume_scroll import VolumeScroll


RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/runtime-{os.getuid()}"))
LOCK_FILE = RUNTIME_DIR / "linux-personalization-osd.lock"
ACTION_LOCK_FILE = RUNTIME_DIR / "linux-personalization-osd-action.lock"
STATE_FILE = RUNTIME_DIR / "linux-personalization-osd.json"
VISIBLE_SECONDS = 1.8

CSS = b"""
#osd-window { background: rgba(23,25,34,0.96); border: 1px solid rgba(255,255,255,0.10);
  border-radius: 15px; color: #f1f2f7; font-family: "Noto Sans"; }
#osd-window.volume { background: #25262b; border-radius: 26px; }
#osd-card { padding: 12px 16px; }
#osd-icon { background: transparent; border: none; box-shadow: none; color: #f16e44;
  font: 18pt "Hack Nerd Font"; min-width: 50px; padding: 0 6px; }
#osd-icon:hover { color: #ff8a63; background: rgba(255,255,255,0.07); border-radius: 20px; }
#osd-window.volume #osd-icon { color: #f4f4f4; }
#osd-icon.muted { color: #757575; }
#osd-window.volume #osd-icon.muted { color: #898b91; }
#volume-meter trough, #volume-meter progress { min-width: 1px; min-height: 6px; border: none; }
#volume-meter trough { background: #41434a; }
#volume-meter progress { background: #f4f4f4; }
#volume-meter .normal trough, #volume-meter .normal progress { border-radius: 3px 0 0 3px; }
#volume-meter .boost trough, #volume-meter .boost progress { border-radius: 0 3px 3px 0; }
#volume-meter .boost progress { background: #e8404f; }
#volume-meter.muted progress { background: #898b91; }
#volume-divider { background: #a6a8af; min-width: 2px; min-height: 8px; }
#osd-value { color: #c3c7d4; font-size: 9pt; font-weight: 700; min-width: 44px; }
scale trough { min-height: 7px; border-radius: 4px; background: #343846; }
scale highlight { min-height: 7px; border-radius: 4px; background: #f16e44; }
scale.muted highlight { background: #757575; }
scale slider { min-width: 16px; min-height: 16px; margin: -6px;
  border-radius: 8px; border: none; background: #f4f4f4; }
"""


def write_state(state: dict[str, object]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, STATE_FILE)


def perform_action(arguments: list[str]) -> dict[str, object]:
    if len(arguments) < 2:
        raise ValueError("Uso: osd_popup.py volume change N|mute | brightness change N | microphone mute")

    section, action = arguments[0], arguments[1]
    if section == "volume":
        if action == "change" and len(arguments) == 3:
            change_volume("@DEFAULT_AUDIO_SINK@", int(arguments[2]), DEFAULT_MAXIMUM)
            value, muted = volume_state("@DEFAULT_AUDIO_SINK@", DEFAULT_MAXIMUM)
        elif action == "mute":
            value, muted = toggle_mute("@DEFAULT_AUDIO_SINK@")
        else:
            raise ValueError("Acción de volumen desconocida")
        return {
            "title": "Volumen silenciado" if muted else "Volumen",
            "icon": sink_icon(value, muted),
            "value": value,
            "maximum": DEFAULT_MAXIMUM,
            "muted": muted,
            "section": "volume",
        }

    if section == "microphone" and action == "mute":
        value, muted = toggle_mute("@DEFAULT_AUDIO_SOURCE@", 100)
        return {
            "title": "Micrófono silenciado" if muted else "Micrófono activo",
            "icon": source_icon(muted),
            "value": value,
            "maximum": 100,
            "muted": muted,
            "section": "microphone",
        }

    if section == "brightness" and action == "change" and len(arguments) == 3:
        requested = max(5, min(100, get_brightness() + int(arguments[2])))
        set_brightness(requested)
        value = get_brightness()
        return {
            "title": "Brillo de pantalla",
            "icon": "󰃠",
            "value": value,
            "maximum": 100,
            "muted": False,
            "section": "brightness",
        }

    raise ValueError("Acción OSD desconocida")


def update_state(arguments: list[str]) -> None:
    # Each key press reads and updates the current level. Serialize these
    # operations so overlapping key repeats cannot overwrite one another.
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ACTION_LOCK_FILE.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        write_state(perform_action(arguments))


class VolumeMeter(Gtk.Grid):
    ANIMATION_US = 120_000

    def __init__(self) -> None:
        super().__init__(column_homogeneous=True, valign=Gtk.Align.CENTER)
        self.set_name("volume-meter")
        self.get_accessible().set_name("Volumen")
        self.normal = Gtk.ProgressBar()
        self.normal.get_style_context().add_class("normal")
        self.boost = Gtk.ProgressBar()
        self.boost.get_style_context().add_class("boost")
        divider = Gtk.Box(valign=Gtk.Align.CENTER)
        divider.set_name("volume-divider")
        boost_segment = Gtk.Box()
        boost_segment.pack_start(divider, False, False, 0)
        boost_segment.pack_start(self.boost, True, True, 0)
        self.attach(self.normal, 0, 0, 2, 1)
        self.attach(boost_segment, 2, 0, 1, 1)
        self.displayed = self.target = self.start = 0.0
        self.start_us = 0
        self.tick_id = 0

    def set_level(self, value: int, *, immediate: bool = False) -> None:
        if immediate:
            if self.tick_id:
                self.remove_tick_callback(self.tick_id)
                self.tick_id = 0
            self.target = value
            self._paint(value)
        elif value != self.target:
            self.start = self.displayed
            self.target = value
            self.start_us = GLib.get_monotonic_time()
            if not self.tick_id:
                self.tick_id = self.add_tick_callback(self._animate)

    def _animate(self, _widget, clock: Gdk.FrameClock) -> bool:
        progress = max(0.0, min(1.0, (clock.get_frame_time() - self.start_us) / self.ANIMATION_US))
        eased = 1 - (1 - progress) ** 2
        self._paint(self.start + (self.target - self.start) * eased)
        if progress >= 1:
            self.tick_id = 0
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _paint(self, value: float) -> None:
        self.displayed = value
        self.normal.set_fraction(min(value, 100) / 100)
        self.boost.set_fraction(max(0.0, value - 100) / (DEFAULT_MAXIMUM - 100))


class OSDWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.last_mtime = 0
        self.deadline = time.monotonic() + VISIBLE_SECONDS
        self.pointer_inside = False
        self.section = ""
        self.muted = False
        self.audio_read_pending = False
        self.last_audio_read = 0.0
        self.actions = ThreadPoolExecutor(max_workers=1)
        self.scroll_write = None
        self.set_title("Controles BSPWM")
        self.set_name("osd-window")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_size_request(390, -1)
        self.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        scroll = VolumeScroll(self._change_from_scroll)
        self.connect("scroll-event", lambda widget, event: (
            self.section == "volume" and scroll(widget, event)
        ))

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        card.set_name("osd-card")
        card.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        card.connect("enter-notify-event", self._pointer_enter)
        card.connect("leave-notify-event", self._pointer_leave)
        self.add(card)
        self.icon = Gtk.EventBox()
        self.icon.set_name("osd-icon")
        self.icon_label = Gtk.Label()
        self.icon_label.set_size_request(48, -1)
        self.icon_label.set_xalign(0.5)
        self.icon.add(self.icon_label)
        self.icon.connect("button-release-event", self._toggle_from_icon)
        self.value_label = Gtk.Label(xalign=1)
        self.value_label.set_name("osd-value")
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.scale.set_draw_value(False)
        self.scale.set_can_focus(False)
        self.scale.set_hexpand(True)
        self.meter = VolumeMeter()
        levels = Gtk.Stack()
        levels.add_named(self.scale, "scale")
        levels.add_named(self.meter, "volume")
        levels.show_all()
        self.levels = levels
        card.pack_start(self.icon, False, False, 0)
        card.pack_start(levels, True, True, 0)
        card.pack_start(self.value_label, False, False, 0)

        self._read_state()
        GLib.timeout_add(25, self._poll)

    def _read_state(self) -> None:
        try:
            stat = STATE_FILE.stat()
            if stat.st_mtime_ns == self.last_mtime:
                return
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return
        self.last_mtime = stat.st_mtime_ns
        value = int(state.get("value", 0))
        maximum = max(1, int(state.get("maximum", 100)))
        section = str(state.get("section", ""))
        section_changed = section != self.section
        self.section = section
        volume = section == "volume"
        context = self.get_style_context()
        if volume:
            context.add_class("volume")
        else:
            context.remove_class("volume")
        self.levels.set_visible_child_name("volume" if volume else "scale")
        self.scale.set_range(0, maximum)
        self._display_state(value, bool(state.get("muted", False)), str(state.get("icon", "")),
                            immediate=section_changed)
        self.icon.set_sensitive(section in {"volume", "microphone"})
        self.deadline = time.monotonic() + VISIBLE_SECONDS

    def _display_state(self, value: int, muted: bool, icon: str, *, immediate: bool = False) -> None:
        self.muted = muted
        self.icon_label.set_text(icon)
        self.value_label.set_text(f"{value}%")
        for widget in (self.icon, self.scale, self.meter):
            context = widget.get_style_context()
            if self.muted:
                context.add_class("muted")
            else:
                context.remove_class("muted")
        if self.section == "volume":
            self.meter.set_level(value, immediate=immediate)
        else:
            self.scale.set_value(value)

    def _pointer_enter(self, *_args) -> bool:
        self.pointer_inside = True
        return False

    def _pointer_leave(self, *_args) -> bool:
        self.pointer_inside = False
        self.deadline = time.monotonic() + VISIBLE_SECONDS
        return False

    def _toggle_from_icon(self, _widget, _event) -> bool:
        if self.section not in {"volume", "microphone"}:
            return False
        self.actions.submit(update_state, [self.section, "mute"])
        return True

    def _change_from_scroll(self, delta: int) -> None:
        self.deadline = time.monotonic() + VISIBLE_SECONDS
        if self.scroll_write is None or self.scroll_write.done():
            self.scroll_write = self.actions.submit(update_state, ["volume", "change", str(delta)])

    def _read_audio(self, section: str, revision: int) -> None:
        target = "@DEFAULT_AUDIO_SINK@" if section == "volume" else "@DEFAULT_AUDIO_SOURCE@"
        maximum = DEFAULT_MAXIMUM if section == "volume" else 100
        value, muted = volume_state(target, maximum)
        GLib.idle_add(self._apply_audio, section, revision, value, muted)

    def _apply_audio(self, section: str, revision: int, value: int, muted: bool) -> bool:
        self.audio_read_pending = False
        self._read_state()
        if self.section == section and self.last_mtime == revision:
            icon = sink_icon(value, muted) if section == "volume" else source_icon(muted)
            self._display_state(value, muted, icon)
        return GLib.SOURCE_REMOVE

    def _poll(self) -> bool:
        self._read_state()
        now = time.monotonic()
        if (self.section in {"volume", "microphone"} and not self.audio_read_pending
                and now - self.last_audio_read >= 0.2):
            self.last_audio_read = now
            self.audio_read_pending = True
            threading.Thread(target=self._read_audio, args=(self.section, self.last_mtime),
                             daemon=True).start()
        try:
            pointer = Gdk.Display.get_default().get_default_seat().get_pointer()
            _screen, pointer_x, pointer_y = pointer.get_position()
            window_x, window_y = self.get_position()
            width, height = self.get_size()
            hovering = (
                window_x <= pointer_x < window_x + width
                and window_y <= pointer_y < window_y + height
            )
            if self.pointer_inside and not hovering:
                self.deadline = time.monotonic() + VISIBLE_SECONDS
            self.pointer_inside = hovering
        except (AttributeError, TypeError):
            pass
        if not self.pointer_inside and time.monotonic() >= self.deadline:
            Gtk.main_quit()
            return False
        return True


def position(window: Gtk.Window) -> None:
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor()
    geometry = monitor.get_geometry()
    width, height = window.get_size()
    x = geometry.x + (geometry.width - width) // 2
    y = geometry.y + geometry.height - height - 95
    window.move(x, y)


def main() -> int:
    try:
        update_state(sys.argv[1:])
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    lock = LOCK_FILE.open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()))
    lock.flush()

    window = OSDWindow()
    window.show_all()
    position(window)
    window.present()
    Gtk.main()
    window.destroy()
    window.actions.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
