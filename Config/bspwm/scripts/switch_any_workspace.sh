#!/bin/bash

# Obtén la lista de todos los espacios de trabajo en el monitor actual
desktops=$(bspc query -D -m focused)

# Encuentra el espacio de trabajo actual
current=$(bspc query -D -d focused)

# Encuentra el siguiente espacio de trabajo en la lista
next_desktop=$(echo $desktops | awk -v current=$current '{for (i=1; i<=NF; i++) if ($i == current) {print $(i%NF+1); exit}}')

# Cambia al siguiente espacio de trabajo
bspc desktop -f $next_desktop
