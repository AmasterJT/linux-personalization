#!/usr/bin/env sh

set -u

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/polybar"
LOG_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/polybar"
mkdir -p "$LOG_DIR"

# Terminate already running bar instances
killall -q polybar 2>/dev/null || true

## Wait until the processes have been shut down
while pgrep -u "$(id -u)" -x polybar >/dev/null; do sleep 1; done

launch_bar() {
    bar=$1
    config=$2
    nohup polybar "$bar" -c "$config" >"$LOG_DIR/$bar.log" 2>&1 &
}

## Launch

## Left bar
launch_bar log "$CONFIG_DIR/current.ini"
launch_bar primary "$CONFIG_DIR/current.ini"

launch_bar terciary "$CONFIG_DIR/current.ini"

## Right bar
launch_bar systemStats "$CONFIG_DIR/current.ini"
launch_bar systemConfig "$CONFIG_DIR/current.ini"
launch_bar systemTurnOFF "$CONFIG_DIR/current.ini"

## Center bar
launch_bar workspace "$CONFIG_DIR/workspace.ini"

# A BSPWM reload can replace all Polybar processes while a window is already
# fullscreen. Re-apply the current visibility state after IPC is ready.
FULLSCREEN_WATCHER="${XDG_CONFIG_HOME:-$HOME/.config}/bspwm/scripts/hide_polybar_fullscreen.sh"
if [ -x "$FULLSCREEN_WATCHER" ]; then
    (sleep 0.5; "$FULLSCREEN_WATCHER" --once) &
fi
