#!/usr/bin/env python3
"""GTK Wi-Fi menu for the Polybar network module."""

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
gi.require_version("Pango", "1.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from popup_behavior import install_click_outside


RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/runtime-{os.getuid()}"))
LOCK_FILE = RUNTIME_DIR / "linux-personalization-wifi.lock"

CSS = b"""
#wifi-window {
  background-color: #171922;
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 14px;
  color: #e5e7ef;
  font-family: "Noto Sans";
  font-size: 10pt;
}
#wifi-card { padding: 16px; }
#title { color: #f1f2f7; font-size: 12pt; font-weight: 700; }
#subtitle, #status { color: #a1a6b5; font-size: 9pt; }
.network-row {
  background: transparent; border: none; box-shadow: none;
  border-radius: 9px; padding: 10px; color: #e5e7ef;
}
.network-row:hover { background: #282c39; }
.network-name { color: #f0f1f6; font-size: 10pt; font-weight: 600; }
.network-state { color: #a1a6b5; font-size: 8.5pt; }
.network-icon { color: #4da3e6; font: 16pt "Hack Nerd Font"; }
.connected { color: #43a047; }
.action-button {
  background: #222632; border: none; box-shadow: none;
  border-radius: 9px; padding: 10px 12px; color: #f0f1f6;
  font-size: 9pt; font-weight: 600;
}
.action-button:hover { background: #303544; }
.primary { background: #f16e44; color: #ffffff; }
.primary:hover { background: #f8825c; }
.tab-switcher button { background: transparent; border: none; box-shadow: none;
  color: #a1a6b5; padding: 7px 16px; }
.tab-switcher button:checked { color: #ffffff; background: #282c39; border-radius: 9px; }
.vpn-summary { background: #20232e; border-radius: 11px; padding: 12px; }
.vpn-row { background: transparent; border-radius: 9px; padding: 9px; }
.vpn-row:hover { background: #282c39; }
.vpn-active { color: #45c392; font-weight: 700; }
.vpn-offline { color: #8c91a0; }
.vpn-loading { min-width: 22px; min-height: 22px; }
.password-box { background: #20232e; border-radius: 9px; padding: 10px; }
.password-entry {
  background: #151720; color: #ffffff; border: 1px solid #3b4050;
  border-radius: 7px; padding: 8px 10px;
}
switch { background: #343846; border-radius: 12px; }
switch:checked { background: #f16e44; }
switch slider { min-width: 18px; min-height: 18px; border-radius: 9px; }
separator { background: rgba(255,255,255,0.08); min-height: 1px; }
"""

VPN_KEYWORDS = {
    "Cloudflare WARP": ("cloudflare", "warp"),
    "Proton VPN": ("proton vpn", "protonvpn", "proton.vpn"),
    "NordVPN": ("nordvpn", "nord vpn"),
    "Mullvad VPN": ("mullvad",),
    "ExpressVPN": ("expressvpn",),
    "Surfshark": ("surfshark",),
    "Windscribe": ("windscribe",),
    "CyberGhost": ("cyberghost",),
    "Private Internet Access": ("private internet access", "pia vpn", "pia-client"),
    "PureVPN": ("purevpn",),
    "IVPN": ("ivpn",),
    "Tailscale": ("tailscale",),
    "ZeroTier": ("zerotier",),
    "OpenVPN": ("openvpn",),
    "WireGuard": ("wireguard",),
    "TunnelBear": ("tunnelbear",),
    "Hotspot Shield": ("hotspot shield", "hotspotshield"),
    "Hide.me": ("hide.me", "hideme"),
    "VyprVPN": ("vyprvpn",),
    "Mozilla VPN": ("mozilla vpn", "mozillavpn"),
}


def command_output(*arguments: str, timeout: int = 4) -> str:
    try:
        return subprocess.run(
            list(arguments), text=True, capture_output=True, timeout=timeout,
            check=False, env={**os.environ, "LC_ALL": "C"},
        ).stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def active_vpn_descriptions() -> list[str]:
    active: list[str] = []
    nm = run_nmcli(
        "-t", "--escape", "yes", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active",
        timeout=5,
    ).stdout
    for line in nm.splitlines():
        fields = split_escaped(line)
        if len(fields) >= 2 and fields[1] in {"vpn", "wireguard"}:
            active.append(fields[0])
    nord = command_output("nordvpn", "status")
    if "Status: Connected" in nord:
        detail = []
        for key in ("Country", "City", "Server"):
            match = re.search(rf"^{key}:\s*(.+)$", nord, re.MULTILINE)
            if match:
                detail.append(match.group(1).strip())
        active.append("NordVPN" + (" · " + ", ".join(detail[:2]) if detail else ""))
    warp = command_output("warp-cli", "status")
    if re.search(r"\bConnected\b", warp, re.IGNORECASE):
        active.append("Cloudflare WARP")
    # Preserve order while removing provider/profile duplicates.
    return list(dict.fromkeys(active))


def installed_vpn_apps() -> list[dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for app in Gio.AppInfo.get_all():
        if not app.should_show() or not app.get_id():
            continue
        haystack = " ".join(
            filter(None, (app.get_id(), app.get_name(), app.get_description(), app.get_executable()))
        ).casefold()
        for provider, keywords in VPN_KEYWORDS.items():
            if any(keyword in haystack for keyword in keywords):
                found.setdefault(provider, {"name": provider, "app": app})
                break
    # NetworkManager profiles have no dedicated GUI app, but remain manageable
    # through Debian's connection editor and therefore still appear here.
    profiles = run_nmcli("-t", "--escape", "yes", "-f", "NAME,TYPE", "connection", "show", timeout=5).stdout
    for line in profiles.splitlines():
        fields = split_escaped(line)
        if len(fields) >= 2 and fields[1] in {"vpn", "wireguard"}:
            found.setdefault(fields[0], {"name": fields[0], "app": None})
    return sorted(found.values(), key=lambda item: str(item["name"]).casefold())[:20]


COUNTRY_LOCATIONS = {
    "spain": ("España", "ES", 40.4, -3.7),
    "united states": ("Estados Unidos", "US", 39.8, -98.6),
    "united kingdom": ("Reino Unido", "GB", 54.0, -2.0),
    "germany": ("Alemania", "DE", 51.2, 10.4),
    "france": ("Francia", "FR", 46.2, 2.2),
    "netherlands": ("Países Bajos", "NL", 52.2, 5.3),
    "switzerland": ("Suiza", "CH", 46.8, 8.2),
    "sweden": ("Suecia", "SE", 62.0, 15.0),
    "norway": ("Noruega", "NO", 61.0, 8.0),
    "finland": ("Finlandia", "FI", 64.0, 26.0),
    "denmark": ("Dinamarca", "DK", 56.0, 10.0),
    "poland": ("Polonia", "PL", 52.0, 19.0),
    "italy": ("Italia", "IT", 42.8, 12.8),
    "portugal": ("Portugal", "PT", 39.6, -8.0),
    "canada": ("Canadá", "CA", 56.1, -106.3),
    "mexico": ("México", "MX", 23.6, -102.5),
    "brazil": ("Brasil", "BR", -10.3, -53.2),
    "argentina": ("Argentina", "AR", -38.4, -63.6),
    "chile": ("Chile", "CL", -33.4, -70.7),
    "japan": ("Japón", "JP", 36.2, 138.3),
    "singapore": ("Singapur", "SG", 1.35, 103.8),
    "australia": ("Australia", "AU", -25.3, 133.8),
    "india": ("India", "IN", 22.6, 79.0),
    "hong kong": ("Hong Kong", "HK", 22.3, 114.2),
    "romania": ("Rumanía", "RO", 45.9, 24.9),
    "austria": ("Austria", "AT", 47.5, 14.6),
    "belgium": ("Bélgica", "BE", 50.5, 4.5),
    "czechia": ("Chequia", "CZ", 49.8, 15.5),
    "ireland": ("Irlanda", "IE", 53.1, -8.2),
    "iceland": ("Islandia", "IS", 65.0, -19.0),
    "turkey": ("Turquía", "TR", 39.0, 35.0),
    "israel": ("Israel", "IL", 31.0, 35.0),
    "south africa": ("Sudáfrica", "ZA", -30.6, 22.9),
}


def provider_location(active: list[str]) -> dict[str, object]:
    """Infer a coarse map point from provider-reported/profile text locally."""
    description = " | ".join(active)
    folded = description.casefold()
    for english, (display, code, latitude, longitude) in COUNTRY_LOCATIONS.items():
        code_match = re.search(rf"(?:^|[-_ #]){re.escape(code)}(?:$|[-_ #0-9])", description, re.I)
        if english in folded or code_match:
            city = ""
            if "NordVPN ·" in description and "," in description:
                city = description.rsplit(",", 1)[-1].strip()
            return {
                "city": city, "region": "", "country": display,
                "latitude": latitude, "longitude": longitude,
            }
    return {}


def run_nmcli(
    *arguments: str,
    timeout: int = 20,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        environment = os.environ.copy()
        environment["LC_ALL"] = "C"
        return subprocess.run(
            ["nmcli", *arguments], text=True, capture_output=True,
            input=input_text, timeout=timeout, check=False, env=environment,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(["nmcli", *arguments], 1, "", str(error))


def split_escaped(line: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    fields.append("".join(current))
    return fields


def wifi_device() -> str | None:
    output = run_nmcli("-t", "-f", "DEVICE,TYPE", "device", "status", timeout=4).stdout
    for line in output.splitlines():
        fields = split_escaped(line)
        if len(fields) >= 2 and fields[1] == "wifi" and not fields[0].startswith("p2p-"):
            return fields[0]
    return None


def wifi_enabled() -> bool:
    return run_nmcli("radio", "wifi", timeout=4).stdout.strip() == "enabled"


def wired_connection() -> tuple[str, str] | None:
    output = run_nmcli(
        "-t", "--escape", "yes", "-f", "DEVICE,TYPE,STATE,CONNECTION",
        "device", "status", timeout=4,
    ).stdout
    for line in output.splitlines():
        fields = split_escaped(line)
        if len(fields) >= 4 and fields[1] == "ethernet" and fields[2].startswith("connected"):
            return fields[0], fields[3]
    return None


def current_ssid() -> str:
    output = run_nmcli(
        "-t", "--escape", "yes", "-f", "ACTIVE,SSID", "device", "wifi", "list",
        "--rescan", "no", timeout=5,
    ).stdout
    for line in output.splitlines():
        fields = split_escaped(line)
        if len(fields) >= 2 and fields[0] == "yes":
            return fields[1]
    return ""


def visible_networks() -> list[dict[str, object]]:
    output = run_nmcli(
        "-t", "--escape", "yes", "-f", "IN-USE,SSID,SIGNAL,SECURITY",
        "device", "wifi", "list", "--rescan", "no", timeout=6,
    ).stdout
    networks: dict[str, dict[str, object]] = {}
    for line in output.splitlines():
        fields = split_escaped(line)
        if len(fields) < 4 or not fields[1]:
            continue
        active, ssid, signal_value, security = fields[:4]
        try:
            strength = int(signal_value)
        except ValueError:
            strength = 0
        candidate = {
            "active": active.strip() == "*",
            "ssid": ssid,
            "signal": strength,
            "security": security.strip(),
        }
        previous = networks.get(ssid)
        if previous is None or bool(candidate["active"]) or strength > int(previous["signal"]):
            networks[ssid] = candidate
    return sorted(
        networks.values(),
        key=lambda network: (not bool(network["active"]), -int(network["signal"]), str(network["ssid"]).lower()),
    )


def saved_profiles() -> dict[str, str]:
    profiles: dict[str, str] = {}
    output = run_nmcli("-t", "-f", "UUID,TYPE", "connection", "show", timeout=5).stdout
    for line in output.splitlines():
        fields = split_escaped(line)
        if len(fields) < 2 or fields[1] != "802-11-wireless":
            continue
        uuid = fields[0]
        detail = run_nmcli(
            "-g", "connection.id,802-11-wireless.ssid", "connection", "show", uuid,
            timeout=4,
        ).stdout.splitlines()
        if len(detail) >= 2 and detail[1]:
            profiles[detail[1]] = uuid
    return profiles


def signal_icon(strength: int) -> str:
    if strength >= 75:
        return "󰤨"
    if strength >= 50:
        return "󰤥"
    if strength >= 25:
        return "󰤢"
    return "󰤟"


class WifiPopup(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.busy = False
        self.pending_network: dict[str, object] | None = None
        self.set_title("Red BSPWM")
        self.set_name("wifi-window")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(True)
        self.set_focus_on_map(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_size_request(480, -1)
        self.vpn_refresh_id = 0

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
        card.set_name("wifi-card")
        self.add(card)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title = Gtk.Label(label="Red", xalign=0)
        title.set_name("title")
        self.subtitle = Gtk.Label(xalign=0)
        self.subtitle.set_name("subtitle")
        title_box.pack_start(title, False, False, 0)
        title_box.pack_start(self.subtitle, False, False, 0)
        wifi_control = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        wifi_label = Gtk.Label(label="Wi-Fi")
        wifi_label.set_name("status")
        self.power_switch = Gtk.Switch()
        self.power_switch.set_valign(Gtk.Align.CENTER)
        self.power_switch.connect("notify::active", self._power_changed)
        wifi_control.pack_start(wifi_label, False, False, 0)
        wifi_control.pack_start(self.power_switch, False, False, 0)
        header.pack_start(title_box, True, True, 0)
        header.pack_end(wifi_control, False, False, 0)
        card.pack_start(header, False, False, 0)
        card.pack_start(Gtk.Separator(), False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(140)
        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self.stack)
        switcher.set_halign(Gtk.Align.CENTER)
        switcher.get_style_context().add_class("tab-switcher")
        card.pack_start(switcher, False, False, 0)

        network_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.stack.add_titled(network_page, "network", "Red")

        self.network_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(190)
        scroll.set_max_content_height(390)
        scroll.add(self.network_box)
        network_page.pack_start(scroll, True, True, 0)

        self.password_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.password_box.get_style_context().add_class("password-box")
        self.password_label = Gtk.Label(xalign=0)
        self.password_label.get_style_context().add_class("network-name")
        self.password_entry = Gtk.Entry()
        self.password_entry.set_visibility(False)
        self.password_entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.password_entry.set_placeholder_text("Contraseña de la red")
        self.password_entry.get_style_context().add_class("password-entry")
        self.password_entry.connect("activate", self._password_connect)
        password_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        connect_button = self._action_button("Conectar", True)
        connect_button.connect("clicked", self._password_connect)
        cancel_button = self._action_button("Cancelar", False)
        cancel_button.connect("clicked", self._cancel_password)
        password_actions.pack_start(connect_button, True, True, 0)
        password_actions.pack_start(cancel_button, True, True, 0)
        self.password_box.pack_start(self.password_label, False, False, 0)
        self.password_box.pack_start(self.password_entry, False, False, 0)
        self.password_box.pack_start(password_actions, False, False, 0)
        network_page.pack_start(self.password_box, False, False, 0)
        self.password_box.set_no_show_all(True)
        self.password_box.hide()

        self.status = Gtk.Label(xalign=0)
        self.status.set_name("status")
        self.status.set_line_wrap(True)
        network_page.pack_start(self.status, False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.scan_button = self._action_button("Actualizar redes", True)
        self.scan_button.connect("clicked", self._rescan)
        settings = self._action_button("Abrir configuración", False)
        settings.connect("clicked", self._open_settings)
        actions.pack_start(self.scan_button, True, True, 0)
        actions.pack_start(settings, True, True, 0)
        network_page.pack_start(actions, False, False, 0)

        self.vpn_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        self.stack.add_titled(self.vpn_page, "vpn", "VPN")
        self._build_vpn_page()
        card.pack_start(self.stack, True, True, 0)
        self.stack.connect("notify::visible-child-name", self._tab_changed)

        self.connect("key-press-event", self._on_key)
        install_click_outside(self)
        self.connect("delete-event", lambda *_args: Gtk.main_quit())
        self.refresh()
        GLib.timeout_add(200, self._initial_rescan)

    def _build_vpn_page(self) -> None:
        summary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        summary.get_style_context().add_class("vpn-summary")
        summary_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.vpn_title = Gtk.Label(label="Comprobando conexiones VPN…", xalign=0)
        self.vpn_title.get_style_context().add_class("network-name")
        self.vpn_spinner = Gtk.Spinner()
        self.vpn_spinner.get_style_context().add_class("vpn-loading")
        self.vpn_location = Gtk.Label(label="", xalign=0)
        self.vpn_location.set_line_wrap(True)
        self.vpn_location.get_style_context().add_class("network-state")
        summary_header.pack_start(self.vpn_title, True, True, 0)
        summary_header.pack_end(self.vpn_spinner, False, False, 0)
        summary.pack_start(summary_header, False, False, 0)
        summary.pack_start(self.vpn_location, False, False, 0)
        self.vpn_page.pack_start(summary, False, False, 0)

        self.vpn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(150)
        scroll.set_max_content_height(285)
        scroll.add(self.vpn_box)
        self.vpn_page.pack_start(scroll, True, True, 0)
        refresh = self._action_button("Actualizar estado", True)
        refresh.connect("clicked", lambda _button: self.refresh_vpn())
        self.vpn_page.pack_start(refresh, False, False, 0)

    def _tab_changed(self, _stack, _param) -> None:
        if self.stack.get_visible_child_name() == "vpn":
            self.refresh_vpn()

    def refresh_vpn(self) -> None:
        self.vpn_refresh_id += 1
        refresh_id = self.vpn_refresh_id
        self.vpn_title.set_text("Comprobando conexiones VPN…")
        self.vpn_location.set_text("Actualizando proveedor y ubicación de salida…")
        self.vpn_spinner.show()
        self.vpn_spinner.start()

        def worker() -> None:
            apps = installed_vpn_apps()
            active = active_vpn_descriptions()
            location = provider_location(active) if active else {}
            GLib.idle_add(self._render_vpn, refresh_id, apps, active, location)

        threading.Thread(target=worker, daemon=True).start()

    def _render_vpn(
        self, refresh_id: int, apps: list[dict[str, object]], active: list[str],
        location: dict[str, object],
    ) -> bool:
        if refresh_id != self.vpn_refresh_id:
            return False
        self.vpn_spinner.stop()
        self.vpn_spinner.hide()
        for child in self.vpn_box.get_children():
            self.vpn_box.remove(child)
        active_text = " · ".join(active)
        self.vpn_title.set_text(
            f"Conectada: {active_text}" if active else "Ninguna VPN activa"
        )
        self.vpn_title.get_style_context().remove_class("vpn-active")
        self.vpn_title.get_style_context().remove_class("vpn-offline")
        self.vpn_title.get_style_context().add_class("vpn-active" if active else "vpn-offline")
        place = ", ".join(
            str(location.get(field)) for field in ("city", "region", "country") if location.get(field)
        )
        self.vpn_location.set_text(
            f"Salida a Internet: {place}" if place else
            ("Ubicación no disponible" if active else "Activa una VPN para ver su ubicación de salida")
        )
        for provider in apps:
            name = str(provider["name"])
            app = provider.get("app")
            is_active = any(name.casefold() in item.casefold() or item.casefold() in name.casefold() for item in active)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.get_style_context().add_class("vpn-row")
            icon_name = "network-vpn-symbolic"
            if app and app.get_icon():
                icon_name = app.get_icon().to_string()
            icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DND)
            icon.set_pixel_size(24)
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            label = Gtk.Label(label=name, xalign=0)
            label.get_style_context().add_class("network-name")
            state = Gtk.Label(label="Conectada" if is_active else "Desconectada", xalign=0)
            state.get_style_context().add_class("vpn-active" if is_active else "vpn-offline")
            labels.pack_start(label, False, False, 0)
            labels.pack_start(state, False, False, 0)
            open_button = self._action_button("Abrir", False)
            open_button.connect("clicked", self._open_vpn_app, app)
            row.pack_start(icon, False, False, 0)
            row.pack_start(labels, True, True, 0)
            row.pack_end(open_button, False, False, 0)
            self.vpn_box.pack_start(row, False, False, 0)
        if not apps:
            empty = Gtk.Label(label="No se detectaron aplicaciones ni perfiles VPN", xalign=0)
            empty.set_name("status")
            empty.set_margin_top(18)
            empty.set_margin_bottom(18)
            self.vpn_box.pack_start(empty, False, False, 0)
        self.vpn_box.show_all()
        return False

    def _open_vpn_app(self, _button: Gtk.Button, app: Gio.AppInfo | None) -> None:
        Gtk.main_quit()
        try:
            if app:
                app.launch([], None)
            else:
                subprocess.Popen(
                    ["nm-connection-editor"], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True,
                )
        except GLib.Error:
            pass

    def _action_button(self, text: str, primary: bool) -> Gtk.Button:
        button = Gtk.Button(label=text)
        context = button.get_style_context()
        context.add_class("action-button")
        if primary:
            context.add_class("primary")
        return button

    def refresh(self) -> bool:
        enabled = wifi_enabled()
        ethernet = wired_connection()
        self.power_switch.handler_block_by_func(self._power_changed)
        self.power_switch.set_active(enabled)
        self.power_switch.handler_unblock_by_func(self._power_changed)
        active_ssid = current_ssid() if enabled else ""
        if ethernet:
            _device, connection_name = ethernet
            suffix = f" · Wi-Fi: {active_ssid}" if active_ssid else ""
            self.subtitle.set_text(f"Ethernet: {connection_name}{suffix}")
        elif not enabled:
            self.subtitle.set_text("Adaptador apagado")
        elif active_ssid:
            self.subtitle.set_text(f"Conectada a {active_ssid}")
        else:
            self.subtitle.set_text("Sin conexión")

        for child in self.network_box.get_children():
            self.network_box.remove(child)
        networks = visible_networks() if enabled else []
        profiles = saved_profiles() if enabled else {}
        for network in networks:
            self.network_box.pack_start(self._network_row(network, profiles), False, False, 0)
        if enabled and not networks:
            empty = Gtk.Label(label="No se encontraron redes", xalign=0)
            empty.set_name("status")
            empty.set_margin_top(24)
            empty.set_margin_bottom(24)
            self.network_box.pack_start(empty, False, False, 0)
        self.status.set_text(
            "Selecciona una red para conectarte" if enabled
            else "Activa el adaptador para buscar redes"
        )
        self.scan_button.set_sensitive(enabled and not self.busy)
        self.network_box.show_all()
        return False

    def _network_row(self, network: dict[str, object], profiles: dict[str, str]) -> Gtk.Button:
        ssid = str(network["ssid"])
        strength = int(network["signal"])
        security = str(network["security"])
        active = bool(network["active"])
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.get_style_context().add_class("network-row")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon = Gtk.Label(label=signal_icon(strength))
        icon.get_style_context().add_class("network-icon")
        if active:
            icon.get_style_context().add_class("connected")
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        name_label = Gtk.Label(label=ssid, xalign=0)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.get_style_context().add_class("network-name")
        if active:
            state = f"Conectada · {strength}% · pulsa para desconectar"
        else:
            known = "Guardada" if ssid in profiles else ("Abierta" if not security or security == "--" else "Protegida")
            state = f"{known} · señal {strength}%"
        state_label = Gtk.Label(label=state, xalign=0)
        state_label.get_style_context().add_class("network-state")
        labels.pack_start(name_label, False, False, 0)
        labels.pack_start(state_label, False, False, 0)
        row.pack_start(icon, False, False, 0)
        row.pack_start(labels, True, True, 0)
        if security and security != "--":
            lock = Gtk.Label(label="")
            lock.get_style_context().add_class("network-state")
            row.pack_end(lock, False, False, 0)
        button.add(row)
        button.connect("clicked", self._network_clicked, network, profiles.get(ssid))
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

    def _network_clicked(self, _button: Gtk.Button, network: dict[str, object], profile_uuid: str | None) -> None:
        ssid = str(network["ssid"])
        if bool(network["active"]):
            device = wifi_device()
            if device:
                self._background(
                    lambda: self._result_error(run_nmcli("device", "disconnect", device, timeout=15), "No se pudo desconectar"),
                    "Desconectando…",
                )
            return
        if profile_uuid:
            device = wifi_device()
            self._background(
                lambda: self._result_error(
                    run_nmcli("--wait", "25", "connection", "up", "uuid", profile_uuid, "ifname", device or "*", timeout=30),
                    "No se pudo conectar a la red guardada",
                ),
                f"Conectando a {ssid}…",
            )
            return
        security = str(network["security"])
        if security and security != "--":
            self.pending_network = network
            self.password_label.set_text(f"Contraseña para {ssid}")
            self.password_entry.set_text("")
            self.password_box.set_no_show_all(False)
            self.password_box.show_all()
            self.password_entry.grab_focus()
            return
        self._connect_new(network, "")

    def _connect_new(self, network: dict[str, object], password: str) -> None:
        ssid = str(network["ssid"])
        device = wifi_device()

        def operation() -> str | None:
            arguments = ["--wait", "25"]
            if password:
                # --ask consumes the secret over stdin, keeping it out of the
                # process list and shell history.
                arguments.append("--ask")
            arguments.extend(["device", "wifi", "connect", ssid])
            if device:
                arguments.extend(["ifname", device])
            result = run_nmcli(
                *arguments, timeout=30,
                input_text=f"{password}\n" if password else None,
            )
            return self._result_error(result, "No se pudo conectar. Comprueba la contraseña")

        self._background(operation, f"Conectando a {ssid}…")

    @staticmethod
    def _result_error(result: subprocess.CompletedProcess[str], message: str) -> str | None:
        return None if result.returncode == 0 else message

    def _password_connect(self, _widget) -> None:
        if self.pending_network is None:
            return
        password = self.password_entry.get_text()
        if not password:
            self.status.set_text("Escribe la contraseña de la red")
            return
        network = self.pending_network
        self.pending_network = None
        self.password_entry.set_text("")
        self.password_box.hide()
        self._connect_new(network, password)

    def _cancel_password(self, _button: Gtk.Button) -> None:
        self.pending_network = None
        self.password_entry.set_text("")
        self.password_box.hide()

    def _initial_rescan(self) -> bool:
        if wifi_enabled() and not self.busy:
            self._rescan(None)
        return False

    def _rescan(self, _button: Gtk.Button | None) -> None:
        device = wifi_device()
        if not device:
            self.status.set_text("No se encontró un adaptador Wi-Fi")
            return

        def operation() -> str | None:
            result = run_nmcli(
                "--wait", "15", "device", "wifi", "list",
                "ifname", device, "--rescan", "yes", timeout=20,
            )
            return self._result_error(result, "No se pudo actualizar la lista de redes")

        self._background(operation, "Buscando redes cercanas…")

    def _power_changed(self, switch: Gtk.Switch, _param) -> None:
        desired = "on" if switch.get_active() else "off"
        self._background(
            lambda: self._result_error(run_nmcli("radio", "wifi", desired, timeout=12), "No se pudo cambiar el estado del Wi-Fi"),
            "Actualizando adaptador…",
        )

    def _open_settings(self, _button: Gtk.Button) -> None:
        subprocess.Popen(
            ["gnome-control-center", "network"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        Gtk.main_quit()

    def _on_key(self, _widget: Gtk.Widget, event: Gdk.EventKey) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            if self.password_box.get_visible():
                self._cancel_password(Gtk.Button())
            else:
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
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()))
    lock.flush()
    return lock


def main() -> int:
    lock = acquire_lock()
    if lock is None:
        return 0
    window = WifiPopup()
    window.show_all()
    window.password_box.hide()
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor()
    geometry = monitor.get_geometry()
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)
    width, _height = window.get_size()
    window.move(geometry.x + geometry.width - width - 16, geometry.y + 48)
    window.present()
    Gtk.main()
    window.password_entry.set_text("")
    window.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
