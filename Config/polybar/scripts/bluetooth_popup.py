#!/usr/bin/env python3
"""GTK Bluetooth menu for the Polybar system controls."""

from pathlib import Path
import fcntl
import os
import re
import signal
import subprocess
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from popup_behavior import install_click_outside, present_at


RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/runtime-{os.getuid()}"))
LOCK_FILE = RUNTIME_DIR / "linux-personalization-bluetooth.lock"
DEVICE_RE = re.compile(r"^Device\s+([0-9A-F:]{17})\s+(.+)$")

CSS = b"""
#bluetooth-window {
  background-color: #171922;
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 14px;
  color: #e5e7ef;
  font-family: "Noto Sans";
  font-size: 10pt;
}
#bluetooth-card { padding: 16px; }
#title { color: #f1f2f7; font-size: 12pt; font-weight: 700; }
#subtitle { color: #a1a6b5; font-size: 9pt; }
#status { color: #a1a6b5; font-size: 9pt; }
.device-row {
  background: transparent; border: none; box-shadow: none;
  border-radius: 9px; padding: 11px 10px; color: #e5e7ef;
}
.device-row:hover { background: #282c39; }
.device-name { color: #f0f1f6; font-size: 10pt; font-weight: 600; }
.device-state { color: #a1a6b5; font-size: 8.5pt; }
.device-icon { color: #aeb3c2; font: 16pt "Hack Nerd Font"; }
.connected { color: #43a047; }
.action-button {
  background: #222632; border: none; box-shadow: none;
  border-radius: 9px; padding: 10px 12px; color: #f0f1f6;
  font-size: 9pt; font-weight: 600;
}
.action-button:hover { background: #303544; }
.primary { background: #f16e44; color: #ffffff; }
.primary:hover { background: #f8825c; }
switch { background: #343846; border-radius: 12px; }
switch:checked { background: #f16e44; }
switch slider { min-width: 18px; min-height: 18px; border-radius: 9px; }
separator { background: rgba(255,255,255,0.08); min-height: 1px; }
"""


def run_bluetooth(*arguments: str, timeout: int = 12) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["bluetoothctl", *arguments], text=True, capture_output=True,
            timeout=timeout, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(["bluetoothctl", *arguments], 1, "", str(error))


def controller_powered() -> bool:
    return "Powered: yes" in run_bluetooth("show", timeout=3).stdout


def known_devices() -> list[tuple[str, str]]:
    devices: list[tuple[str, str]] = []
    for line in run_bluetooth("devices", timeout=4).stdout.splitlines():
        match = DEVICE_RE.match(line.strip())
        if match:
            devices.append((match.group(1), match.group(2)))
    return devices


def device_info(address: str) -> dict[str, bool]:
    output = run_bluetooth("info", address, timeout=4).stdout
    return {
        "connected": "Connected: yes" in output,
        "paired": "Paired: yes" in output,
        "trusted": "Trusted: yes" in output,
    }


class BluetoothPopup(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.scanning = False
        self.scan_process: subprocess.Popen | None = None
        self.busy = False
        self.set_title("Bluetooth BSPWM")
        self.set_name("bluetooth-window")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(True)
        self.set_focus_on_map(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_size_request(420, -1)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.set_name("bluetooth-card")
        self.add(card)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title = Gtk.Label(label="Bluetooth", xalign=0)
        title.set_name("title")
        self.subtitle = Gtk.Label(xalign=0)
        self.subtitle.set_name("subtitle")
        title_box.pack_start(title, False, False, 0)
        title_box.pack_start(self.subtitle, False, False, 0)
        self.power_switch = Gtk.Switch()
        self.power_switch.set_valign(Gtk.Align.CENTER)
        self.power_switch.connect("notify::active", self._power_changed)
        header.pack_start(title_box, True, True, 0)
        header.pack_end(self.power_switch, False, False, 0)
        card.pack_start(header, False, False, 0)
        card.pack_start(Gtk.Separator(), False, False, 0)

        self.device_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(150)
        scroll.set_max_content_height(310)
        scroll.add(self.device_box)
        card.pack_start(scroll, True, True, 0)

        self.status = Gtk.Label(xalign=0)
        self.status.set_name("status")
        card.pack_start(self.status, False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.scan_button = self._action_button("Buscar dispositivos", True)
        self.scan_button.connect("clicked", self._toggle_scan)
        settings = self._action_button("Abrir configuración", False)
        settings.connect("clicked", self._open_settings)
        actions.pack_start(self.scan_button, True, True, 0)
        actions.pack_start(settings, True, True, 0)
        card.pack_start(actions, False, False, 0)

        self.connect("key-press-event", self._on_key)
        install_click_outside(self)
        self.connect("delete-event", lambda *_args: Gtk.main_quit())
        self.refresh()

    def _action_button(self, text: str, primary: bool) -> Gtk.Button:
        button = Gtk.Button(label=text)
        context = button.get_style_context()
        context.add_class("action-button")
        if primary:
            context.add_class("primary")
        return button

    def refresh(self) -> bool:
        powered = controller_powered()
        self.power_switch.handler_block_by_func(self._power_changed)
        self.power_switch.set_active(powered)
        self.power_switch.handler_unblock_by_func(self._power_changed)
        self.subtitle.set_text("Adaptador encendido" if powered else "Adaptador apagado")
        for child in self.device_box.get_children():
            self.device_box.remove(child)

        devices = known_devices() if powered else []
        connected_count = 0
        for address, name in devices:
            info = device_info(address)
            connected_count += int(info["connected"])
            self.device_box.pack_start(self._device_row(address, name, info), False, False, 0)
        if powered and not devices:
            empty = Gtk.Label(label="No se encontraron dispositivos", xalign=0)
            empty.set_name("status")
            empty.set_margin_top(18)
            empty.set_margin_bottom(18)
            self.device_box.pack_start(empty, False, False, 0)
        self.status.set_text(
            "Buscando dispositivos nuevos…" if self.scanning
            else f"{connected_count} dispositivo{'s' if connected_count != 1 else ''} conectado{'s' if connected_count != 1 else ''}"
        )
        self.scan_button.set_sensitive(powered and not self.busy)
        self.device_box.show_all()
        return self.scanning

    def _device_row(self, address: str, name: str, info: dict[str, bool]) -> Gtk.Button:
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.get_style_context().add_class("device-row")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        icon = Gtk.Label(label="")
        icon.get_style_context().add_class("device-icon")
        if info["connected"]:
            icon.get_style_context().add_class("connected")
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        name_label = Gtk.Label(label=name, xalign=0)
        name_label.set_ellipsize(3)
        name_label.get_style_context().add_class("device-name")
        if info["connected"]:
            state = "Conectado · pulsa para desconectar"
        elif info["paired"]:
            state = "Emparejado · pulsa para conectar"
        else:
            state = "Nuevo · pulsa para emparejar"
        state_label = Gtk.Label(label=state, xalign=0)
        state_label.get_style_context().add_class("device-state")
        labels.pack_start(name_label, False, False, 0)
        labels.pack_start(state_label, False, False, 0)
        row.pack_start(icon, False, False, 0)
        row.pack_start(labels, True, True, 0)
        button.add(row)
        button.connect("clicked", self._device_clicked, address, info)
        return button

    def _background(self, operation, message: str) -> None:
        if self.busy:
            return
        self.busy = True
        self.status.set_text(message)
        self.scan_button.set_sensitive(False)

        def worker() -> None:
            error = operation()
            GLib.idle_add(self._operation_finished, error)

        threading.Thread(target=worker, daemon=True).start()

    def _operation_finished(self, error: str | None) -> bool:
        self.busy = False
        self.refresh()
        if error:
            self.status.set_text(error)
        return False

    def _device_clicked(self, _button: Gtk.Button, address: str, info: dict[str, bool]) -> None:
        def operation() -> str | None:
            if info["connected"]:
                result = run_bluetooth("disconnect", address, timeout=15)
                return None if result.returncode == 0 else "No se pudo desconectar el dispositivo"
            if not info["paired"]:
                pair = run_bluetooth("pair", address, timeout=35)
                if pair.returncode != 0:
                    return "No se pudo emparejar el dispositivo"
                run_bluetooth("trust", address, timeout=8)
            result = run_bluetooth("connect", address, timeout=25)
            return None if result.returncode == 0 else "No se pudo conectar el dispositivo"

        action = "Desconectando…" if info["connected"] else "Conectando…"
        self._background(operation, action)

    def _power_changed(self, switch: Gtk.Switch, _param) -> None:
        desired = "on" if switch.get_active() else "off"

        def operation() -> str | None:
            result = run_bluetooth("power", desired, timeout=10)
            return None if result.returncode == 0 else "No se pudo cambiar el estado del adaptador"

        self._background(operation, "Actualizando adaptador…")

    def _toggle_scan(self, _button: Gtk.Button) -> None:
        if self.scanning:
            run_bluetooth("scan", "off", timeout=5)
            self.scanning = False
            self.scan_button.set_label("Buscar dispositivos")
            self.refresh()
            return
        self.scanning = True
        self.scan_button.set_label("Detener búsqueda")
        self.status.set_text("Buscando dispositivos nuevos…")
        run_bluetooth("pairable", "on", timeout=5)
        self.scan_process = subprocess.Popen(
            ["bluetoothctl", "--timeout", "20", "scan", "on"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        GLib.timeout_add_seconds(2, self.refresh)
        GLib.timeout_add_seconds(20, self._stop_scan)

    def _stop_scan(self) -> bool:
        if self.scanning:
            if self.scan_process and self.scan_process.poll() is None:
                self.scan_process.terminate()
            run_bluetooth("scan", "off", timeout=5)
            self.scan_process = None
            self.scanning = False
            self.scan_button.set_label("Buscar dispositivos")
            self.refresh()
        return False

    def _open_settings(self, _button: Gtk.Button) -> None:
        subprocess.Popen(
            ["gnome-control-center", "bluetooth"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        Gtk.main_quit()

    def _on_key(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        return False

    def close_scan(self) -> None:
        if self.scanning:
            if self.scan_process and self.scan_process.poll() is None:
                self.scan_process.terminate()
            run_bluetooth("scan", "off", timeout=5)
            self.scan_process = None
            self.scanning = False


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
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()))
    lock.flush()
    return lock


def main() -> int:
    lock = acquire_lock()
    if lock is None:
        return 0
    window = BluetoothPopup()
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor()
    geometry = monitor.get_geometry()
    present_at(window, geometry.x + geometry.width - 436, geometry.y + 48)
    Gtk.main()
    window.close_scan()
    window.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
