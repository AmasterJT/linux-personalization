#!/usr/bin/env python3
"""GTK window switcher with live X11 previews for BSPWM."""

from __future__ import annotations

from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GdkPixbuf, GdkX11, GLib, Gtk, Pango, Wnck  # noqa: E402


RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/runtime-{os.getuid()}"))
LOCK_FILE = RUNTIME_DIR / "linux-personalization-window-switcher.lock"
PREVIEW_WIDTH = 228
PREVIEW_HEIGHT = 132
CARD_WIDTH = 246
CARD_HEIGHT = 180
# Gtk.FlowBox wraps each button in a child with 3 px of internal spacing, and
# the card's CSS padding raises its natural size above the raw size request.
GRID_CELL_WIDTH = 262
GRID_CELL_HEIGHT = 209
GRID_SPACING = 10
MAX_COLUMNS = 4
MAX_VISIBLE_ROWS = 2

CSS = b"""
#switcher-window {
  background-color: rgba(20, 22, 30, 0.97);
  border: 1px solid rgba(255,255,255,0.10);
  /* BSPWM uses a 15 px outer radius around a 3 px border. */
  border-radius: 12px;
  color: #f1f2f7;
  font-family: "Noto Sans";
}
#switcher-card {
  background: transparent;
  border: 2px solid transparent;
  border-radius: 13px;
  box-shadow: none;
  padding: 10px;
  color: #e7e9f1;
}
#switcher-card:hover { background: #282c39; }
#switcher-card.selected {
  background: #303645;
  border-color: #f16e44;
}
#preview-frame {
  background: #0d1017;
  border-radius: 8px;
  padding: 2px;
}
#window-title { font-size: 10pt; font-weight: 600; color: #f4f5f8; }
#window-workspace { font-size: 8.5pt; color: #a1a6b5; }
scrollbar { background: transparent; }
scrollbar slider {
  background: #444a5b;
  border-radius: 4px;
  min-width: 6px;
  min-height: 24px;
}
"""


@dataclass
class WindowEntry:
    window: Wnck.Window
    xid: int
    title: str
    workspace: str
    preview: GdkPixbuf.Pixbuf | None
    icon: GdkPixbuf.Pixbuf | None


def scaled_pixbuf(
    pixbuf: GdkPixbuf.Pixbuf, max_width: int, max_height: int
) -> GdkPixbuf.Pixbuf:
    width = max(1, pixbuf.get_width())
    height = max(1, pixbuf.get_height())
    factor = min(max_width / width, max_height / height)
    target_width = max(1, round(width * factor))
    target_height = max(1, round(height * factor))
    return pixbuf.scale_simple(
        target_width, target_height, GdkPixbuf.InterpType.BILINEAR
    )


def pixbuf_is_blank(pixbuf: GdkPixbuf.Pixbuf) -> bool:
    """Detect the all-black pixmap X11 exposes for an unmapped workspace."""
    width = pixbuf.get_width()
    height = pixbuf.get_height()
    channels = pixbuf.get_n_channels()
    rowstride = pixbuf.get_rowstride()
    pixels = pixbuf.get_pixels()
    visible_samples = 0
    for y in range(0, height, max(1, height // 12)):
        for x in range(0, width, max(1, width // 16)):
            offset = y * rowstride + x * channels
            if sum(pixels[offset : offset + 3]) > 18:
                visible_samples += 1
                if visible_samples >= 3:
                    return False
    return True


def capture_window(xid: int) -> GdkPixbuf.Pixbuf | None:
    """Capture a mapped X11 client; hidden workspaces safely fall back to icons."""
    try:
        display = Gdk.Display.get_default()
        gdk_window = GdkX11.X11Window.foreign_new_for_display(display, xid)
        if gdk_window is None:
            return None
        _x, _y, width, height = gdk_window.get_geometry()
        if width < 2 or height < 2:
            return None
        pixbuf = Gdk.pixbuf_get_from_window(gdk_window, 0, 0, width, height)
        if pixbuf is None:
            return None
        preview = scaled_pixbuf(pixbuf, PREVIEW_WIDTH, PREVIEW_HEIGHT)
        return None if pixbuf_is_blank(preview) else preview
    except (GLib.Error, TypeError, ValueError):
        return None


def workspace_label(window: Wnck.Window) -> str:
    workspace = window.get_workspace()
    if workspace is None:
        return "Todos los escritorios"
    name = workspace.get_name() or str(workspace.get_number() + 1)
    return f"Espacio {name}"


def collect_windows() -> tuple[list[WindowEntry], int | None]:
    screen = Wnck.Screen.get_default()
    screen.force_update()
    active = screen.get_active_window()
    active_workspace = screen.get_active_workspace()
    active_xid = active.get_xid() if active is not None else None

    # Only show clients visible on the current workspace. Wnck also returns true
    # for pinned windows because they are deliberately visible on every desktop.
    # Top-most windows come first, with the focused window at index 0.
    candidates = list(reversed(screen.get_windows_stacked()))
    candidates.sort(key=lambda window: window.get_xid() != active_xid)
    entries: list[WindowEntry] = []
    allowed_types = {
        Wnck.WindowType.NORMAL,
        Wnck.WindowType.DIALOG,
        Wnck.WindowType.UTILITY,
    }
    for window in candidates:
        if window.is_skip_tasklist() or window.get_window_type() not in allowed_types:
            continue
        if active_workspace is not None and not window.is_on_workspace(active_workspace):
            continue
        title = (window.get_name() or "Ventana sin título").strip()
        if not title:
            title = "Ventana sin título"
        icon = window.get_icon()
        if icon is not None:
            icon = scaled_pixbuf(icon, 48, 48)
        entries.append(
            WindowEntry(
                window=window,
                xid=window.get_xid(),
                title=title,
                workspace=workspace_label(window),
                preview=capture_window(window.get_xid()),
                icon=icon,
            )
        )
    return entries, active_xid


class WindowSwitcher(Gtk.Window):
    def __init__(
        self,
        previous: bool,
        auto_activate_on_alt_release: bool,
        alt_down_on_start: bool,
    ) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.entries, active_xid = collect_windows()
        self.cards: list[Gtk.Button] = []
        self.columns = max(1, min(MAX_COLUMNS, len(self.entries)))
        self.selected = 0
        self.closing = False
        self.auto_activate_on_alt_release = auto_activate_on_alt_release
        self.alt_was_pressed = alt_down_on_start
        self.alt_watch_started = time.monotonic()

        self.set_title("Selector de ventanas")
        self.set_wmclass("bspwm-window-switcher", "BspwmWindowSwitcher")
        self.set_name("switcher-window")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(True)
        self.set_focus_on_map(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_border_width(14)
        self.add(outer)

        card_grid = Gtk.FlowBox()
        card_grid.set_selection_mode(Gtk.SelectionMode.NONE)
        card_grid.set_homogeneous(True)
        card_grid.set_row_spacing(GRID_SPACING)
        card_grid.set_column_spacing(GRID_SPACING)
        card_grid.set_min_children_per_line(self.columns)
        card_grid.set_max_children_per_line(MAX_COLUMNS)
        card_grid.set_halign(Gtk.Align.CENTER)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_shadow_type(Gtk.ShadowType.NONE)
        scroller.set_overlay_scrolling(False)
        scroller.add(card_grid)
        outer.pack_start(scroller, True, True, 0)

        for index, entry in enumerate(self.entries):
            card = self._create_card(entry, index)
            self.cards.append(card)
            card_grid.insert(card, -1)

        if self.entries:
            active_index = next(
                (i for i, entry in enumerate(self.entries) if entry.xid == active_xid), 0
            )
            direction = -1 if previous else 1
            self.selected = (active_index + direction) % len(self.entries)
            self._update_selection()

        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geometry = monitor.get_workarea()
        total_rows = max(1, (len(self.entries) + self.columns - 1) // self.columns)
        visible_rows = min(MAX_VISIBLE_ROWS, total_rows)
        grid_width = self.columns * GRID_CELL_WIDTH + (self.columns - 1) * GRID_SPACING
        grid_height = visible_rows * GRID_CELL_HEIGHT + (visible_rows - 1) * GRID_SPACING
        scrollbar_width = 12 if total_rows > visible_rows else 0
        content_width = min(round(geometry.width * 0.90), grid_width + scrollbar_width + 28)
        content_height = grid_height + 28
        card_grid.set_size_request(grid_width, -1)
        scroller.set_size_request(grid_width + scrollbar_width, grid_height)
        scroller.set_min_content_height(grid_height)
        scroller.set_max_content_height(grid_height)
        scroller.set_propagate_natural_height(False)
        self.set_size_request(content_width, content_height)
        self.set_default_size(content_width, content_height)

        self.connect("key-press-event", self._on_key_press)
        self.connect("key-release-event", self._on_key_release)
        self.connect("delete-event", lambda *_args: Gtk.main_quit())

    def _create_card(self, entry: WindowEntry, index: int) -> Gtk.Button:
        card = Gtk.Button()
        card.set_name("switcher-card")
        card.set_relief(Gtk.ReliefStyle.NONE)
        card.set_size_request(CARD_WIDTH, CARD_HEIGHT)
        card.connect("clicked", lambda _button, selected=index: self.activate(selected))

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        frame = Gtk.Box()
        frame.set_name("preview-frame")
        frame.set_size_request(PREVIEW_WIDTH + 4, PREVIEW_HEIGHT + 4)
        frame.set_halign(Gtk.Align.CENTER)
        frame.set_valign(Gtk.Align.CENTER)

        image = Gtk.Image()
        if entry.preview is not None:
            image.set_from_pixbuf(entry.preview)
        elif entry.icon is not None:
            image.set_from_pixbuf(entry.icon)
        else:
            image.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
        image.set_halign(Gtk.Align.CENTER)
        image.set_valign(Gtk.Align.CENTER)
        frame.pack_start(image, True, True, 0)
        content.pack_start(frame, True, True, 0)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        if entry.icon is not None:
            icon = Gtk.Image.new_from_pixbuf(scaled_pixbuf(entry.icon, 20, 20))
            title_row.pack_start(icon, False, False, 0)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title = Gtk.Label(label=entry.title, xalign=0)
        title.set_name("window-title")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.set_max_width_chars(27)
        workspace = Gtk.Label(label=entry.workspace, xalign=0)
        workspace.set_name("window-workspace")
        labels.pack_start(title, False, False, 0)
        labels.pack_start(workspace, False, False, 0)
        title_row.pack_start(labels, True, True, 0)
        content.pack_start(title_row, False, False, 0)
        card.add(content)
        return card

    def move_selection(self, direction: int) -> bool:
        if not self.entries:
            return False
        self.selected = (self.selected + direction) % len(self.entries)
        self._update_selection()
        return False

    def move_vertical(self, direction: int) -> bool:
        """Move by grid rows without wrapping unexpectedly to the first row."""
        if not self.entries:
            return False
        target = self.selected + direction * self.columns
        if target < 0:
            return False
        if target >= len(self.entries):
            last_row_start = ((len(self.entries) - 1) // self.columns) * self.columns
            if direction > 0 and self.selected < last_row_start:
                target = len(self.entries) - 1
            else:
                return False
        self.selected = target
        self._update_selection()
        return False

    def _update_selection(self) -> None:
        for index, card in enumerate(self.cards):
            context = card.get_style_context()
            if index == self.selected:
                context.add_class("selected")
                card.grab_focus()
            else:
                context.remove_class("selected")

    def activate(self, index: int | None = None) -> None:
        if self.closing:
            return
        self.closing = True
        if index is not None:
            self.selected = index
        if not self.entries:
            Gtk.main_quit()
            return
        xid = self.entries[self.selected].xid
        subprocess.run(
            ["bspc", "node", f"0x{xid:x}", "-f"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        Gtk.main_quit()

    def watch_alt_release(self) -> bool:
        """Confirm the selection even when SXHKD consumes Alt's release event."""
        if not self.auto_activate_on_alt_release or self.closing:
            return False
        keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
        state = keymap.get_modifier_state()
        if state & Gdk.ModifierType.MOD1_MASK:
            self.alt_was_pressed = True
            return True

        # Normally Alt was observed at process start. The short grace period
        # also handles a very quick tap released while previews were captured.
        if self.alt_was_pressed or time.monotonic() - self.alt_watch_started >= 0.18:
            self.activate()
            return False
        return True

    def _on_key_press(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.activate()
            return True
        if event.keyval == Gdk.KEY_Right:
            self.move_selection(1)
            return True
        if event.keyval == Gdk.KEY_Left:
            self.move_selection(-1)
            return True
        if event.keyval == Gdk.KEY_Down:
            self.move_vertical(1)
            return True
        if event.keyval == Gdk.KEY_Up:
            self.move_vertical(-1)
            return True
        if event.keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            backwards = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
            self.move_selection(-1 if backwards else 1)
            return True
        return False

    def _on_key_release(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval in (Gdk.KEY_Alt_L, Gdk.KEY_Alt_R):
            self.activate()
            return True
        return False


def signal_existing(previous: bool) -> bool:
    try:
        pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGUSR2 if previous else signal.SIGUSR1)
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return False


def acquire_lock(previous: bool):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = LOCK_FILE.open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        signal_existing(previous)
        return None
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()))
    lock.flush()
    return lock


def main() -> int:
    previous = "--previous" in sys.argv[1:]
    auto_activate = "--alt-held" in sys.argv[1:]
    keymap = Gdk.Keymap.get_for_display(Gdk.Display.get_default())
    alt_down_on_start = bool(
        keymap.get_modifier_state() & Gdk.ModifierType.MOD1_MASK
    )
    lock = acquire_lock(previous)
    if lock is None:
        return 0

    switcher = WindowSwitcher(previous, auto_activate, alt_down_on_start)
    if not switcher.entries:
        return 0

    signal.signal(signal.SIGUSR1, lambda *_args: GLib.idle_add(switcher.move_selection, 1))
    signal.signal(signal.SIGUSR2, lambda *_args: GLib.idle_add(switcher.move_selection, -1))
    switcher.show_all()
    switcher.present()
    if auto_activate:
        GLib.timeout_add(20, switcher.watch_alt_release)
    Gtk.main()
    switcher.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
