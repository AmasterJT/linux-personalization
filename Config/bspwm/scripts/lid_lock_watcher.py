#!/usr/bin/env python3
"""Lock the BSPWM session when UPower reports that the laptop lid closed."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


CONFIG_PATH = Path.home() / ".config/bspwm/lid-lock.conf"
LOCK_SCRIPT = Path.home() / ".config/bspwm/scripts/gdm_lock_screen.sh"
INTERNAL_OUTPUT_PREFIXES = ("eDP", "LVDS", "DSI")


def as_bool(value: str, default: bool) -> bool:
    normalized = value.strip().strip("'\"").lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def load_config() -> dict[str, bool]:
    settings = {
        "LOCK_ON_LID_CLOSE": True,
        "LOCK_WHEN_EXTERNAL_MONITOR": True,
    }
    try:
        lines = CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return settings

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in settings:
            settings[key] = as_bool(value, settings[key])
    return settings


def external_monitor_connected() -> bool:
    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return False

    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[1] != "connected":
            continue
        if not fields[0].startswith(INTERNAL_OUTPUT_PREFIXES):
            return True
    return False


def request_lock() -> None:
    settings = load_config()
    if not settings["LOCK_ON_LID_CLOSE"]:
        return
    if external_monitor_connected() and not settings["LOCK_WHEN_EXTERNAL_MONITOR"]:
        return
    if not os.access(LOCK_SCRIPT, os.X_OK):
        print(f"Lid watcher: lock script is not executable: {LOCK_SCRIPT}", file=sys.stderr)
        return

    subprocess.Popen(
        [str(LOCK_SCRIPT)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def variant_bool(value: object) -> bool:
    while isinstance(value, GLib.Variant):
        value = value.unpack()
    return value is True


def properties_changed(
    _connection: Gio.DBusConnection,
    _sender_name: str,
    _object_path: str,
    _interface_name: str,
    _signal_name: str,
    parameters: GLib.Variant,
    _user_data: object,
) -> None:
    changed_interface, changed_properties, _invalidated = parameters.unpack()
    if changed_interface != "org.freedesktop.UPower":
        return
    if "LidIsClosed" in changed_properties and variant_bool(
        changed_properties["LidIsClosed"]
    ):
        request_lock()


def main() -> int:
    connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    connection.signal_subscribe(
        "org.freedesktop.UPower",
        "org.freedesktop.DBus.Properties",
        "PropertiesChanged",
        "/org/freedesktop/UPower",
        "org.freedesktop.UPower",
        Gio.DBusSignalFlags.NONE,
        properties_changed,
        None,
    )
    GLib.MainLoop().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
