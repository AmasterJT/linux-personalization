#!/usr/bin/env sh

# Small, dependency-free status icon for the Polybar Bluetooth module.
set -u

icon=''
if ! command -v bluetoothctl >/dev/null 2>&1; then
    printf '%%{F#5b5f6f}%s%%{F-}\n' "$icon"
    exit 0
fi

controller=$(bluetoothctl show 2>/dev/null || true)
if ! printf '%s\n' "$controller" | grep -q 'Powered: yes'; then
    printf '%%{F#5b5f6f}%s%%{F-}\n' "$icon"
elif bluetoothctl devices Connected 2>/dev/null | grep -q '^Device '; then
    printf '%%{F#1e88e5}%s%%{F-}\n' "$icon"
else
    printf '%%{F#c5c8d3}%s%%{F-}\n' "$icon"
fi
