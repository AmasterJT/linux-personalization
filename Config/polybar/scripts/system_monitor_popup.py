#!/usr/bin/env python3
"""Compact live system monitor opened from the Polybar stats group."""

from collections import deque
import fcntl
import os
from pathlib import Path
import shutil
import signal
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from popup_behavior import install_click_outside


RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/runtime-{os.getuid()}"))
LOCK_FILE = RUNTIME_DIR / "linux-personalization-system-monitor.lock"

CSS = b"""
#monitor-window { background: #171922; color: #f1f2f7; border: 1px solid rgba(255,255,255,.09);
  border-radius: 15px; font-family: "Noto Sans"; font-size: 10pt; }
#monitor-card { padding: 16px; }
#title { font-size: 14pt; font-weight: 700; }
#subtitle { color: #9298a8; font-size: 9pt; }
.metric-card { background: #22252e; border: 1px solid rgba(255,255,255,.08);
  border-radius: 13px; padding: 12px; }
.metric-title { font-size: 11pt; font-weight: 700; }
.metric-value { font-size: 11pt; font-weight: 700; }
.metric-icon { font: 17pt "Hack Nerd Font"; }
.cpu { color: #45c392; } .ram { color: #a879e8; } .swap { color: #e6b922; }
.root { color: #4da3e6; } .home { color: #f16e44; }
"""


def memory_info() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.strip().split()[0]) * 1024
    except (OSError, ValueError):
        pass
    return values


def human(value: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit in {"GiB", "TiB"} else f"{value:.0f} {unit}"
        value /= 1024
    return "0 B"


def temperature() -> str:
    candidates = list(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
    for path in candidates:
        try:
            value = float(path.read_text().strip()) / 1000
            if 10 <= value <= 110:
                return f"{value:.0f}°C"
        except (OSError, ValueError):
            continue
    return ""


class Sparkline(Gtk.DrawingArea):
    COLORS = {
        "cpu": (0.27, 0.76, 0.57), "ram": (0.66, 0.47, 0.91),
        "swap": (0.90, 0.73, 0.13), "root": (0.30, 0.64, 0.90),
        "home": (0.95, 0.43, 0.27),
    }

    def __init__(self, kind: str) -> None:
        super().__init__()
        self.values = deque([0.0] * 42, maxlen=42)
        self.color = self.COLORS[kind]
        self.set_size_request(180, 52)
        self.connect("draw", self._draw)

    def push(self, value: float) -> None:
        self.values.append(max(0.0, min(100.0, value)))
        self.queue_draw()

    def _draw(self, _widget, context) -> bool:
        width, height = self.get_allocated_width(), self.get_allocated_height()
        context.set_source_rgba(*self.color, 0.20)
        context.set_line_width(1)
        context.move_to(0, height - 1)
        context.line_to(width, height - 1)
        context.stroke()
        points = list(self.values)
        if len(points) < 2:
            return False
        context.set_source_rgb(*self.color)
        context.set_line_width(2)
        for index, value in enumerate(points):
            x = index * width / (len(points) - 1)
            y = height - 3 - value / 100 * (height - 7)
            context.move_to(x, y) if index == 0 else context.line_to(x, y)
        context.stroke()
        return False


class MetricCard(Gtk.Box):
    def __init__(self, title: str, icon: str, kind: str) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.get_style_context().add_class("metric-card")
        icon_label = Gtk.Label(label=icon)
        icon_label.set_size_request(32, -1)
        icon_label.get_style_context().add_class("metric-icon")
        icon_label.get_style_context().add_class(kind)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name = Gtk.Label(label=title, xalign=0)
        name.get_style_context().add_class("metric-title")
        self.detail = Gtk.Label(xalign=0)
        self.detail.set_name("subtitle")
        labels.pack_start(name, False, False, 0)
        labels.pack_start(self.detail, False, False, 0)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.value = Gtk.Label(xalign=1)
        self.value.get_style_context().add_class("metric-value")
        self.value.get_style_context().add_class(kind)
        self.graph = Sparkline(kind)
        right.pack_start(self.value, False, False, 0)
        right.pack_start(self.graph, False, False, 0)
        self.pack_start(icon_label, False, False, 0)
        self.pack_start(labels, True, True, 0)
        self.pack_end(right, False, False, 0)

    def update(self, percent: float, detail: str, suffix: str = "") -> None:
        self.value.set_text(f"{suffix}  {percent:.0f}%".strip())
        self.detail.set_text(detail)
        self.graph.push(percent)


class MonitorWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_wmclass("bspwm-system-monitor", "BspwmSystemMonitor")
        self.set_title("Monitor del sistema")
        self.set_name("monitor-window")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_size_request(540, -1)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.set_name("monitor-card")
        self.add(card)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title = Gtk.Label(label="Monitor del sistema", xalign=0)
        title.set_name("title")
        self.updated = Gtk.Label(xalign=1)
        self.updated.set_name("subtitle")
        header.pack_start(title, True, True, 0)
        header.pack_end(self.updated, False, False, 0)
        card.pack_start(header, False, False, 0)
        self.cards = {
            "cpu": MetricCard("CPU", "󰍛", "cpu"),
            "ram": MetricCard("Memoria", "", "ram"),
            "swap": MetricCard("Swap", "󰋊", "swap"),
            "root": MetricCard("Disco raíz", "󰋊", "root"),
            "home": MetricCard("Disco de usuario", "󰉋", "home"),
        }
        for item in self.cards.values():
            card.pack_start(item, False, False, 0)
        self.previous_cpu: tuple[int, int] | None = None
        install_click_outside(self)
        self.connect("key-press-event", self._key)
        self.connect("delete-event", lambda *_args: Gtk.main_quit())
        self._refresh()
        GLib.timeout_add_seconds(1, self._refresh)

    @staticmethod
    def _cpu_values() -> tuple[int, int]:
        fields = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
        values = [int(value) for value in fields]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return sum(values), idle

    def _refresh(self) -> bool:
        try:
            current = self._cpu_values()
            if self.previous_cpu:
                total = max(1, current[0] - self.previous_cpu[0])
                cpu = 100 * (total - (current[1] - self.previous_cpu[1])) / total
            else:
                cpu = 0
            self.previous_cpu = current
        except (OSError, ValueError, IndexError):
            cpu = 0
        self.cards["cpu"].update(cpu, f"{os.cpu_count() or 1} procesadores", temperature())
        info = memory_info()
        total = info.get("MemTotal", 1)
        available = info.get("MemAvailable", 0)
        used = max(0, total - available)
        self.cards["ram"].update(100 * used / total, f"{human(used)} / {human(total)}")
        swap_total = info.get("SwapTotal", 0)
        swap_used = max(0, swap_total - info.get("SwapFree", 0))
        swap_pct = 100 * swap_used / swap_total if swap_total else 0
        self.cards["swap"].update(swap_pct, f"{human(swap_used)} / {human(swap_total)}")
        for key, path in (("root", Path("/")), ("home", Path.home())):
            usage = shutil.disk_usage(path)
            pct = 100 * usage.used / usage.total if usage.total else 0
            self.cards[key].update(pct, f"{human(usage.used)} / {human(usage.total)}")
        self.updated.set_text(time.strftime("%H:%M:%S"))
        return True

    @staticmethod
    def _key(_widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        return False


def acquire_lock():
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
        return None
    lock.seek(0); lock.truncate(); lock.write(str(os.getpid())); lock.flush()
    return lock


def main() -> int:
    lock = acquire_lock()
    if lock is None:
        return 0
    window = MonitorWindow()
    window.show_all()
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor()
    geometry = monitor.get_geometry()
    width, _height = window.get_size()
    window.move(geometry.x + int(geometry.width * 0.60), geometry.y + 48)
    window.present()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
