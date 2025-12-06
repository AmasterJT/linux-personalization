#!/bin/bash

#--------------------------------------------------------------------------------------------------
# Descripción: Gestiona notas en la terminal, permitiendo crear, abrir y eliminar notas.
# Uso: note [-n] [-r] [-ra] [-h] [nombre_fichero]
# Parámetros:
#   -n   -> Crea un nuevo fichero con el formato "note[id]" (id incremental).
#   -r   -> Borra el último fichero creado.
#   -ra  -> Borra todos los ficheros en el directorio (pide confirmación).
#   -h   -> Muestra la ayuda sobre el uso del script.
#   [nombre_fichero] -> Abre un fichero específico (si existe, pregunta si sobrescribir).
#--------------------------------------------------------------------------------------------------

NOTES_DIR=~/Documentos/.notes

# Verificar si el directorio de notas existe, si no, crearlo
[[ ! -d "$NOTES_DIR" ]] && mkdir -p "$NOTES_DIR"

# Encontrar el último fichero con prefijo "note"
LATEST_NOTE=$(ls "$NOTES_DIR" | grep -E "^note[0-9]+$" | sort -V | tail -n 1)
LATEST_NOTE=${LATEST_NOTE:-0}

# Función para mostrar ayuda
function help() {
    echo "Uso: note [-n] [-r] [-ra] [-h] [nombre_fichero]"
    echo "Opciones:"
    echo "  -n   Crea una nueva nota con formato 'note[id]'."
    echo "  -r   Borra la última nota creada."
    echo "  -ra  Borra todas las notas (requiere confirmación)."
    echo "  -P   Muestra toas las notas creadas"
    echo "  -h   Muestra esta ayuda."
    echo "  [nombre_fichero] Abre un fichero específico (pregunta antes de sobrescribir si ya existe)."
    exit 0
}

# Capturar Ctrl+C y mostrar un mensaje antes de salir
trap ctrl_c INT

function ctrl_c(){
    echo -e "\nSaliendo de notes."
	exit 1
}

# Si se pasa la opción -h, mostrar la ayuda
if [[ "$1" == "-h" ]]; then
    help
fi

# Si se pasa un argumento con nombre de fichero
if [[ -n "$1" && "$1" != -*  && "$1" != "--"* ]]; then
    CUSTOM_NOTE="$NOTES_DIR/$1"
    if [[ -f "$CUSTOM_NOTE" ]]; then
        read -p "El fichero '$1' ya existe. ¿Deseas sobrescribirlo? (s/n): " confirm
        
        if [[ "$confirm" != "s" ]]; then
            nano "$CUSTOM_NOTE"
        else
            touch "$CUSTOM_NOTE"
            nano "$CUSTOM_NOTE"
        fi
    fi
    exit 0
fi

case "$1" in
    -n) 
        # Obtener el próximo ID disponible
        NEW_ID=1
        if [[ "$LATEST_NOTE" != "0" ]]; then
            LAST_ID=$(echo "$LATEST_NOTE" | grep -oE "[0-9]+$")
            NEW_ID=$((LAST_ID + 1))
        fi
        NEW_NOTE="$NOTES_DIR/note$NEW_ID"
        touch "$NEW_NOTE"
        nano "$NEW_NOTE"
        ;;
    
    -r)
        # Eliminar el último fichero creado
        if [[ "$LATEST_NOTE" != "0" ]]; then
            rm "$NOTES_DIR/$LATEST_NOTE"
            echo "Última nota eliminada: $LATEST_NOTE"
        else
            echo "No hay notas para eliminar."
        fi
        ;;
    
    -ra)
        # Confirmar antes de eliminar todas las notas
        read -p "¿Seguro que quieres eliminar todas las notas? (s/n): " confirm
        if [[ "$confirm" == "s" ]]; then
            rm -rf "$NOTES_DIR"/*
            echo "Todas las notas han sido eliminadas."
        fi
        ;;
        
    -P)
        tree "$NOTES_DIR"
        ;;
    
    *)
        # Si no se pasa un argumento, abrir la última nota creada
        if [[ "$LATEST_NOTE" != "0" ]]; then
            nano "$NOTES_DIR/$LATEST_NOTE"
        else
            echo $LATEST_NOTE
            NEW_ID=$(($LATEST_NOTE + 1))
            NEW_NOTE="$NOTES_DIR/note$NEW_ID"
            touch "$NEW_NOTE"
            echo "No hay notas disponibles. Usa 'note -n' para crear una nueva."
        fi
        ;;
esac
