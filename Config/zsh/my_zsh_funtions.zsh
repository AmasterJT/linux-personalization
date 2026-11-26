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


#--------------------------------------------------------------------------------------------------
# Función: check_vpn
# Descripción: Detecta si WARP, Proton VPN o Nord VPN están activos y muestra la ubicación/región externa.
# Uso: check_vpn
#--------------------------------------------------------------------------------------------------
check_vpn () {
        local warp_status="off"
        local proton_status="off"
        local nord_status="off"

        # 1. Cloudflare WARP
        if command -v warp-cli &> /dev/null
        then
                if warp-cli status 2> /dev/null | grep -q "Connected"
                then
                        warp_status="on"
                fi
        fi

        # 2. Proton VPN
        if ip link show | grep -E "(pvpn|proton)" &> /dev/null
        then
                proton_status="on"
        elif command -v protonvpn-cli &> /dev/null && protonvpn-cli status 2> /dev/null | grep -q "Status: Connected"
        then
                proton_status="on"
        fi

        # 3. NordVPN (CLI + interfaces nordlynx / nordtun)
        if command -v nordvpn &> /dev/null && nordvpn status 2> /dev/null | grep -q "Status: Connected"
        then
                nord_status="on"
        elif ip link show | grep -E "(nordlynx|nordtun)" &> /dev/null
        then
                nord_status="on"
        fi

        echo -e "${BLUE}[+] Estado de los servicios VPN:${RESET}"
        if [[ "$warp_status" == "on" ]]
        then
                echo -e "  ${CYAN}Cloudflare WARP:${RESET} ${GREEN}▲ ENCENDIDO${RESET}"
        else
                echo -e "  ${CYAN}Cloudflare WARP:${RESET} ${RED}▼ APAGADO${RESET}"
        fi

        if [[ "$proton_status" == "on" ]]
        then
                echo -e "  ${PURPLE}Proton VPN:${RESET}      ${GREEN}▲ ENCENDIDO${RESET}"
        else
                echo -e "  ${PURPLE}Proton VPN:${RESET}      ${RED}▼ APAGADO${RESET}"
        fi

        if [[ "$nord_status" == "on" ]]
        then
                echo -e "  ${BLUE}NordVPN:${RESET}         ${GREEN}▲ ENCENDIDO${RESET}"
        else
                echo -e "  ${BLUE}NordVPN:${RESET}         ${RED}▼ APAGADO${RESET}"
        fi

        echo -e "\n${BLUE}[+] Geolocalización de la IP de salida:${RESET}"
        if command -v jq &> /dev/null
        then
                local location=$(curl -s --max-time 5 https://ifconfig.co/json | jq -r '"\(.country), \(.time_zone)"')
                echo -e "  ${YELLOW}Ubicación:${RESET} ${WHITE}$location${RESET}\n"
        else
                local country=$(curl -s --max-time 5 https://ifconfig.co/country)
                echo -e "  ${YELLOW}País:${RESET} ${WHITE}$country ${RED}(Instala 'jq' para ver la región/zona horaria)${RESET}\n"
        fi
}



#--------------------------------------------------------------------------------------------------
# Función: system_info
# Descripción: Muestra una lista limpia y completa del software, hardware y red sin logotipos.
# Uso: system_info [opciones_extra_fastfetch]
#--------------------------------------------------------------------------------------------------
function system_info(){
    # Validar si el binario existe para evitar errores silenciosos o caídas del script
    if ! command -v fastfetch &> /dev/null; then
        local RED='\033[0;31m'
        local RESET='\033[0m'
        echo -e "${RED}[!] Error: 'fastfetch' no está instalado en el sistema.${RESET}"
        return 1
    fi

    # Definir estructura fija de la lista limpia de manera organizada
    local structure="Title:Separator:OS:Host:Kernel:Uptime:Packages:Shell:Display:DE:WM:WMTheme:Theme:Icons:Font:Cursor:Terminal:TerminalFont:CPU:GPU:Memory:Swap:Disk:LocalIp:Locale"

    # Ejecutar fastfetch. Los "$@" permiten añadirle parámetros dinámicos sobre la marcha si lo deseas.
    fastfetch -l none -s "$structure" "$@"
}


#--------------------------------------------------------------------------------------------------
# Función: reboot_open_bios
# Descripción: Reinicia el sistema y abre directamente la configuración de firmware BIOS/UEFI.
# Uso: reboot_open_bios
#--------------------------------------------------------------------------------------------------
function reboot_open_bios(){
    # Verificar si systemctl está disponible
    if ! command -v systemctl &> /dev/null; then
        echo -e "${RED}[!] Error: 'systemctl' no está disponible en este sistema.${RESET}"
        return 1
    fi

    # Verificar si el sistema arrancó en modo UEFI
    if [[ ! -d /sys/firmware/efi ]]; then
        echo -e "${RED}[!] Error: este sistema no parece haber arrancado en modo UEFI.${RESET}"
        echo -e "${YELLOW}[!] La opción '--firmware-setup' solo funciona con firmware UEFI.${RESET}"
        return 1
    fi

    # Verificar si systemd permite reiniciar hacia la configuración del firmware
    if ! systemctl reboot --help 2>/dev/null | grep -q -- '--firmware-setup'; then
        echo -e "${RED}[!] Error: tu versión de systemctl no parece soportar '--firmware-setup'.${RESET}"
        return 1
    fi

    # Confirmación compatible con Bash y Zsh
    echo -e "${YELLOW}[!] El sistema se reiniciará y abrirá la configuración BIOS/UEFI.${RESET}"
    printf "¿Quieres continuar? [s/N]: "
    read confirmacion

    case "$confirmacion" in
        s|S|si|SI|sí|SÍ)
            echo -e "${GREEN}[+] Reiniciando hacia BIOS/UEFI...${RESET}"
            sleep 1

            # Intentar sin sudo primero; si no hay permisos, usar sudo
            if systemctl reboot --firmware-setup 2>/dev/null; then
                return 0
            else
                sudo systemctl reboot --firmware-setup
            fi
            ;;
        *)
            echo -e "${CYAN}[+] Operación cancelada.${RESET}"
            return 0
            ;;
    esac
}


#--------------------------------------------------------------------------------------------------
# Función: sandbox
# Descripción: Ejecuta una aplicación con Firejail en un directorio personal temporal.
#              Firefox se abre en una instancia independiente y usa Firefox ESR si hace falta.
# Uso: sandbox <aplicación> [argumentos...]
#--------------------------------------------------------------------------------------------------
function sandbox() {
    if (( $# == 0 )); then
        print -u2 -- 'Uso: sandbox <aplicación> [argumentos...]'
        return 2
    fi
    if ! (( $+commands[firejail] )); then
        print -u2 -- 'Falta Firejail. Instala: sudo apt install firejail firejail-profiles'
        return 127
    fi
    local app="$1"
    shift
    if [[ "$app" == firefox ]] && ! (( $+commands[firefox] )) && (( $+commands[firefox-esr] )); then
        app=firefox-esr
    fi
    case "${app:t}" in
        firefox|firefox-esr)
            command firejail --private "$app" --no-remote "$@"
            ;;
        *)
            command firejail --private "$app" "$@"
            ;;
    esac
}


#--------------------------------------------------------------------------------------------------
# Función: proteger-terminal
# Descripción: Activa o desactiva la protección de la ventana enfocada frente al cierre
#              normal de BSPWM (Super+W) y confirma el cambio en la terminal.
# Uso: proteger-terminal {on|off|-h|--help}
#--------------------------------------------------------------------------------------------------
function proteger-terminal() {
    if (( $# == 1 )) && [[ $1 == -h || $1 == --help ]]; then
        print -r -- 'Uso: proteger-terminal {on|off}'
        print -r -- '  on        Impide cerrar la ventana enfocada con Super+W.'
        print -r -- '  off       Vuelve a permitir el cierre normal.'
        print -r -- '  -h, --help  Muestra esta ayuda.'
        print -r -- 'Ejecuta el comando desde la terminal que quieras proteger.'
        return 0
    fi

    if (( $# != 1 )) || [[ $1 != on && $1 != off ]]; then
        print -u2 -r -- 'Uso: proteger-terminal {on|off|--help}'
        return 2
    fi

    if ! command -v bspc >/dev/null 2>&1; then
        print -u2 -r -- 'No se encontró bspc. Este comando requiere BSPWM.'
        return 1
    fi

    if ! command bspc node focused.window -g "locked=$1"; then
        print -u2 -r -- 'No se pudo cambiar la protección. Comprueba que estés en BSPWM y haya una ventana enfocada.'
        return 1
    fi

    if [[ $1 == on ]]; then
        print -r -- 'Protección activada. Super+W no cerrará esta ventana.'
    else
        print -r -- 'Protección desactivada. Ya puedes cerrar esta ventana con Super+W.'
    fi
}


#--------------------------------------------------------------------------------------------------
# Función: proteger-pestana-tmux
# Descripción: Activa o desactiva la protección del Zsh del panel actual de tmux
#              frente a Ctrl+D en el prompt vacío y confirma el cambio.
# Uso: proteger-pestana-tmux {on|off|-h|--help}
#--------------------------------------------------------------------------------------------------
function proteger-pestana-tmux() {
    if (( $# == 1 )) && [[ $1 == -h || $1 == --help ]]; then
        print -r -- 'Uso: proteger-pestana-tmux {on|off}'
        print -r -- '  on          Protege el panel actual frente a Ctrl+D en el prompt vacío.'
        print -r -- '  off         Restaura el comportamiento habitual de Ctrl+D.'
        print -r -- '  -h, --help  Muestra esta ayuda.'
        print -r -- 'Ejecuta el comando en cada panel de tmux que quieras proteger.'
        return 0
    fi

    if (( $# != 1 )) || [[ $1 != on && $1 != off ]]; then
        print -u2 -r -- 'Uso: proteger-pestana-tmux {on|off|--help}'
        return 2
    fi

    if [[ -z ${TMUX:-} || -z ${TMUX_PANE:-} ]]; then
        print -u2 -r -- 'Ejecuta este comando dentro de un panel de tmux.'
        return 1
    fi

    if [[ $1 == on ]]; then
        setopt IGNORE_EOF
        print -r -- 'Protección activada en este panel de tmux.'
    else
        unsetopt IGNORE_EOF
        print -r -- 'Protección desactivada en este panel de tmux.'
    fi
}
