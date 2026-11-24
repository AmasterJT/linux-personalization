#!/usr/bin/env sh

# BSPWM briefly restores its default pointer-following behaviour while it is
# restarting. Preserve the cursor position around the reload so it never jumps
# to the newly focused window.
set -u

XDOTOOL_BIN=$(command -v xdotool 2>/dev/null || true)
if [ -z "$XDOTOOL_BIN" ] && [ -x "$HOME/.local/bin/xdotool" ]; then
    XDOTOOL_BIN="$HOME/.local/bin/xdotool"
fi

if [ -z "$XDOTOOL_BIN" ]; then
    exec bspc wm -r
fi

pointer=$($XDOTOOL_BIN getmouselocation --shell)
pointer_x=$(printf '%s\n' "$pointer" | sed -n 's/^X=//p')
pointer_y=$(printf '%s\n' "$pointer" | sed -n 's/^Y=//p')

bspc wm -r

# The new BSPWM process executes bspwmrc synchronously, so a short wait is
# enough for its initial focus event to finish before restoring the cursor.
sleep 0.15
$XDOTOOL_BIN mousemove "$pointer_x" "$pointer_y"
