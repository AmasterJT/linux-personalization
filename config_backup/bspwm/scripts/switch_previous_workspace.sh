#!/bin/bash

# Obtén la lista de todos los espacios de trabajo en el monitor actual
desktops=$(bspc query -D -m focused)

# Encuentra el espacio de trabajo actual
current=$(bspc query -D -d focused)

# Encuentra el espacio de trabajo anterior en la lista
previous_desktop=$(echo $desktops | awk -v current=$current '{for (i=1; i<=NF; i++) if ($i == current) {print $(i==1?NF:i-1); exit}}')

# Verifica si el espacio de trabajo anterior está en uso
while [ -z "$(bspc query -N -d $previous_desktop)" ]; do
    # Si no está en uso, busca el anterior
    previous_desktop=$(echo $desktops | awk -v current=$previous_desktop '{for (i=1; i<=NF; i++) if ($i == current) {print $(i==1?NF:i-1); exit}}')
    # Si volvemos al primer espacio, salimos del bucle para evitar un bucle infinito
    if [ "$previous_desktop" == "$current" ]; then
        break
    fi
done

# Cambia al espacio de trabajo anterior
bspc desktop -f $previous_desktop
