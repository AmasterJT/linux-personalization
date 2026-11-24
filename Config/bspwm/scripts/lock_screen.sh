#!/usr/bin/env sh

# xss-lock backend for BSPWM. Keep the logind session locked while Debian's GDM
# greeter is visible; no painted-over i3lock screen is used.

has_gdm_backend() {
    command -v loginctl >/dev/null 2>&1 \
        && { command -v gdbus >/dev/null 2>&1 \
            || command -v gdmflexiserver >/dev/null 2>&1; }
}

if [ "${1:-}" = "--check" ]; then
    has_gdm_backend
    exit $?
fi

has_gdm_backend || {
    printf '%s\n' 'GDM is not available; refusing to show an insecure fake lock screen.' >&2
    exit 1
}

external_power_online() {
    mains_found=false
    for supply in /sys/class/power_supply/*; do
        [ -r "$supply/type" ] && [ -r "$supply/online" ] || continue
        type=$(cat "$supply/type" 2>/dev/null || true)
        [ "$type" = Mains ] || continue
        mains_found=true
        [ "$(cat "$supply/online" 2>/dev/null || printf 0)" = 1 ] && return 0
    done
    [ "$mains_found" = true ] && return 1
    for supply in /sys/class/power_supply/*; do
        [ -r "$supply/type" ] && [ -r "$supply/online" ] || continue
        type=$(cat "$supply/type" 2>/dev/null || true)
        case "$type" in USB|USB_C|USB_PD)
            [ "$(cat "$supply/online" 2>/dev/null || printf 0)" = 1 ] && return 0;;
        esac
    done
    return 1
}

lid_is_closed() {
    for state in /proc/acpi/button/lid/*/state; do
        [ -r "$state" ] || continue
        grep -qi 'closed' "$state" && return 0
    done
    return 1
}

release_sleep_lock() {
    fd=${XSS_SLEEP_LOCK_FD:-}
    case "$fd" in
        ''|*[!0-9]*) ;;
        *)
            if [ -e "/proc/$$/fd/$fd" ]; then
                eval "exec ${fd}<&-"
            fi
            ;;
    esac
}

# The AC lid inhibitor normally prevents this invocation altogether. This
# guard covers the small charger/connect race without ever showing a greeter.
if external_power_online && lid_is_closed; then
    release_sleep_lock
    exit 0
fi

runtime_dir=${XDG_RUNTIME_DIR:-/tmp/runtime-$(id -u)}
mkdir -p "$runtime_dir"
lock_file="$runtime_dir/linux-personalization-screen-lock.lock"
exec 9>"$lock_file"
if command -v flock >/dev/null 2>&1; then
    flock -n 9 || exit 0
fi

session_id=${XDG_SESSION_ID:-}
if [ -z "$session_id" ]; then
    session_id=$(loginctl list-sessions --no-legend 2>/dev/null \
        | awk -v uid="$(id -u)" '$2 == uid && $4 == "seat0" && $6 == "user" {print $1; exit}')
fi
[ -n "$session_id" ] || exit 1

activate_gdm_greeter() {
    candidate=""
    for candidate in $(loginctl list-sessions --no-legend 2>/dev/null | awk '{print $1}'); do
        properties=$(loginctl show-session "$candidate" \
            -p Class -p Seat -p State 2>/dev/null || true)
        if printf '%s\n' "$properties" | grep -qx 'Class=greeter' \
                && printf '%s\n' "$properties" | grep -qx 'Seat=seat0' \
                && ! printf '%s\n' "$properties" | grep -qx 'State=closing'; then
            loginctl activate "$candidate" >/dev/null 2>&1
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

    gdmflexiserver >/dev/null 2>&1 || true
}

# Direct invocations also mark the logind session as locked. When xss-lock
# started this process the property is already set, so this is a no-op.
if [ "$(loginctl show-session "$session_id" -p LockedHint --value 2>/dev/null)" != yes ]; then
    loginctl lock-session "$session_id" >/dev/null 2>&1 || true
fi

activate_gdm_greeter || exit 1

# xss-lock transfers logind's delay inhibitor through this descriptor. Release
# it only after GDM accepted the switch, allowing lid-close suspension to begin
# with the greeter already in front of the BSPWM session.
sleep_lock_fd=${XSS_SLEEP_LOCK_FD:-}
case "$sleep_lock_fd" in
    ''|*[!0-9]*) ;;
    *)
        if [ -e "/proc/$$/fd/$sleep_lock_fd" ]; then
            eval "exec ${sleep_lock_fd}<&-"
        fi
        ;;
esac
unset sleep_lock_fd

stop_waiting() {
    exit 0
}
trap stop_waiting HUP INT TERM

# Remain in the foreground for xss-lock. GDM clears LockedHint after successful
# authentication; returning then completes the normal xss-lock lifecycle.
while [ "$(loginctl show-session "$session_id" -p LockedHint --value 2>/dev/null)" = yes ]; do
    sleep 0.25
done
