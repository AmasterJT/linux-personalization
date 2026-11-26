#!/usr/bin/env python3
"""Shared, reliable outside-click dismissal for BSPWM GTK popups."""

import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402


def popup_size(window: Gtk.Window) -> tuple[int, int]:
    """Measure the popup with its contents shown, while it is still unmapped."""
    window.get_child().show_all()
    minimum, natural = window.get_preferred_size()
    default_width, default_height = window.get_default_size()
    width = default_width if default_width > 0 else natural.width
    height = default_height if default_height > 0 else natural.height
    return max(minimum.width, width), max(minimum.height, height)


def present_at(
    window: Gtk.Window, x: int, y: int, wm_class: str = "BspwmPolybarPopup"
) -> None:
    """Give BSPWM the final X11 position before its first MapRequest."""
    window.set_wmclass(GLib.get_prgname() or "polybar-popup", wm_class)
    if not window.get_child().get_visible():
        window.get_child().show_all()
    window.move(x, y)
    window.realize()
    # Gtk.Window.move can defer its X11 ConfigureWindow until the first layout.
    # Set the initial native geometry now so BSPWM cannot center it first.
    window.get_window().move(x, y)
    window.present()


BUTTON_MASKS = (
    Gdk.ModifierType.BUTTON1_MASK
    | Gdk.ModifierType.BUTTON2_MASK
    | Gdk.ModifierType.BUTTON3_MASK
)


class OutsideClickController:
    def __init__(
        self,
        window: Gtk.Window,
        can_close: Callable[[], bool] | None = None,
        grace_seconds: float = 0.65,
    ) -> None:
        self.window = window
        self.can_close = can_close or (lambda: True)
        self.grace_seconds = grace_seconds
        self.opened_at = time.monotonic()
        self.previous_pressed = False
        self.closed = False
        window.connect("focus-out-event", self._focus_out)
        GLib.timeout_add(45, self._poll_pointer)

    def _ready(self) -> bool:
        return (
            time.monotonic() - self.opened_at >= self.grace_seconds
            and self.can_close()
        )

    def _close(self) -> bool:
        if not self.closed and self._ready():
            self.closed = True
            Gtk.main_quit()
        return GLib.SOURCE_REMOVE

    def _focus_out(self, _window, _event) -> bool:
        if self._ready():
            GLib.timeout_add(80, self._close)
        return False

    def _poll_pointer(self) -> bool:
        if self.closed or not self.window.get_visible():
            return GLib.SOURCE_REMOVE
        try:
            display = Gdk.Display.get_default()
            pointer = display.get_default_seat().get_pointer()
            _screen, pointer_x, pointer_y = pointer.get_position()
            _axes, modifiers = pointer.get_state(
                self.window.get_screen().get_root_window()
            )
            pressed = bool(modifiers & BUTTON_MASKS)
            window_x, window_y = self.window.get_position()
            width, height = self.window.get_size()
            outside = not (
                window_x <= pointer_x < window_x + width
                and window_y <= pointer_y < window_y + height
            )
            if pressed and not self.previous_pressed and outside and self._ready():
                self._close()
                return GLib.SOURCE_REMOVE
            self.previous_pressed = pressed
        except (AttributeError, TypeError):
            pass
        return GLib.SOURCE_CONTINUE


def install_click_outside(
    window: Gtk.Window,
    can_close: Callable[[], bool] | None = None,
) -> OutsideClickController:
    controller = OutsideClickController(window, can_close)
    window._outside_click_controller = controller  # type: ignore[attr-defined]
    return controller
