#!/usr/bin/env sh

# This file is sourced by bspwmrc so its exports reach SXHKD, Polybar and every
# application launched from them. GNOME never sources it.
export XDG_CURRENT_DESKTOP=bspwm
export XDG_SESSION_DESKTOP=bspwm
export DESKTOP_SESSION=bspwm
export GTK_THEME=Adwaita:dark
export GTK2_RC_FILES=/usr/share/themes/Adwaita-dark/gtk-2.0/gtkrc
export QT_QPA_PLATFORMTHEME=gtk3
export XCURSOR_THEME=breeze_cursors
export XCURSOR_SIZE=24

# Update the per-session D-Bus activation environment without persisting these
# overrides in the user systemd manager used by GNOME sessions.
if command -v dbus-update-activation-environment >/dev/null 2>&1; then
    dbus-update-activation-environment \
        DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP DESKTOP_SESSION \
        GTK_THEME GTK2_RC_FILES QT_QPA_PLATFORMTHEME XCURSOR_THEME XCURSOR_SIZE \
        >/dev/null 2>&1 || true
fi

XSETTINGSD_CONFIG="$HOME/.config/bspwm/xsettingsd.conf"
if command -v xsettingsd >/dev/null 2>&1 \
        && [ -r "$XSETTINGSD_CONFIG" ] \
        && ! pgrep -x xsettingsd >/dev/null 2>&1; then
    if command -v setsid >/dev/null 2>&1; then
        setsid -f xsettingsd --config="$XSETTINGSD_CONFIG" >/dev/null 2>&1
    else
        nohup xsettingsd --config="$XSETTINGSD_CONFIG" >/dev/null 2>&1 &
    fi
fi

unset XSETTINGSD_CONFIG
