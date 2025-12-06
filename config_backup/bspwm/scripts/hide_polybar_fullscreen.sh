#!/bin/bash

# Nombre del monitor polybar (ajusta esto con el nombre correcto de tu barra)
POLYBAR_NAME="$1" # Reemplaza con el nombre de tu barra

# Función para ocultar la polybar
hide_polybar() {
    #echo "Ocultando Polybar $POLYBAR_NAME"

    polybar-msg -p $(pgrep -f "polybar $POLYBAR_NAME") cmd hide
}

# Función para mostrar la polybar
show_polybar() {
    #echo "Mostrando Polybar $POLYBAR_NAME"
    polybar-msg -p $(pgrep -f "polybar $POLYBAR_NAME") cmd show
}

# Bucle infinito para comprobar ventanas en pantalla completa
while true; do
    # Obtener la ID de la ventana en foco
    WINDOW_ID=$(xdotool getactivewindow)
    #echo "ID de la ventana en foco: $WINDOW_ID"

    # Obtener el estado de la ventana
    WINDOW_STATE=$(xprop -id $WINDOW_ID | grep "_NET_WM_STATE_FULLSCREEN")
    #echo "Estado de la ventana: $WINDOW_STATE"

    # Si la ventana está en pantalla completa, oculta la polybar
    if [ -n "$WINDOW_STATE" ]; then
        hide_polybar
    else
        show_polybar
    fi

    # Esperar un segundo antes de comprobar de nuevo
    sleep 1
done
