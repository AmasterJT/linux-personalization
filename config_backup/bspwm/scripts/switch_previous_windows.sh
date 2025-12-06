#!/bin/bash

# Obtener el monitor y escritorio actual
current_monitor=$(bspc query -M -m focused)
current_desktop=$(bspc query -D -d focused)

# Obtener la lista de ventanas en el escritorio actual
windows=$(bspc query -N -n .window --desktop "$current_desktop")

# Obtener la ventana enfocada actualmente
current_window=$(bspc query -N -n focused)

# Convertir la lista de ventanas en un array
windows_array=($windows)

# Buscar la posición de la ventana enfocada actualmente en el array
current_index=-1
for i in "${!windows_array[@]}"; do
    if [ "${windows_array[$i]}" == "$current_window" ]; then
        current_index=$i
        break
    fi
done

# Calcular el índice de la ventana anterior
if [ $current_index -ge 0 ]; then
    previous_index=$(( (current_index - 1 + ${#windows_array[@]}) % ${#windows_array[@]} ))
    # Enfocar la ventana anterior
    bspc node -f "${windows_array[$previous_index]}"
else
    # En caso de no encontrar la ventana actual, enfocar la primera ventana
    bspc node -f "${windows_array[0]}"
fi
