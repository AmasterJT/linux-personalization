#!/usr/bin/env sh

# Apply per-session libinput preferences without requiring a system-wide Xorg
# configuration. Device names are discovered dynamically.
set -u

XINPUT_BIN=$(command -v xinput 2>/dev/null || true)
if [ -z "$XINPUT_BIN" ] && [ -x "$HOME/.local/bin/xinput" ]; then
    XINPUT_BIN="$HOME/.local/bin/xinput"
fi
[ -n "$XINPUT_BIN" ] || exit 0

"$XINPUT_BIN" list --name-only | while IFS= read -r device; do
    case "$device" in
        *Touchpad*|*touchpad*|*Trackpad*|*trackpad*)
            "$XINPUT_BIN" set-prop "$device" 'libinput Tapping Enabled' 1 2>/dev/null || true
            "$XINPUT_BIN" set-prop "$device" 'libinput Tapping Drag Enabled' 1 2>/dev/null || true
            "$XINPUT_BIN" set-prop "$device" 'libinput Natural Scrolling Enabled' 1 2>/dev/null || true
            ;;
    esac
done
