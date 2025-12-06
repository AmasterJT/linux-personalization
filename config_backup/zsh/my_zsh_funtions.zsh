# Definición de colores para mejorar la visualización en la terminal
BLACK="\e[0;30m"
RED="\e[0;31m"
GREEN="\e[0;32m"
YELLOW="\e[0;33m"
BLUE="\e[0;34m"
PURPLE="\e[0;35m"
CYAN="\e[0;36m"
WHITE="\e[0;37m"
RESET="\e[0m"  # Para resetear colores después de usarlos


#==================================================================================================
#===================================== CUSTOM FUNCTIONS ===========================================
#==================================================================================================


#--------------------------------------------------------------------------------------------------
# Función: mkt
# Descripción: Crea una estructura de directorios comúnmente utilizada en pentesting o CTFs.
# Uso: mkt
#--------------------------------------------------------------------------------------------------
function mkt(){
    mkdir {nmap,content,exploits,scripts}  # Crea las carpetas nmap, content, exploits y scripts
}


#--------------------------------------------------------------------------------------------------
# Función: mkdoc
# Descripción: Crea una estructura de directorios para documentación y navega a la carpeta principal.
# Uso: mkdoc
#--------------------------------------------------------------------------------------------------
function mkdoc(){
    mkdir doc              # Crea el directorio principal 'doc'
    cd doc                 # Entra en el directorio 'doc'
    mkdir -p {imagenes/screenshots,config}  # Crea subdirectorios 'imagenes/screenshots' y 'config'
}


#--------------------------------------------------------------------------------------------------
# Función: extract_ports
# Descripción: Extrae información de puertos abiertos de un escaneo Nmap y los copia al portapapeles.
# Uso: extractPorts <archivo_nmap>
#--------------------------------------------------------------------------------------------------
function extract_ports(){
    # Extrae los puertos abiertos desde el archivo de salida de Nmap
    ports="$(cat $1 | grep -oP '\d{1,5}/open' | awk '{print $1}' FS='/' | xargs | tr ' ' ',')"
    
    # Extrae la dirección IP objetivo del escaneo
    ip_address="$(cat $1 | grep -oP '\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}' | sort -u | head -n 1)"
    
    # Imprime y guarda la información en un archivo temporal
    echo -e "\n[*] Extracting information...\n" > extractPorts.tmp
    echo -e "\t[*] IP Address: $ip_address"  >> extractPorts.tmp
    echo -e "\t[*] Open ports: $ports\n"  >> extractPorts.tmp
    
    # Copia los puertos al portapapeles
    echo $ports | tr -d '\n' | xclip -sel clip
    echo -e "[*] Ports copied to clipboard\n"  >> extractPorts.tmpX
    
    # Muestra el contenido y elimina el archivo temporal
    cat extractPorts.tmp; rm extractPorts.tmp
}

#--------------------------------------------------------------------------------------------------
# Función: set_target
# Descripción: Guarda una dirección IP y opcionalmente un nombre en un archivo de configuración.
# Uso: settarget [IP] [NAME]
#--------------------------------------------------------------------------------------------------
function set_target(){
    if [ $# -eq 1 ]; then
        echo $1 > ~/.config/bin/target
    elif [ $# -gt 2 ]; then
        echo "settarget [IP] [NAME] | settarget [IP]"
    else
        echo $1 $2 > ~/.config/bin/target
    fi
}

#--------------------------------------------------------------------------------------------------
# Función: man (modificada)
# Descripción: Aplica colores personalizados a la visualización del comando 'man'.
# Uso: man <comando>
#--------------------------------------------------------------------------------------------------
function man() {
    env \
    LESS_TERMCAP_mb=$'\e[01;31m' \
    LESS_TERMCAP_md=$'\e[01;31m' \
    LESS_TERMCAP_me=$'\e[0m' \
    LESS_TERMCAP_se=$'\e[0m' \
    LESS_TERMCAP_so=$'\e[01;44;33m' \
    LESS_TERMCAP_ue=$'\e[0m' \
    LESS_TERMCAP_us=$'\e[01;32m' \
    man "$@"
}

#--------------------------------------------------------------------------------------------------
# Función: fzf-fzf_hidden_file-file
# Descripción: Usa fzf para buscar archivos ocultos en el sistema.
# Uso: fzf-hidden-file
#--------------------------------------------------------------------------------------------------
function fzf_hidden_file(){
    find ~ -type f -name ".*" | fzf --exact 
}

#--------------------------------------------------------------------------------------------------
# Función: rmk
# Descripción: Elimina archivos de forma segura sobrescribiéndolos varias veces.
# Uso: rmk <archivo>
#--------------------------------------------------------------------------------------------------
function rmk(){
    scrub -p dod $1
    shred -zun 10 $1
}

#--------------------------------------------------------------------------------------------------
# Función: copy_path
# Descripción: Copia la ruta absoluta del directorio actual al portapapeles.
# Uso: copy_path
#--------------------------------------------------------------------------------------------------
function copy_path(){
    pwd 1>/dev/null 2>&1 | tr -d '\n' | xclip -selection clipboard
}

#--------------------------------------------------------------------------------------------------
# Función: copy_file_path
# Descripción: Copia la ruta absoluta de un archivo al portapapeles.
# Uso: copy_file_path <archivo>
#--------------------------------------------------------------------------------------------------
function copy_file_path() {
    if [[ -z "$1" ]]; then
        echo "Usage: copy_file_path <filename>"
        return 1
    fi

    local file_path=$(realpath "$1" 2>/dev/null)

    if [[ ! -f "$file_path" && ! -d "$file_path" ]]; then
        echo "File not found: $1"
        return 1
    fi

    echo -n "$file_path" | xclip -selection clipboard
    echo "Path copied to clipboard: $file_path"
}

#--------------------------------------------------------------------------------------------------
# Función: copy_file_content
# Descripción: Copia el contenido de un archivo al portapapeles.
# Uso: copy_file_content <archivo>
#--------------------------------------------------------------------------------------------------
function copy_file_content() {	
    if [ -f "$1" ]; then
        xclip -selection clipboard < "$1"
        echo "Contenido de $1 copiado al portapapeles."
    else
        echo "El archivo $1 no existe."
    fi
}

#--------------------------------------------------------------------------------------------------
# Función: reload_sxhkd
# Descripción: Reinicia el gestor de atajos de teclado sxhkd.
# Uso: reloadSxhkd
#--------------------------------------------------------------------------------------------------
function reload_sxhkd(){
    pkill -USR1 -x sxhkd
}

#--------------------------------------------------------------------------------------------------
# Función: select_theme_batCat
# Descripción: Permite seleccionar un tema para batcat (similar a cat pero con colores).
# Uso: selectThemeBatCat <archivo>
#--------------------------------------------------------------------------------------------------
function select_theme_batCat(){
    local filename="$1"
    if [[ -e "$filename" ]]; then
        local absolute_path=$(realpath "$filename")
        batcat --list-themes | fzf --preview="batcat --theme={} --color=always $absolute_path"
    else
        echo "El archivo $filename no existe en el directorio actual."
    fi
}

#--------------------------------------------------------------------------------------------------
# Función: show_battery_name
# Descripción: Muestra el nombre del dispositivo de batería en el sistema.
# Uso: showBatteryName
#--------------------------------------------------------------------------------------------------
function show_battery_name(){
    ls /sys/class/power_supply/
}

#--------------------------------------------------------------------------------------------------
# Función: show_repo_info
# Descripción: Muestra información detallada de un repositorio Git.
# Uso: show_repo_info
#--------------------------------------------------------------------------------------------------
function show_repo_info(){
    
    # Verificar si estamos en un repositorio Git
    repo_path=$(git rev-parse --show-toplevel 2>/dev/null)
    if [[ -z "$repo_path" ]]; then
        echo -e "${RED}Not inside a Git repository.${RESET}"
        return 1
    fi

    # Obtener el nombre del repositorio (directorio raíz del repo)
    repo_name=$(basename "$repo_path")

    # Obtener la URL del repositorio remoto (origin)
    repo_url=$(git remote get-url origin 2>/dev/null)

    # Obtener la rama actual
    branch_name=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

    # Obtener información del último commit
    last_commit_hash=$(git log -1 --format="%H" 2>/dev/null)          # Hash del último commit
    last_commit_author=$(git log -1 --format="%an" 2>/dev/null)       # Autor del último commit
    last_commit_date=$(git log -1 --format="%cd" --date=short 2>/dev/null)  # Fecha del último commit
    last_commit_message=$(git log -1 --format="%s" 2>/dev/null)       # Mensaje del último commit

    # Obtener la fecha de creación del repositorio (primer commit)
    repo_creation_date=$(git log --reverse --format=%cd --date=short | head -n 1)

    # Determinar el estado del repositorio
    git_status=$(git status --short)
    if [[ -z "$git_status" ]]; then
        repo_status="${GREEN}Clean${RESET}"  # No hay cambios sin confirmar
    else
        repo_status="${YELLOW}Modified${RESET}"  # Hay cambios sin confirmar
    fi

    # Mostrar la información recopilada
    echo -e "${CYAN}Repository Name: ${WHITE}$repo_name"
    echo -e "${CYAN}Repository URL: ${WHITE}${repo_url:-'No remote found'}"
    echo -e "${CYAN}Branch: ${WHITE}$branch_name"
    echo -e "${CYAN}Last Commit: ${WHITE}"
    echo -e "  ${YELLOW}Hash:${WHITE} $last_commit_hash"
    echo -e "  ${YELLOW}Author:${WHITE} $last_commit_author"
    echo -e "  ${YELLOW}Date:${WHITE} $last_commit_date"
    echo -e "  ${YELLOW}Message:${WHITE} $last_commit_message"
    echo -e "${CYAN}Repository Created On: ${WHITE}${repo_creation_date:-'Unknown'}"
    echo -e "${CYAN}Repository Status: ${WHITE}$repo_status"
}

