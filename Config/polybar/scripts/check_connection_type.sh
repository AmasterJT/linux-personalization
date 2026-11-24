#!/usr/bin/env bash

# NetworkManager is the source of truth. Unlike the old implementation, this
# ignores Docker/VMware bridges and does not assume that public ICMP is allowed.
set -u

WIRED_COLOR="#43A047"
WIFI_COLOR="#1E88E5"
LIMITED_COLOR="#F6CF59"
DISCONNECTED_COLOR="#757575"

# Material Design's cable glyph remains legible at the compact Polybar size.
WIRED_ICON="󰌘"
WIFI_ICON=""
DISCONNECTED_ICON=""

if ! command -v nmcli >/dev/null 2>&1; then
    printf '%%{F%s}%s%%{F-}\n' "$DISCONNECTED_COLOR" "$DISCONNECTED_ICON"
    exit 0
fi

devices=$(LC_ALL=C nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null || true)
wifi_device=$(printf '%s\n' "$devices" | awk -F: '$2 == "wifi" && $3 ~ /^connected/ {print $1; exit}')
wired_device=$(printf '%s\n' "$devices" | awk -F: '$2 == "ethernet" && $3 ~ /^connected/ {print $1; exit}')
connectivity=$(LC_ALL=C nmcli -t -f CONNECTIVITY general 2>/dev/null || printf 'unknown')

color_for_connection() {
    if [ "$connectivity" = "full" ]; then
        printf '%s' "$1"
    else
        printf '%s' "$LIMITED_COLOR"
    fi
}

# Prefer the wired route when both adapters are connected: plugging in a cable
# should immediately replace the Wi-Fi glyph with the Ethernet glyph.
if [ -n "$wired_device" ]; then
    color=$(color_for_connection "$WIRED_COLOR")
    printf '%%{F%s}%s%%{F-}\n' "$color" "$WIRED_ICON"
elif [ -n "$wifi_device" ]; then
    color=$(color_for_connection "$WIFI_COLOR")
    printf '%%{F%s}%s%%{F-}\n' "$color" "$WIFI_ICON"
else
    printf '%%{F%s}%s%%{F-}\n' "$DISCONNECTED_COLOR" "$DISCONNECTED_ICON"
fi
