#!/bin/bash

# Define el nombre de la polybar que deseas controlar
POLYBAR_NAME="main"

# Verifica el estado de las ventanas cada cierto intervalo
while true; do
  # Comprueba si alguna ventana está en fullscreen
  fullscreen=$(xprop -root _NET_ACTIVE_WINDOW | grep -o "0x[0-9a-fA-F]*")
  if [ -n "$fullscreen" ]; then
    state=$(xprop -id "$fullscreen" _NET_WM_STATE | grep _NET_WM_STATE_FULLSCREEN)
    if [ -n "$state" ]; then
      # Oculta la polybar si una ventana está en fullscreen
      polybar-msg cmd hide
    else
      # Muestra la polybar si no hay ventanas en fullscreen
      polybar-msg cmd show
    fi
  else
    # Muestra la polybar si no hay ventanas activas
    polybar-msg cmd show
  fi
  # Espera un segundo antes de la siguiente verificación
  sleep 1
done
