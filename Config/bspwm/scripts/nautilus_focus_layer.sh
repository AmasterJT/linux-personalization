#!/usr/bin/env bash

# Lower unfocused Nautilus windows behind tiled clients and restore their
# normal layer as soon as they receive focus again.
set -u

PID_FILE="${XDG_RUNTIME_DIR:-/tmp}/bspwm-nautilus-focus-layer.pid"

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

is_nautilus() {
    local node=$1
    local window_class

    window_class=$(xprop -id "$node" WM_CLASS 2>/dev/null || true)
    [[ "$window_class" == *'"org.gnome.Nautilus"'* ]]
}

sync_layers() {
    local focused=""
    local node=""
    local tree=""
    local state=""
    local current_layer=""
    local target_layer=""

    focused=$(bspc query -N -n focused.window 2>/dev/null || true)

    while read -r node; do
        [ -n "$node" ] || continue
        is_nautilus "$node" || continue

        tree=$(bspc query -T -n "$node" 2>/dev/null || true)
        [ -n "$tree" ] || continue
        state=$(jq -r '.client.state // ""' <<<"$tree")
        [ "$state" = "floating" ] || continue
        current_layer=$(jq -r '.client.layer // ""' <<<"$tree")

        target_layer="below"
        [ "$node" = "$focused" ] && target_layer="normal"
        if [ "$current_layer" != "$target_layer" ]; then
            bspc node "$node" -l "$target_layer" >/dev/null 2>&1 || true
        fi
    done < <(bspc query -N -n .window 2>/dev/null || true)
}

sync_layers

if [ "${1:-}" = "--once" ]; then
    exit 0
fi

if [ "${1:-}" = "--replace" ]; then
    replace_previous_watcher
fi

while read -r _event; do
    sync_layers
done < <(bspc subscribe node_focus node_add node_remove node_state desktop_focus monitor_focus)
