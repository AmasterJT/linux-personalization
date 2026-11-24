#!/usr/bin/env sh

# Present Debian's real GDM greeter while xss-lock keeps the BSPWM logind
# session marked as locked underneath. No i3lock surface is displayed.
backend="$HOME/.config/bspwm/scripts/lock_screen.sh"

if [ "${1:-}" = "--check" ]; then
    command -v loginctl >/dev/null 2>&1
    command -v gdbus >/dev/null 2>&1 || command -v gdmflexiserver >/dev/null 2>&1
    [ -x "$backend" ]
    "$backend" --check
    exit $?
fi

activate_gdm_greeter() {
    # Reuse an existing greeter when possible. Otherwise ask GDM to create the
    # same transient login display used internally by gdmflexiserver.
    for candidate in $(loginctl list-sessions --no-legend 2>/dev/null | awk '{print $1}'); do
        properties=$(loginctl show-session "$candidate" \
            -p Class -p Seat -p State 2>/dev/null || true)
        if printf '%s\n' "$properties" | grep -qx 'Class=greeter' \
                && printf '%s\n' "$properties" | grep -qx 'Seat=seat0' \
                && ! printf '%s\n' "$properties" | grep -qx 'State=closing'; then
            loginctl activate "$candidate"
            return $?
        fi
    done

    if command -v gdbus >/dev/null 2>&1; then
        gdbus call --system \
            --dest org.gnome.DisplayManager \
            --object-path /org/gnome/DisplayManager/LocalDisplayFactory \
            --method org.gnome.DisplayManager.LocalDisplayFactory.CreateTransientDisplay \
            >/dev/null 2>&1
        return $?
    fi

    command -v gdmflexiserver >/dev/null 2>&1 || return 1
    # gdmflexiserver returns 1 even after a successful switch in GDM 48.
    gdmflexiserver >/dev/null 2>&1 || true
}

runtime_dir=${XDG_RUNTIME_DIR:-/tmp/runtime-$(id -u)}
mkdir -p "$runtime_dir"
request_lock="$runtime_dir/linux-personalization-gdm-lock.lock"
exec 8>"$request_lock"
if command -v flock >/dev/null 2>&1; then
    flock -n 8 || exit 0
fi

session_id=${XDG_SESSION_ID:-}
if [ -z "$session_id" ]; then
    session_id=$(loginctl list-sessions --no-legend 2>/dev/null \
        | awk -v uid="$(id -u)" '$2 == uid && $4 == "seat0" {print $1; exit}')
fi

if [ -n "$session_id" ] \
        && pgrep -u "$(id -u)" -x xss-lock >/dev/null 2>&1 \
        && loginctl lock-session "$session_id"; then
    locked=false
    attempts=0
    while [ "$attempts" -lt 50 ]; do
        if [ "$(loginctl show-session "$session_id" -p LockedHint --value 2>/dev/null)" = yes ]; then
            locked=true
            break
        fi
        attempts=$((attempts + 1))
        sleep 0.05
    done

    if [ "$locked" = true ]; then
        activate_gdm_greeter && exit 0
    fi
fi

# Direct fallback when the logind/xss-lock bridge is unavailable. The backend
# itself uses GDM and refuses to substitute a cosmetic lock screen.
exec "$backend"
