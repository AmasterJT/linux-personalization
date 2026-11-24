#!/usr/bin/env sh

# Keep the laptop awake and unlocked when its lid is closed while external
# power is present. logind resumes its normal lid/suspend policy immediately
# after the charger is disconnected.

set -u

inhibitor_pid=""

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
    # Machines without a dedicated Mains device may expose USB-PD as USB.
    for supply in /sys/class/power_supply/*; do
        [ -r "$supply/type" ] && [ -r "$supply/online" ] || continue
        type=$(cat "$supply/type" 2>/dev/null || true)
        case "$type" in USB|USB_C|USB_PD)
            [ "$(cat "$supply/online" 2>/dev/null || printf 0)" = 1 ] && return 0;;
        esac
    done
    return 1
}

stop_inhibitor() {
    if [ -n "$inhibitor_pid" ]; then
        kill "$inhibitor_pid" 2>/dev/null || true
        wait "$inhibitor_pid" 2>/dev/null || true
        inhibitor_pid=""
    fi
}

cleanup() {
    trap - HUP INT TERM EXIT
    stop_inhibitor
    exit 0
}
trap cleanup HUP INT TERM EXIT

while :; do
    if external_power_online; then
        if [ -z "$inhibitor_pid" ] || ! kill -0 "$inhibitor_pid" 2>/dev/null; then
            systemd-inhibit \
                --what=handle-lid-switch \
                --who="BSPWM lid policy" \
                --why="Use an external monitor while connected to power" \
                --mode=block \
                sleep infinity &
            inhibitor_pid=$!
        fi
    else
        stop_inhibitor
    fi
    sleep 2
done
