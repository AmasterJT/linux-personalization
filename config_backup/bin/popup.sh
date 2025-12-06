#!/usr/bin/env bash

# Lanza la aplicación pasada como argumento
"$@" &
app_pid=$!

# Espera a que bspwm gestione la ventana (la que se enfoca tras lanzar la app)
while :; do
  popup_node=$(bspc query -N -n focused.local.window 2>/dev/null) && break
  sleep 0.1
done

# Opcional: hacerla flotante y centrarla (tipo popup)
bspc node "$popup_node" -t floating
bspc node "$popup_node" -g center

# Cuando pierda el foco, se cierra
bspc subscribe node_focus | while read -r _ wid _; do
  # Si el foco va a otra ventana distinta del popup: cerrar y salir
  if [ "$wid" != "$popup_node" ]; then
    bspc node "$popup_node" -c
    break
  fi
done
