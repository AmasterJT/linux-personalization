#!/bin/sh

# Alacritty closes when its child exits. Keep a protected X11 window usable
# by starting a fresh tmux session after the current client exits normally.
window_id=
case "${WINDOWID:-}" in
    ''|*[!0-9]*) ;;
    *) window_id=$(printf '0x%X' "$WINDOWID" 2>/dev/null) || window_id= ;;
esac

while :; do
    tmux new-session || exit "$?"
    if [ -z "$window_id" ] || ! bspc query -N -n "$window_id.locked.window" >/dev/null 2>&1; then
        exit 0
    fi
    printf '%s\n' 'La terminal está protegida. Se abrirá una sesión nueva de tmux.'
done
