#!/usr/bin/env bash

# Keep the floating window being used on the normal layer and lower every
# inactive floating window. This makes floating applications behave like
# ordinary loose windows instead of permanently covering tiled clients.
set -u

PID_FILE="${XDG_RUNTIME_DIR:-/tmp}/bspwm-floating-window-layers.pid"

cleanup_pid_file() {
    if [ -r "$PID_FILE" ] && [ "$(cat "$PID_FILE")" = "$$" ]; then
        unlink "$PID_FILE" 2>/dev/null || true
    fi
}

replace_existing() {
    local old_pid=""
    if [ -r "$PID_FILE" ]; then
        old_pid=$(cat "$PID_FILE" 2>/dev/null || true)
    fi
    case "$old_pid" in
        ''|*[!0-9]*) ;;
        *)
            if [ "$old_pid" != "$$" ] && kill -0 "$old_pid" 2>/dev/null; then
                kill "$old_pid" 2>/dev/null || true
                for _attempt in {1..20}; do
                    kill -0 "$old_pid" 2>/dev/null || break
                    sleep 0.05
                done
            fi
            ;;
    esac
}

if [ "${1:-}" = "--replace" ]; then
    replace_existing
fi

mkdir -p "$(dirname "$PID_FILE")"
printf '%s\n' "$$" >"$PID_FILE"
trap cleanup_pid_file EXIT HUP INT TERM

sync_layers() {
    local focused=""
    local node=""
    local tree=""
    local state=""
    local current_layer=""
    local target_layer=""

    focused=$(bspc query -N -n focused.window 2>/dev/null || true)

    while IFS= read -r node; do
        [ -n "$node" ] || continue
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

command -v bspc >/dev/null 2>&1 || exit 1
command -v jq >/dev/null 2>&1 || exit 1

while read -r _event; do
    sync_layers
done < <(bspc subscribe node_focus node_add node_remove node_state desktop_focus monitor_focus)
