#!/usr/bin/env bash

# Keep all Polybar windows behind BSPWM fullscreen clients. Event-driven
# updates avoid polling and also handle desktop/monitor changes.
set -u

PID_FILE="${XDG_RUNTIME_DIR:-/tmp}/bspwm-polybar-fullscreen.pid"

cleanup_pid_file() {
    if [ -r "$PID_FILE" ] && [ "$(cat "$PID_FILE")" = "$$" ]; then
        unlink "$PID_FILE" 2>/dev/null || true
    fi
}

terminate() {
    cleanup_pid_file
    exit 0
}

replace_previous_watcher() {
    local old_pid=""
    local command_line=""

    if [ -r "$PID_FILE" ]; then
        old_pid=$(cat "$PID_FILE")
    fi

    case "$old_pid" in
        ''|*[!0-9]*) ;;
        *)
            if [ -r "/proc/$old_pid/cmdline" ]; then
                command_line=$(tr '\0' ' ' < "/proc/$old_pid/cmdline")
                case "$command_line" in
                    *"$0"*) kill "$old_pid" 2>/dev/null || true ;;
                esac
            fi
            ;;
    esac

    printf '%s\n' "$$" > "$PID_FILE"
    trap cleanup_pid_file EXIT
    trap terminate INT TERM
}

bar_command() {
    local command=$1
    local pid

    while read -r pid; do
        [ -n "$pid" ] || continue
        polybar-msg -p "$pid" cmd "$command" >/dev/null 2>&1 || true
    done < <(pgrep -x polybar || true)
}

sync_visibility() {
    local command="show"

    if bspc query -N -d focused -n '.fullscreen.window' 2>/dev/null | grep -q .; then
        command="hide"
    fi

    if [ "$command" != "${last_command:-}" ]; then
        bar_command "$command"
        last_command=$command
    fi
}

last_command=""
sync_visibility

if [ "${1:-}" = "--once" ]; then
    exit 0
fi

if [ "${1:-}" = "--replace" ]; then
    replace_previous_watcher
fi

while read -r _event; do
    sync_visibility
done < <(bspc subscribe node_state node_focus node_add node_remove desktop_focus monitor_focus)
