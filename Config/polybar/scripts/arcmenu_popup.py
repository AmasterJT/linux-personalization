#!/usr/bin/env python3
"""Two-column ArcMenu-style application menu for the Debian Polybar icon."""

from pathlib import Path
import fcntl
import json
import os
import pwd
import shlex
import signal
import subprocess

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from popup_behavior import install_click_outside, present_at


RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/runtime-{os.getuid()}"))
LOCK_FILE = RUNTIME_DIR / "linux-personalization-arcmenu.lock"
TERMINAL_COMMAND = (str(Path.home() / ".config/alacritty/alacritty-auto"),)
FAVORITES_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "polybar/arcmenu-favorites.json"

CSS = b"""
#arcmenu-window {
  background-color: rgba(48, 48, 48, 0.96);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 15px;
  color: #f1f1f1;
  font-family: "Noto Sans";
  font-size: 10pt;
}
#menu-card { padding: 10px; }
#column-separator { background: rgba(255,255,255,0.10); min-width: 1px; }
.menu-row {
  background: transparent; border: none; box-shadow: none;
  border-radius: 8px; padding: 4px 6px; color: #eeeeee;
}
.menu-row:hover { background: rgba(255,255,255,0.10); }
.menu-row.selected { background: #f16e44; color: #ffffff; }
.menu-row.selected .menu-row-label { color: #ffffff; font-weight: 700; }
.menu-row-label { color: #eeeeee; font-size: 9.5pt; }
.menu-icon { min-width: 22px; min-height: 22px; }
.section-title { color: #d8d8d8; font-size: 9pt; font-weight: 600; }
.muted { color: #a9a9a9; font-size: 8.5pt; }
.search-entry {
  background: rgba(255,255,255,0.10); color: #ffffff;
  border: none; border-radius: 16px; padding: 8px 10px;
}
.all-apps {
  background: transparent; border: none; box-shadow: none;
  color: #e4e4e4; padding: 5px; border-radius: 7px;
}
.all-apps:hover { background: rgba(255,255,255,0.08); }
.session-button {
  background: transparent; border: none; box-shadow: none;
  color: #f0f0f0; min-width: 31px; min-height: 31px;
  border-radius: 16px; padding: 0;
}
.session-button:hover { background: rgba(255,255,255,0.12); }
.user-icon { background: rgba(255,255,255,0.12); border-radius: 18px; padding: 2px; }
separator { background: rgba(255,255,255,0.09); min-height: 1px; }
"""


DEFAULT_FAVORITES = (
    {"kind": "app", "desktop_id": "brave-browser.desktop", "label": "Brave", "icon": "brave-browser"},
    {"kind": "app", "desktop_id": "org.gnome.Nautilus.desktop", "label": "Archivos", "icon": "org.gnome.Nautilus"},
    {"kind": "command", "id": "terminal", "label": "Terminal", "icon": "Alacritty", "command": list(TERMINAL_COMMAND)},
    {"kind": "app", "desktop_id": "org.gnome.TextEditor.desktop", "label": "Editor de texto", "icon": "org.gnome.TextEditor"},
)


def _valid_favorite(item: object) -> bool:
    if not isinstance(item, dict) or item.get("kind") not in {"app", "command"}:
        return False
    if item["kind"] == "app":
        return isinstance(item.get("desktop_id"), str) and bool(item["desktop_id"])
    command = item.get("command")
    return (
        isinstance(item.get("id"), str)
        and isinstance(command, list)
        and bool(command)
        and all(isinstance(part, str) for part in command)
    )


def load_favorites() -> list[dict[str, object]]:
    try:
        data = json.loads(FAVORITES_FILE.read_text(encoding="utf-8"))
        favorites = [item for item in data if _valid_favorite(item)]
        if favorites:
            return favorites
    except (OSError, TypeError, ValueError):
        pass
    return [dict(item) for item in DEFAULT_FAVORITES]


def save_favorites(favorites: list[dict[str, object]]) -> None:
    FAVORITES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = FAVORITES_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(favorites, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, FAVORITES_FILE)


def spawn(command: tuple[str, ...] | list[str]) -> None:
    try:
        subprocess.Popen(
            list(command), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        pass


class ArcMenu(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.all_mode = False
        self.context_menu_open = False
        self.result_rows: list[Gtk.Button] = []
        self.result_apps: list[Gio.AppInfo | None] = []
        self.selected_result = -1
        self.favorites = load_favorites()
        self.apps = sorted(
            [app for app in Gio.AppInfo.get_all() if app.should_show() and app.get_name()],
            key=lambda app: app.get_name().casefold(),
        )
        self.apps_by_id = {app.get_id(): app for app in self.apps if app.get_id()}
        self.set_title("ArcMenu BSPWM")
        self.set_name("arcmenu-window")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(True)
        self.set_focus_on_map(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_size_request(470, 510)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        card.set_name("menu-card")
        self.add(card)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        left.set_size_request(250, -1)
        self.app_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.app_scroll = Gtk.ScrolledWindow()
        self.app_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.app_scroll.add(self.app_box)
        left.pack_start(self.app_scroll, True, True, 0)

        left.pack_start(Gtk.Separator(), False, False, 0)
        self.all_button = Gtk.Button()
        self.all_button.set_relief(Gtk.ReliefStyle.NONE)
        self.all_button.get_style_context().add_class("all-apps")
        self.all_button.connect("clicked", self._toggle_all)
        left.pack_start(self.all_button, False, False, 0)

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Buscar…")
        self.search.get_style_context().add_class("search-entry")
        self.search.connect("search-changed", self._search_changed)
        self.search.connect("activate", self._launch_first_result)
        left.pack_start(self.search, False, False, 0)
        card.pack_start(left, True, True, 0)

        divider = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        divider.set_name("column-separator")
        card.pack_start(divider, False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        right.set_size_request(175, -1)
        self._build_right_column(right)
        card.pack_start(right, False, False, 0)

        self.connect("key-press-event", self._on_key)
        install_click_outside(self, lambda: not self.context_menu_open)
        self.connect("delete-event", lambda *_args: Gtk.main_quit())
        self._populate_apps()

    def _icon(self, name: str, size: int = 18) -> Gtk.Image:
        image = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.DND)
        image.set_pixel_size(size)
        image.get_style_context().add_class("menu-icon")
        return image

    def _row(self, label: str, icon: str, callback, context_callback=None) -> Gtk.Button:
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.get_style_context().add_class("menu-row")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        text = Gtk.Label(label=label, xalign=0)
        text.get_style_context().add_class("menu-row-label")
        box.pack_start(self._icon(icon), False, False, 0)
        box.pack_start(text, True, True, 0)
        button.add(box)
        button.connect("clicked", callback)
        if context_callback:
            button.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            button.connect("button-press-event", self._row_button_press, context_callback)
        return button

    @staticmethod
    def _row_button_press(button: Gtk.Button, event: Gdk.EventButton, callback) -> bool:
        if event.button != Gdk.BUTTON_SECONDARY:
            return False
        callback(button, event)
        return True

    def _on_focus_out(self, _widget: Gtk.Widget, _event: Gdk.EventFocus) -> bool:
        if not self.context_menu_open:
            GLib.idle_add(self._quit_if_unfocused)
        return False

    def _quit_if_unfocused(self) -> bool:
        if not self.context_menu_open and not self.is_active():
            Gtk.main_quit()
        return False

    def _show_context_menu(self, anchor: Gtk.Widget, event: Gdk.EventButton, actions) -> None:
        self.context_menu_open = True
        menu = Gtk.Menu()
        for label, callback in actions:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _item, action=callback: action())
            menu.append(item)
        menu.attach_to_widget(anchor, None)
        menu.connect("deactivate", self._context_menu_closed)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _context_menu_closed(self, _menu: Gtk.Menu) -> None:
        self.context_menu_open = False
        GLib.idle_add(self.present)

    @staticmethod
    def _favorite_key(favorite: dict[str, object]) -> str:
        if favorite.get("kind") == "app":
            return f"app:{favorite.get('desktop_id', '')}"
        return f"command:{favorite.get('id', '')}"

    @staticmethod
    def _app_key(app: Gio.AppInfo) -> str:
        return f"app:{app.get_id() or ''}"

    def _favorite_index(self, key: str) -> int | None:
        return next(
            (index for index, favorite in enumerate(self.favorites) if self._favorite_key(favorite) == key),
            None,
        )

    def _store_favorites(self) -> None:
        try:
            save_favorites(self.favorites)
        except OSError:
            pass

    def _pin_app(self, app: Gio.AppInfo) -> None:
        desktop_id = app.get_id()
        if not desktop_id or self._favorite_index(self._app_key(app)) is not None:
            return
        icon = app.get_icon()
        self.favorites.append({
            "kind": "app",
            "desktop_id": desktop_id,
            "label": app.get_display_name(),
            "icon": icon.to_string() if icon else "application-x-executable",
        })
        self._store_favorites()
        self._populate_apps(self.search.get_text())

    def _unpin_favorite(self, key: str) -> None:
        index = self._favorite_index(key)
        if index is None:
            return
        self.favorites.pop(index)
        self._store_favorites()
        self._populate_apps(self.search.get_text())

    def _app_context_menu(self, button: Gtk.Button, event: Gdk.EventButton, app: Gio.AppInfo) -> None:
        key = self._app_key(app)
        actions = []
        if self._favorite_index(key) is None:
            actions.append(("Fijar en Inicio", lambda: self._pin_app(app)))
        else:
            actions.append(("Desfijar de Inicio", lambda: self._unpin_favorite(key)))
        actions.append(("Ejecutar como administrador…", lambda: self._launch_as_admin(app)))
        self._show_context_menu(button, event, actions)

    def _favorite_context_menu(
        self, button: Gtk.Button, event: Gdk.EventButton, favorite: dict[str, object]
    ) -> None:
        key = self._favorite_key(favorite)
        actions = [("Desfijar de Inicio", lambda: self._unpin_favorite(key))]
        if favorite.get("kind") == "app":
            app = self.apps_by_id.get(str(favorite.get("desktop_id")))
            if app:
                actions.append(("Ejecutar como administrador…", lambda: self._launch_as_admin(app)))
        self._show_context_menu(button, event, actions)

    def _build_right_column(self, column: Gtk.Box) -> None:
        user_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        user_icon = self._user_avatar()
        user_icon.get_style_context().add_class("user-icon")
        username = pwd.getpwuid(os.getuid()).pw_name
        user_label = Gtk.Label(label=username, xalign=0)
        user_label.get_style_context().add_class("section-title")
        user_row.pack_start(user_icon, False, False, 0)
        user_row.pack_start(user_label, True, True, 0)
        column.pack_start(user_row, False, False, 3)
        column.pack_start(Gtk.Separator(), False, False, 6)

        locations = (
            ("Inicio", "user-home-symbolic", Path.home()),
            ("Documentos", "folder-documents-symbolic", self._user_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS, "Documentos")),
            ("Descargas", "folder-download-symbolic", self._user_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD, "Descargas")),
            ("Música", "folder-music-symbolic", self._user_dir(GLib.UserDirectory.DIRECTORY_MUSIC, "Música")),
            ("Imágenes", "folder-pictures-symbolic", self._user_dir(GLib.UserDirectory.DIRECTORY_PICTURES, "Imágenes")),
            ("Vídeos", "folder-videos-symbolic", self._user_dir(GLib.UserDirectory.DIRECTORY_VIDEOS, "Vídeos")),
        )
        for label, icon, path in locations:
            column.pack_start(
                self._row(label, icon, lambda _button, target=path: self._launch(("nautilus", str(target)))),
                False, False, 0,
            )
        column.pack_start(Gtk.Separator(), False, False, 6)

        system_rows = (
            ("Software", "org.gnome.Software-symbolic", ("gnome-software",)),
            (
                "Ajustes", "org.gnome.Settings-symbolic",
                ("env", "XDG_CURRENT_DESKTOP=GNOME", "gnome-control-center"),
            ),
            ("Retoques", "org.gnome.tweaks-symbolic", ("gnome-tweaks",)),
            ("Terminal", "utilities-terminal-symbolic", TERMINAL_COMMAND),
            (
                "Vista de ventanas", "view-grid-symbolic",
                (
                    "rofi", "-no-lazy-grab", "-show", "window", "-theme",
                    str(Path.home() / ".config/rofi/themes/amaster-blur.rasi"),
                ),
            ),
        )
        for label, icon, command in system_rows:
            column.pack_start(
                self._row(label, icon, lambda _button, cmd=command: self._launch(cmd)),
                False, False, 0,
            )

        session = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        session.set_halign(Gtk.Align.END)
        session.pack_start(
            self._session_button(
                "system-lock-screen-symbolic",
                "Bloquear",
                (str(Path.home() / ".config/bspwm/scripts/gdm_lock_screen.sh"),),
            ),
            False,
            False,
            0,
        )
        session.pack_start(self._session_button("system-log-out-symbolic", "Cerrar sesión", ("bspc", "quit"), True), False, False, 0)
        session.pack_start(self._session_button("system-reboot-symbolic", "Reiniciar", ("systemctl", "reboot"), True), False, False, 0)
        session.pack_start(self._session_button("system-shutdown-symbolic", "Apagar", ("systemctl", "poweroff"), True), False, False, 0)
        column.pack_end(session, False, False, 0)

    @staticmethod
    def _user_dir(directory, fallback: str) -> Path:
        value = GLib.get_user_special_dir(directory)
        return Path(value) if value else Path.home() / fallback

    def _user_avatar(self) -> Gtk.Image:
        username = pwd.getpwuid(os.getuid()).pw_name
        candidates = (
            Path("/var/lib/AccountsService/icons") / username,
            Path.home() / ".face",
            Path.home() / ".face.icon",
        )
        for path in candidates:
            try:
                if path.exists():
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 32, 32, True)
                    image = Gtk.Image.new_from_pixbuf(pixbuf)
                    image.get_style_context().add_class("user-icon")
                    return image
            except GLib.Error:
                continue
        image = self._icon("avatar-default-symbolic", 26)
        image.get_style_context().add_class("user-icon")
        return image

    def _session_button(self, icon: str, tooltip: str, command: tuple[str, ...], confirm: bool = False) -> Gtk.Button:
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_image(self._icon(icon, 17))
        button.set_tooltip_text(tooltip)
        button.get_style_context().add_class("session-button")
        if confirm:
            button.connect("clicked", lambda _button: self._confirm_action(tooltip, command))
        else:
            button.connect("clicked", lambda _button: self._launch(command))
        return button

    def _populate_apps(self, query: str = "") -> None:
        self.result_rows = []
        self.result_apps = []
        self.selected_result = -1
        for child in self.app_box.get_children():
            self.app_box.remove(child)
        if query or self.all_mode:
            normalized = query.casefold().strip()
            apps = [app for app in self.apps if not normalized or normalized in app.get_name().casefold()][:40]
            for app in apps:
                icon = app.get_icon()
                icon_name = icon.to_string() if icon else "application-x-executable"
                row = self._row(
                    app.get_name(), icon_name,
                    lambda _button, selected=app: self._launch_app(selected),
                    lambda button, event, selected=app: self._app_context_menu(button, event, selected),
                )
                row.set_tooltip_text("Clic izquierdo: abrir · Clic derecho: fijar o desfijar")
                self.app_box.pack_start(row, False, False, 0)
                self.result_rows.append(row)
                self.result_apps.append(app)
        else:
            for favorite in self.favorites:
                label = str(favorite.get("label") or "Aplicación")
                icon = str(favorite.get("icon") or "application-x-executable")
                if favorite.get("kind") == "app":
                    app = self.apps_by_id.get(str(favorite.get("desktop_id")))
                    if not app:
                        continue
                    callback = lambda _button, selected=app: self._launch_app(selected)
                else:
                    command = tuple(
                        os.path.expandvars(os.path.expanduser(str(part)))
                        for part in favorite.get("command", [])
                    )
                    callback = lambda _button, cmd=command: self._launch(cmd)
                row = self._row(
                    label, icon, callback,
                    lambda button, event, item=favorite: self._favorite_context_menu(button, event, item),
                )
                row.set_tooltip_text("Clic izquierdo: abrir · Clic derecho: desfijar")
                self.app_box.pack_start(row, False, False, 0)
                self.result_rows.append(row)
                self.result_apps.append(app if favorite.get("kind") == "app" else None)
        self.all_button.set_label("‹  Favoritos" if self.all_mode else "Todas las aplicaciones  ›")
        self.app_box.show_all()
        if self.result_rows:
            self._select_result(0)

    def _select_result(self, index: int) -> None:
        if not self.result_rows:
            self.selected_result = -1
            return
        index = max(0, min(index, len(self.result_rows) - 1))
        for number, row in enumerate(self.result_rows):
            context = row.get_style_context()
            if number == index:
                context.add_class("selected")
            else:
                context.remove_class("selected")
        self.selected_result = index
        GLib.idle_add(self._scroll_selected_into_view, self.result_rows[index])

    def _scroll_selected_into_view(self, row: Gtk.Widget) -> bool:
        adjustment = self.app_scroll.get_vadjustment()
        allocation = row.get_allocation()
        top = allocation.y
        bottom = top + allocation.height
        if top < adjustment.get_value():
            adjustment.set_value(top)
        elif bottom > adjustment.get_value() + adjustment.get_page_size():
            adjustment.set_value(bottom - adjustment.get_page_size())
        return GLib.SOURCE_REMOVE

    def _toggle_all(self, _button: Gtk.Button) -> None:
        self.all_mode = not self.all_mode
        self.search.set_text("")
        self._populate_apps()

    def _search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._populate_apps(entry.get_text())

    def _launch_first_result(self, entry: Gtk.SearchEntry) -> None:
        app = (
            self.result_apps[self.selected_result]
            if 0 <= self.selected_result < len(self.result_apps)
            else None
        )
        if app:
            self._launch_app(app)

    def _launch_as_admin(self, app: Gio.AppInfo) -> None:
        commandline = app.get_commandline() or app.get_executable() or ""
        try:
            parts = shlex.split(commandline)
        except ValueError:
            return
        parts = [part for part in parts if not part.startswith("%")]
        if not parts:
            return
        environment = [
            "pkexec", "env", f"DISPLAY={os.environ.get('DISPLAY', ':0')}",
            f"XAUTHORITY={os.environ.get('XAUTHORITY', str(Path.home() / '.Xauthority'))}",
            f"XDG_RUNTIME_DIR={os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')}",
        ]
        self._launch(tuple(environment + parts))

    def focus_search(self) -> bool:
        """Focus the search field after the window has been mapped."""
        self.set_focus(self.search)
        self.search.grab_focus()
        self.search.set_position(-1)
        return GLib.SOURCE_REMOVE

    def _launch_app(self, app: Gio.AppInfo) -> None:
        Gtk.main_quit()
        try:
            app.launch([], None)
        except GLib.Error:
            pass

    def _launch(self, command: tuple[str, ...] | list[str]) -> None:
        Gtk.main_quit()
        spawn(command)

    def _confirm_action(self, label: str, command: tuple[str, ...]) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.CANCEL,
            text=f"¿{label}?",
        )
        dialog.add_button(label, Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self._launch(command)

    def _on_key(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        if event.keyval == Gdk.KEY_slash and not self.search.has_focus():
            self.search.grab_focus()
            return True
        if event.keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            self._select_result(self.selected_result + 1)
            return True
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            self._select_result(self.selected_result - 1)
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._launch_first_result(self.search)
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
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()))
    lock.flush()
    return lock


def main() -> int:
    lock = acquire_lock()
    if lock is None:
        return 0
    window = ArcMenu()
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor()
    geometry = monitor.get_geometry()
    present_at(window, geometry.x + 6, geometry.y + 48)
    GLib.idle_add(window.focus_search)
    Gtk.main()
    window.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
