#!/bin/bash

# Colores para los diferentes estados de la conexión
WIRED_COLOR="#43A047"            # Verde para conexión por cable (Ethernet)
WIFI_COLOR="#1E88E5"             # Azul para conexión por Wi-Fi
NO_INTERNET_CONECTION="#F6CF59"  # Amarillo para cuando no hay conexión a Internet
DISCONNECTED_COLOR="#757575"     # Gris para desconectado

# Iconos para los diferentes estados de la conexión
WIRED_ICON=""            # Icono para conexión por cable (Ethernet)
WIFI_ICON=""             # Icono para conexión por Wi-Fi
DISCONNECTED_ICON=""     # Icono para desconectado

# Verificar el estado de la conexión con nmcli
# nmcli lista los dispositivos de red y su estado.
# grep filtra los dispositivos que están "connected".
# awk filtra para excluir las interfaces loopback y obtiene el tipo de conexión.
CONNECTION_TYPE=$(nmcli -t -f TYPE,STATE device | grep ":connected" | awk -F: '$1 != "loopback" {print $1}')

# Función para verificar la conexión a Internet
# Argumentos:
#   $1 - Color a usar para el icono si hay conexión a Internet
#   $2 - Icono a mostrar
check_internet_connection() {
    # Realiza un ping a 8.8.8.8 (servidor DNS de Google) para verificar la conectividad a Internet
    if ping -q -c 1 -W 1 8.8.8.8 > /dev/null; then
        # Si hay conexión a Internet, muestra el icono con el color correspondiente
        echo "%{F$1}$2%{F-}"
    else
        # Si no hay conexión a Internet, muestra el icono en gris (sin conexión)
        echo "%{F$NO_INTERNET_CONECTION}$2%{F-}"
    fi
}

# Comprobar el tipo de conexión y llamar a la función check_internet_connection con los parámetros adecuados
if [ "$CONNECTION_TYPE" = "ethernet" ]; then
    # Si la conexión es por cable (Ethernet), usa el color y el icono de Ethernet
    check_internet_connection "$WIRED_COLOR" "$WIRED_ICON"
elif [ "$CONNECTION_TYPE" = "wifi" ]; then
    # Si la conexión es por Wi-Fi, usa el color y el icono de Wi-Fi
    check_internet_connection "$WIFI_COLOR" "$WIFI_ICON"
else
    # Si no hay conexión (ni Ethernet ni Wi-Fi), muestra el icono de desconectado en amarillo
    ICON_SELECTED=$DISCONNECTED_ICON
    ICON_COLOR=$DISCONNECTED_COLOR
    echo "%{F$ICON_COLOR}$ICON_SELECTED%{F-}"
fi
