#!/usr/bin/env sh

## Add this to your wm startup file.

# Terminate already running bar instances
killall -q polybar

## Wait until the processes have been shut down
while pgrep -u $UID -x polybar >/dev/null; do sleep 1; done

## Launch

## Left bar
polybar log -c ~/.config/polybar/current.ini &     # system logo, flies, firefox
polybar primary -c ~/.config/polybar/current.ini & # fecha y hora

polybar terciary -c ~/.config/polybar/current.ini & # spotify

## Right bar
polybar systemStats -c ~/.config/polybar/current.ini & # cpu, ram
polybar systemConfig -c ~/.config/polybar/current.ini &  # mute volumen, wifi, battery, settings
polybar systemTurnOFF -c ~/.config/polybar/current.ini & # power/log ...

## Center bar
polybar workspace -c ~/.config/polybar/workspace.ini &
