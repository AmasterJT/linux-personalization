#!/usr/bin/env python3
"""Small Spotify MPRIS client for Polybar; requires only system PyGObject."""

from __future__ import annotations

import subprocess
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


BUS_NAME = "org.mpris.MediaPlayer2.spotify"
OBJECT_PATH = "/org/mpris/MediaPlayer2"
PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
MAX_LABEL_LENGTH = 36


def session_bus() -> Gio.DBusConnection:
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)


def has_owner(connection: Gio.DBusConnection) -> bool:
    reply = connection.call_sync(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "NameHasOwner",
        GLib.Variant("(s)", (BUS_NAME,)),
        GLib.VariantType("(b)"),
        Gio.DBusCallFlags.NONE,
        1_000,
        None,
    )
    return bool(reply.unpack()[0])


def player_proxy(connection: Gio.DBusConnection) -> Gio.DBusProxy:
    return Gio.DBusProxy.new_sync(
        connection,
        Gio.DBusProxyFlags.DO_NOT_AUTO_START,
        None,
        BUS_NAME,
        OBJECT_PATH,
        PLAYER_INTERFACE,
        None,
    )


def unpack(value):
    while isinstance(value, GLib.Variant):
        value = value.unpack()
    return value


def playback_status(proxy: Gio.DBusProxy) -> str:
    value = proxy.get_cached_property("PlaybackStatus")
    return str(unpack(value)) if value is not None else "Stopped"


def metadata_label(proxy: Gio.DBusProxy) -> str:
    value = proxy.get_cached_property("Metadata")
    metadata = unpack(value) if value is not None else {}
    title = str(unpack(metadata.get("xesam:title", ""))).strip()
    artists = unpack(metadata.get("xesam:artist", []))
    if isinstance(artists, str):
        artist = artists.strip()
    else:
        artist = ", ".join(str(unpack(item)).strip() for item in artists if item)

    label = " — ".join(part for part in (artist, title) if part) or "Spotify"
    label = label.replace("%{", "% {").replace("\n", " ")
    if len(label) > MAX_LABEL_LENGTH:
        label = f"{label[: MAX_LABEL_LENGTH - 1]}…"
    return label


def launch_spotify() -> None:
    subprocess.Popen(
        ["spotify"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    connection = session_bus()
    available = has_owner(connection)

    if action == "status":
        if not available:
            print("Spotify")
            return 0
        print(metadata_label(player_proxy(connection)))
        return 0

    if action == "icon":
        if not available:
            print("")
            return 0
        print("" if playback_status(player_proxy(connection)) == "Playing" else "")
        return 0

    methods = {
        "play-pause": "PlayPause",
        "previous": "Previous",
        "next": "Next",
    }
    method = methods.get(action)
    if method is None:
        print(f"Acción desconocida: {action}", file=sys.stderr)
        return 2

    if not available:
        if action == "play-pause":
            launch_spotify()
        return 0

    proxy = player_proxy(connection)
    proxy.call_sync(method, None, Gio.DBusCallFlags.NONE, 2_000, None)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GLib.Error, OSError) as error:
        print(f"Spotify no disponible: {error}", file=sys.stderr)
        raise SystemExit(0)
