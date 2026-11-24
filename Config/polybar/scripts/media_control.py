#!/usr/bin/env python3
"""Control the currently active MPRIS player without requiring playerctl."""

import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402


OBJECT_PATH = "/org/mpris/MediaPlayer2"
PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"


def unpack(value):
    while isinstance(value, GLib.Variant):
        value = value.unpack()
    return value


def players(connection: Gio.DBusConnection) -> list[Gio.DBusProxy]:
    reply = connection.call_sync(
        "org.freedesktop.DBus", "/org/freedesktop/DBus",
        "org.freedesktop.DBus", "ListNames", None,
        GLib.VariantType("(as)"), Gio.DBusCallFlags.NONE, 2_000, None,
    )
    names = [name for name in reply.unpack()[0] if name.startswith("org.mpris.MediaPlayer2.")]
    proxies = []
    for name in names:
        try:
            proxies.append(Gio.DBusProxy.new_sync(
                connection, Gio.DBusProxyFlags.DO_NOT_AUTO_START, None,
                name, OBJECT_PATH, PLAYER_INTERFACE, None,
            ))
        except GLib.Error:
            continue
    return proxies


def playback_status(proxy: Gio.DBusProxy) -> str:
    value = proxy.get_cached_property("PlaybackStatus")
    return str(unpack(value)) if value is not None else "Stopped"


def main() -> int:
    methods = {"play-pause": "PlayPause", "previous": "Previous", "next": "Next"}
    action = sys.argv[1] if len(sys.argv) > 1 else "play-pause"
    method = methods.get(action)
    if method is None:
        print(f"Acción desconocida: {action}", file=sys.stderr)
        return 2

    available = players(Gio.bus_get_sync(Gio.BusType.SESSION, None))
    if not available:
        return 0
    player = next((item for item in available if playback_status(item) == "Playing"), available[0])
    player.call_sync(method, None, Gio.DBusCallFlags.NONE, 2_000, None)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (GLib.Error, OSError) as error:
        print(f"MPRIS no disponible: {error}", file=sys.stderr)
        raise SystemExit(0)
