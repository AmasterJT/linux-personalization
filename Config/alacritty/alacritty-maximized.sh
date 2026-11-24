#!/usr/bin/env bash

# Launch a new Alacritty window with a font size suited to the active session.
# This is a per-process override: it does not modify already-open terminals or
# rewrite alacritty.toml.
set -euo pipefail

BSPWM_FONT_SIZE="${ALACRITTY_BSPWM_FONT_SIZE:-7.0}"
GNOME_FONT_SIZE="${ALACRITTY_GNOME_FONT_SIZE:-10.0}"
DEFAULT_FONT_SIZE="${ALACRITTY_DEFAULT_FONT_SIZE:-10.0}"

desktop="${XDG_CURRENT_DESKTOP:-${XDG_SESSION_DESKTOP:-${DESKTOP_SESSION:-}}}"
desktop="${desktop,,}"

# BSPWM_SOCKET/bspc are more reliable than desktop variables inherited by a
# panel that may have been started by a display manager.
if [ -n "${BSPWM_SOCKET:-}" ] && command -v bspc >/dev/null 2>&1 \
        && bspc query -M >/dev/null 2>&1; then
    desktop="bspwm"
fi

case "$desktop" in
    *bspwm*) font_size="$BSPWM_FONT_SIZE" ;;
    *gnome*) font_size="$GNOME_FONT_SIZE" ;;
    *)       font_size="$DEFAULT_FONT_SIZE" ;;
esac

exec /usr/bin/alacritty \
    --option 'window.startup_mode="Maximized"' \
    --option "font.size=$font_size" \
    "$@"
