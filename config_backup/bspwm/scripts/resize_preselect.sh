#!/bin/bash

# Incremento de tamaño
increment=30

# Dirección del ajuste
direction=$1

case $direction in
    left)
        bspc node -z left -$increment 0
        ;;
    right)
        bspc node -z right $increment 0
        ;;
    up)
        bspc node -z top 0 -$increment
        ;;
    down)
        bspc node -z bottom 0 $increment
        ;;
    *)
        echo "Dirección desconocida: $direction"
        exit 1
        ;;
esac
