#!/usr/bin/env python3
"""PipeWire audio panel for outputs, microphones and application streams."""

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
import fcntl
import os
import re
import shutil
import signal
import subprocess
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from audio_control import run_wpctl, set_volume_percent, sink_icon, source_icon, volume_state
from popup_behavior import install_click_outside, popup_size, present_at
from volume_scroll import VolumeScroll


RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/runtime-{os.getuid()}"))
LOCK_FILE = RUNTIME_DIR / "linux-personalization-volume.lock"
NODE_PATTERN = re.compile(r"^[\s│├└─]*(\*)?\s*(\d+)\.\s+(.*?)\s+\[vol:")
STREAM_PATTERN = re.compile(r"^ {8}(\d+)\.\s+(.+?)\s*$")
OUTPUT_MAXIMUM = 150
INPUT_MAXIMUM = 100
STREAM_MAXIMUM = 150
VOLUME_WRITE_INTERVAL_MS = 55

CSS = b"""
#volume-window { background-color: #171922; border: 1px solid rgba(255,255,255,0.07);
  border-radius: 14px; color: #e5e7ef; font-family: "Noto Sans"; font-size: 10pt; }
#volume-card { padding: 16px; } #title { color: #f1f2f7; font-size: 12pt; font-weight: 700; }
#subtitle, #status { color: #a1a6b5; font-size: 9pt; }
notebook, notebook stack, scrolledwindow, scrolledwindow viewport {
  background: #171922; border: none; box-shadow: none;
}
.section-title { color: #a1a6b5; font-size: 8.5pt; font-weight: 600; }
.value { color: #f1f2f7; font-size: 10pt; font-weight: 700; min-width: 42px; }
.device-row { background: transparent; border: none; box-shadow: none;
  border-radius: 0; padding: 7px 3px; color: #e5e7ef; }
.device-row:hover { background: transparent; color: #ffffff; }
.device-name { color: #f0f1f6; font-size: 9.5pt; font-weight: 600; }
.device-state { color: #a1a6b5; font-size: 8.5pt; }
.audio-icon { color: #aeb3c2; font: 16pt "Hack Nerd Font"; }
.audio-icon.output-icon { color: #f16e44; }
.audio-icon.muted { color: #757575; }
.audio-toggle, .audio-toggle:hover, .audio-toggle:checked {
  background: transparent; border: none; box-shadow: none; padding: 2px;
  min-width: 30px; min-height: 30px;
}
.selected { color: #43a047; }
.action-button { background: transparent; border: 1px solid rgba(255,255,255,0.12); box-shadow: none;
  border-radius: 9px; padding: 7px 10px; color: #f0f1f6; font-size: 9pt; font-weight: 600; }
.action-button:hover { background: transparent; border-color: rgba(255,255,255,0.28); }
.mute-button, .mute-button:hover { background: transparent; border: none; box-shadow: none;
  padding: 2px; color: #f16e44; }
.mute-button:checked { background: transparent; color: #757575;
  border: none; box-shadow: none; }
.stream-row { background: transparent; border-bottom: 1px solid rgba(255,255,255,0.07);
  border-radius: 0; padding: 7px 3px; }
.app-icon { min-width: 26px; min-height: 26px; }
.icon-button { min-width: 28px; min-height: 28px; padding: 2px; font: 14pt "Hack Nerd Font"; }
notebook header { background: transparent; border: none; box-shadow: none; }
notebook tab { background: transparent; color: #aeb3c2; padding: 7px 12px;
  border: none; border-bottom: 2px solid transparent; box-shadow: none; }
notebook tab:hover { background: transparent; color: #ffffff; }
notebook tab:checked { background: transparent; color: #ffffff; border-bottom-color: #f16e44; }
scale trough { min-height: 6px; border-radius: 3px; background: #343846; }
scale highlight { min-height: 6px; border-radius: 3px; background: #f16e44; }
scale.muted highlight { background: #757575; }
scale slider { min-width: 18px; min-height: 18px; margin: -7px;
  border-radius: 9px; background: #f4f4f4; border: none; }
separator { background: rgba(255,255,255,0.08); min-height: 1px; }
"""


def audio_nodes(start_marker: str, end_marker: str) -> list[dict[str, object]]:
    output = run_wpctl("status", timeout=5).stdout
    active = False
    nodes: list[dict[str, object]] = []
    for line in output.splitlines():
        if start_marker in line:
            active = True
            continue
        if active and end_marker in line:
            break
        if active:
            match = NODE_PATTERN.match(line)
            if match:
                nodes.append({
                    "default": bool(match.group(1)), "id": int(match.group(2)),
                    "description": match.group(3).strip(),
                })
    return sorted(nodes, key=lambda node: not bool(node["default"]))


def audio_sinks() -> list[dict[str, object]]:
    return audio_nodes("├─ Sinks:", "├─ Sources:")


def audio_sources() -> list[dict[str, object]]:
    return audio_nodes("├─ Sources:", "├─ Filters:")


def audio_streams() -> list[dict[str, object]]:
    output = run_wpctl("status", timeout=5).stdout
    in_audio = False
    in_streams = False
    streams: list[dict[str, object]] = []
    for line in output.splitlines():
        if line.strip() == "Audio":
            in_audio = True
            continue
        if in_audio and "Streams:" in line:
            in_streams = True
            continue
        if in_audio and in_streams and line.strip() == "Video":
            break
        if in_streams:
            match = STREAM_PATTERN.match(line)
            if match:
                node_id = int(match.group(1))
                properties = stream_properties(node_id)
                streams.append({
                    "id": node_id,
                    "description": properties.get("application.name", match.group(2).strip()),
                    "icon": properties.get("application.icon-name", ""),
                })
    return streams


def stream_properties(node_id: int) -> dict[str, str]:
    output = run_wpctl("inspect", str(node_id), timeout=4).stdout
    properties: dict[str, str] = {}
    for line in output.splitlines():
        match = re.match(r"\s*\*?\s*([\w.-]+)\s*=\s*\"(.*)\"\s*$", line)
        if match:
            properties[match.group(1)] = match.group(2)
    return properties


def volume_scale(maximum: int) -> Gtk.Scale:
    scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, maximum, 1)
    scale.set_draw_value(False)
    scale.set_hexpand(True)
    scale.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
    scale.connect("scroll-event", VolumeScroll(lambda step: scale.set_value(scale.get_value() + step)))
    return scale


class VolumePopup(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.refreshing = False
        self.timers: dict[str, int] = {}
        self.pending_volumes: dict[str, tuple[int, int]] = {}
        self.volume_writes: dict[str, Future] = {}
        self.volume_executor = ThreadPoolExecutor(max_workers=1)
        self.last_volume_edit = float("-inf")
        self.stream_count = 0
        self.set_title("Audio BSPWM")
        self.set_name("volume-window")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(True)
        self.set_focus_on_map(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_size_request(540, -1)
        self.set_default_size(540, 430)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.set_name("volume-card")
        self.add(card)
        title = Gtk.Label(label="Audio", xalign=0)
        title.set_name("title")
        self.subtitle = Gtk.Label(label="Control de PipeWire", xalign=0)
        self.subtitle.set_name("subtitle")
        self.subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        self.subtitle.set_max_width_chars(64)
        card.pack_start(title, False, False, 0)
        card.pack_start(self.subtitle, False, False, 0)

        self.notebook = Gtk.Notebook()
        (self.output_page, self.output_icon, self.output_scale, self.output_value,
         self.output_mute, self.output_box) = self._device_page(
            "󰕾", "Volumen general", "Salidas disponibles", OUTPUT_MAXIMUM, "output-icon"
        )
        (self.input_page, self.input_icon, self.input_scale, self.input_value,
         self.input_mute, self.input_box) = self._device_page(
            "", "Nivel del micrófono", "Entradas disponibles", INPUT_MAXIMUM, "input-icon"
        )
        self.app_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.app_box.set_border_width(8)
        app_scroll = Gtk.ScrolledWindow()
        app_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        app_scroll.add(self.app_box)
        self.notebook.append_page(self.output_page, Gtk.Label(label="Salida"))
        self.notebook.append_page(self.input_page, Gtk.Label(label="Micrófono"))
        self.notebook.append_page(app_scroll, Gtk.Label(label="Aplicaciones"))
        self.notebook.connect("switch-page", self._page_changed)
        card.pack_start(self.notebook, True, True, 0)

        self.output_scale.connect("value-changed", self._schedule_volume,
                                  "@DEFAULT_AUDIO_SINK@", self.output_value, OUTPUT_MAXIMUM)
        self.input_scale.connect("value-changed", self._schedule_volume,
                                 "@DEFAULT_AUDIO_SOURCE@", self.input_value, INPUT_MAXIMUM)
        self.output_mute.connect("toggled", self._mute_changed, "@DEFAULT_AUDIO_SINK@")
        self.input_mute.connect("toggled", self._mute_changed, "@DEFAULT_AUDIO_SOURCE@")

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status = Gtk.Label(xalign=0)
        self.status.set_name("status")
        settings = Gtk.Button(label="Configuración de sonido")
        settings.set_relief(Gtk.ReliefStyle.NONE)
        settings.get_style_context().add_class("action-button")
        settings.connect("clicked", self._open_settings)
        footer.pack_start(self.status, True, True, 0)
        footer.pack_end(settings, False, False, 0)
        card.pack_end(footer, False, False, 0)

        self.connect("key-press-event", self._on_key)
        install_click_outside(self)
        self.connect("delete-event", lambda *_args: Gtk.main_quit())
        self.refresh()
        GLib.timeout_add(400, self._sync_default_state)

    def _device_page(
        self, icon_text: str, level_title: str, devices_title: str,
        maximum: int, icon_class: str,
    ):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        page.set_border_width(8)
        level = Gtk.Label(label=level_title, xalign=0)
        level.get_style_context().add_class("section-title")
        page.pack_start(level, False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mute = Gtk.ToggleButton(label=icon_text)
        mute.set_relief(Gtk.ReliefStyle.NONE)
        mute.get_style_context().add_class("audio-toggle")
        mute.get_style_context().add_class("audio-icon")
        mute.get_style_context().add_class(icon_class)
        scale = volume_scale(maximum)
        value = Gtk.Label()
        value.get_style_context().add_class("value")
        row.pack_start(mute, False, False, 0)
        row.pack_start(scale, True, True, 0)
        row.pack_start(value, False, False, 0)
        page.pack_start(row, False, False, 0)
        page.pack_start(Gtk.Separator(), False, False, 0)
        label = Gtk.Label(label=devices_title, xalign=0)
        label.get_style_context().add_class("section-title")
        page.pack_start(label, False, False, 0)
        device_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(device_box)
        page.pack_start(scroll, True, True, 0)
        return page, mute, scale, value, mute, device_box

    def refresh(self) -> None:
        output_value, output_muted = volume_state("@DEFAULT_AUDIO_SINK@", OUTPUT_MAXIMUM)
        input_value, input_muted = volume_state("@DEFAULT_AUDIO_SOURCE@", INPUT_MAXIMUM)
        sinks, sources, streams = audio_sinks(), audio_sources(), audio_streams()
        self.refreshing = True
        self.output_scale.set_value(output_value)
        self.input_scale.set_value(input_value)
        self.output_mute.set_active(output_muted)
        self.input_mute.set_active(input_muted)
        self._set_mute_label(self.output_mute, "@DEFAULT_AUDIO_SINK@")
        self._set_mute_label(self.input_mute, "@DEFAULT_AUDIO_SOURCE@")
        self._set_default_visual("@DEFAULT_AUDIO_SINK@", output_value, output_muted)
        self._set_default_visual("@DEFAULT_AUDIO_SOURCE@", input_value, input_muted)
        self.refreshing = False
        self.output_value.set_text(f"{output_value}%")
        self.input_value.set_text(f"{input_value}%")
        self._fill_devices(self.output_box, sinks, "󰓄", "Salida activa", self._select_device)
        self._fill_devices(self.input_box, sources, "", "Entrada activa", self._select_device)
        self._fill_streams(streams)
        active_sink = next((item for item in sinks if item["default"]), None)
        active_source = next((item for item in sources if item["default"]), None)
        sink_name = str(active_sink["description"]) if active_sink else "sin salida"
        source_name = str(active_source["description"]) if active_source else "sin micrófono"
        self.subtitle.set_text(f"{sink_name} · {source_name}")
        self.status.set_text(f"{len(sinks)} salidas · {len(sources)} entradas · {len(streams)} aplicaciones")
        self.get_child().show_all()

    def _fill_devices(self, box: Gtk.Box, devices, icon_text: str, active_text: str, callback) -> None:
        for child in box.get_children():
            box.remove(child)
        for device in devices:
            button = Gtk.Button()
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.get_style_context().add_class("device-row")
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            icon = Gtk.Label(label=icon_text)
            icon.get_style_context().add_class("audio-icon")
            if device["default"]:
                icon.get_style_context().add_class("selected")
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            name = Gtk.Label(label=str(device["description"]), xalign=0)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            name.get_style_context().add_class("device-name")
            state = Gtk.Label(label=active_text if device["default"] else "Pulsa para seleccionar", xalign=0)
            state.get_style_context().add_class("device-state")
            labels.pack_start(name, False, False, 0)
            labels.pack_start(state, False, False, 0)
            row.pack_start(icon, False, False, 0)
            row.pack_start(labels, True, True, 0)
            if device["default"]:
                check = Gtk.Label(label="✓")
                check.get_style_context().add_class("selected")
                row.pack_end(check, False, False, 0)
            button.add(row)
            button.set_sensitive(not bool(device["default"]))
            button.connect("clicked", callback, int(device["id"]))
            box.pack_start(button, False, False, 0)

    def _fill_streams(self, streams) -> None:
        self.stream_count = len(streams)
        for child in self.app_box.get_children():
            self.app_box.remove(child)
        if not streams:
            empty = Gtk.Label(label="No hay aplicaciones reproduciendo audio", xalign=0)
            empty.set_name("status")
            self.app_box.pack_start(empty, False, False, 12)
            return
        for stream in streams:
            target = str(stream["id"])
            value, muted = volume_state(target, STREAM_MAXIMUM)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
            row.get_style_context().add_class("stream-row")
            icon = self._application_icon(stream)
            name = Gtk.Label(label=str(stream["description"]), xalign=0)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            name.set_size_request(105, -1)
            name.get_style_context().add_class("device-name")
            scale = volume_scale(STREAM_MAXIMUM)
            scale.set_value(value)
            value_label = Gtk.Label(label=f"{value}%")
            value_label.get_style_context().add_class("value")
            scale.connect("value-changed", self._schedule_volume, target, value_label, STREAM_MAXIMUM)
            mute = Gtk.ToggleButton(label="󰖁" if muted else "")
            mute.set_relief(Gtk.ReliefStyle.NONE)
            mute.set_active(muted)
            mute.get_style_context().add_class("action-button")
            mute.get_style_context().add_class("mute-button")
            mute.get_style_context().add_class("icon-button")
            mute.set_tooltip_text("Activar sonido" if muted else "Silenciar aplicación")
            mute.connect("toggled", self._stream_mute_changed, target)
            row.pack_start(icon, False, False, 0)
            row.pack_start(name, False, False, 0)
            row.pack_start(scale, True, True, 0)
            row.pack_end(mute, False, False, 0)
            row.pack_end(value_label, False, False, 0)
            self.app_box.pack_start(row, False, False, 0)

    def _page_changed(self, _notebook: Gtk.Notebook, _page: Gtk.Widget, page_number: int) -> None:
        application_height = max(220, min(430, 190 + self.stream_count * 48))
        height = (430, 340, application_height)[page_number]
        GLib.idle_add(self._resize_panel, height)

    def _resize_panel(self, height: int) -> bool:
        self.resize(540, height)
        return False

    @staticmethod
    def _application_icon(stream) -> Gtk.Image:
        description = str(stream["description"])
        candidates = [
            str(stream.get("icon", "")),
            description.casefold().replace(" ", "-"),
            {
                "brave": "brave-browser", "chromium": "chromium",
                "firefox": "firefox", "spotify": "spotify", "vlc": "vlc",
            }.get(description.casefold(), ""),
            "applications-multimedia",
        ]
        theme = Gtk.IconTheme.get_default()
        icon_name = next((item for item in candidates if item and theme.has_icon(item)), "applications-multimedia")
        image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DND)
        image.set_pixel_size(24)
        image.get_style_context().add_class("app-icon")
        return image

    def _schedule_volume(self, scale: Gtk.Scale, target: str, label: Gtk.Label, maximum: int) -> None:
        value = round(scale.get_value())
        label.set_text(f"{value}%")
        if target in {"@DEFAULT_AUDIO_SINK@", "@DEFAULT_AUDIO_SOURCE@"}:
            button = self.output_mute if target == "@DEFAULT_AUDIO_SINK@" else self.input_mute
            self._set_default_visual(target, value, button.get_active())
        if self.refreshing:
            return
        self.last_volume_edit = time.monotonic()
        self.pending_volumes[target] = (value, maximum)
        if target not in self.timers:
            self.timers[target] = GLib.timeout_add(VOLUME_WRITE_INTERVAL_MS, self._apply_volume, target)

    def _apply_volume(self, target: str) -> bool:
        previous = self.volume_writes.get(target)
        if previous is not None and not previous.done():
            return GLib.SOURCE_CONTINUE
        self.timers.pop(target, None)
        value, maximum = self.pending_volumes.pop(target)
        self.last_volume_edit = time.monotonic()
        self.volume_writes[target] = self.volume_executor.submit(set_volume_percent, target, value, maximum)
        return GLib.SOURCE_REMOVE

    def finish_volume_writes(self) -> None:
        for timer in self.timers.values():
            GLib.source_remove(timer)
        for target, (value, maximum) in self.pending_volumes.items():
            self.volume_executor.submit(set_volume_percent, target, value, maximum)
        self.volume_executor.shutdown()

    def _mute_changed(self, button: Gtk.ToggleButton, target: str) -> None:
        if self.refreshing:
            return
        run_wpctl("set-mute", target, "1" if button.get_active() else "0", timeout=5)
        self._set_mute_label(button, target)
        scale = self.output_scale if target == "@DEFAULT_AUDIO_SINK@" else self.input_scale
        self._set_default_visual(target, round(scale.get_value()), button.get_active())

    def _stream_mute_changed(self, button: Gtk.ToggleButton, target: str) -> None:
        if self.refreshing:
            return
        muted = button.get_active()
        run_wpctl("set-mute", target, "1" if muted else "0", timeout=5)
        button.set_label("󰖁" if muted else "")
        button.set_tooltip_text("Activar sonido" if muted else "Silenciar aplicación")

    @staticmethod
    def _set_mute_label(button: Gtk.ToggleButton, target: str) -> None:
        muted = button.get_active()
        button.set_label(sink_icon(100, muted) if target == "@DEFAULT_AUDIO_SINK@" else source_icon(muted))
        button.set_tooltip_text("Activar sonido" if muted else "Silenciar")

    def _set_default_visual(self, target: str, value: int, muted: bool) -> None:
        if target == "@DEFAULT_AUDIO_SINK@":
            icon, scale = self.output_icon, self.output_scale
            icon.set_label(sink_icon(value, muted))
        else:
            icon, scale = self.input_icon, self.input_scale
            icon.set_label(source_icon(muted))
        for widget in (icon, scale):
            context = widget.get_style_context()
            if muted:
                context.add_class("muted")
            else:
                context.remove_class("muted")

    def _sync_default_state(self) -> bool:
        # PipeWire may still report the previous value while a user edit is in flight.
        if (self.pending_volumes or any(not write.done() for write in self.volume_writes.values())
                or time.monotonic() - self.last_volume_edit < 0.25):
            return GLib.SOURCE_CONTINUE
        output_value, output_muted = volume_state("@DEFAULT_AUDIO_SINK@", OUTPUT_MAXIMUM)
        input_value, input_muted = volume_state("@DEFAULT_AUDIO_SOURCE@", INPUT_MAXIMUM)
        self.refreshing = True
        self.output_scale.set_value(output_value)
        self.input_scale.set_value(input_value)
        self.output_mute.set_active(output_muted)
        self.input_mute.set_active(input_muted)
        self.refreshing = False
        self.output_value.set_text(f"{output_value}%")
        self.input_value.set_text(f"{input_value}%")
        self._set_mute_label(self.output_mute, "@DEFAULT_AUDIO_SINK@")
        self._set_mute_label(self.input_mute, "@DEFAULT_AUDIO_SOURCE@")
        self._set_default_visual("@DEFAULT_AUDIO_SINK@", output_value, output_muted)
        self._set_default_visual("@DEFAULT_AUDIO_SOURCE@", input_value, input_muted)
        return True

    def _select_device(self, _button: Gtk.Button, node_id: int) -> None:
        self.status.set_text("Cambiando dispositivo…")
        def worker() -> None:
            result = run_wpctl("set-default", str(node_id), timeout=8)
            GLib.idle_add(self._device_changed, result.returncode == 0)
        threading.Thread(target=worker, daemon=True).start()

    def _device_changed(self, success: bool) -> bool:
        self.refresh()
        if not success:
            self.status.set_text("No se pudo cambiar el dispositivo")
        return False

    def _open_settings(self, _button: Gtk.Button) -> None:
        command = ["pavucontrol"] if shutil.which("pavucontrol") else ["gnome-control-center", "sound"]
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        Gtk.main_quit()

    def _on_key(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        return False


def popup_position(window: Gtk.Window, monitor: Gdk.Rectangle) -> tuple[int, int]:
    width, height = popup_size(window)
    try:
        ids = subprocess.check_output(["xdotool", "search", "--name", "^polybar-systemConfig_"],
                                      text=True, stderr=subprocess.DEVNULL).splitlines()
        details = subprocess.check_output(["xdotool", "getwindowgeometry", "--shell", ids[-1]],
                                          text=True, stderr=subprocess.DEVNULL)
        values = dict(line.split("=", 1) for line in details.splitlines() if "=" in line)
        x = int(values["X"]) + int(values["WIDTH"]) - width
        y = int(values["Y"]) + int(values["HEIGHT"]) + 8
    except (FileNotFoundError, IndexError, KeyError, ValueError, subprocess.SubprocessError):
        x, y = monitor.x + monitor.width - width - 65, monitor.y + 48
    x = max(monitor.x + 8, min(x, monitor.x + monitor.width - width - 8))
    y = max(monitor.y + 8, min(y, monitor.y + monitor.height - height - 8))
    return x, y


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
    window = VolumePopup()
    display = Gdk.Display.get_default()
    present_at(window, *popup_position(window, display.get_primary_monitor().get_geometry()))
    Gtk.main()
    window.destroy()
    window.finish_volume_writes()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
