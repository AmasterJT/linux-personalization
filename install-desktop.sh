#!/bin/bash

# ------------------------------------------------------------
# Debian Personal Tools Installer
# GNOME / Wayland edition
#
# Objetivo:
# - Instalar herramientas y utilidades personales.
# - NO instalar bspwm, sxhkd, polybar ni picom.
# - NO compilar entorno gráfico ni compositor.
# - Copiar configuraciones existentes desde el repo.
# - Instalar .zshrc, .p10k.zsh, .tmux.conf, fuentes, wallpapers.
# - Preparado para Debian 12/13 con GNOME Wayland.
# ------------------------------------------------------------

set -euo pipefail

RUTA="$(dirname "$(readlink -f "$0")")"

error_exit() {
    echo -e "\n[ERROR] Ocurrió un error en la línea $1. Saliendo..."
    exit 1
}

trap 'error_exit $LINENO' ERR

run_step() {
    local msg="$1"
    shift
    echo -e "\n[INFO] $msg..."
    "$@"
    echo "[OK] $msg completado."
}

warn() {
    echo -e "[WARN] $*"
}

info() {
    echo -e "[INFO] $*"
}

ok() {
    echo -e "[OK] $*"
}

# ------------------------------------------------------------
# Comprobaciones iniciales
# ------------------------------------------------------------

if [ "$EUID" -eq 0 ]; then
    echo "[ERROR] No ejecutes este script como root. Usa tu usuario normal con sudo."
    exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
    echo "[ERROR] sudo no está instalado o no está disponible para este usuario."
    echo "Solución como root:"
    echo "  apt update"
    echo "  apt install sudo"
    echo "  usermod -aG sudo TU_USUARIO"
    exit 1
fi

if ! grep -qi "debian" /etc/os-release; then
    warn "Este script está pensado para Debian. Continuando igualmente..."
fi

info "Ruta del repo detectada: $RUTA"

# ------------------------------------------------------------
# Actualización base
# ------------------------------------------------------------

run_step "Actualizando índice de paquetes" sudo apt update

# ------------------------------------------------------------
# Paquetes base para Debian
# ------------------------------------------------------------
# Se eliminan explícitamente:
# - bspwm
# - sxhkd
# - polybar
# - picom
# - dependencias pesadas de compilación de polybar/picom
#
# Se mantienen herramientas útiles para GNOME/Wayland y terminal.

PAQUETES_BASE=(
    build-essential
    git
    curl
    wget
    ca-certificates
    gnupg
    apt-transport-https
    software-properties-common
    pkg-config
    cmake
    meson
    ninja-build
    make
    gcc
    g++
    python3
    python3-pip
    python3-venv
    unzip
    p7zip-full
    tar
    rsync
    locate
    file
    tree
    jq
    xclip
    wl-clipboard
    xsel
    fonts-powerline
    fontconfig
)

PAQUETES_TERMINAL=(
    zsh
    tmux
    vim
    nano
    bat
    htop
    btop
    lsd
    fzf
    ripgrep
    fd-find
    ranger
    mc
    neofetch
    fastfetch
    acpi
    wmname
    scrub
)

PAQUETES_APPS=(
    alacritty
    kitty
    rofi
    flameshot
    imagemagick
    pavucontrol
    nautilus
    gnome-tweaks
    gnome-shell-extension-manager
    gnome-browser-connector
)

PAQUETES_ZSH=(
    zsh-syntax-highlighting
    zsh-autosuggestions
)

PAQUETES_TMUX=(
    tmux
)

run_step "Instalando paquetes base" sudo apt install -y "${PAQUETES_BASE[@]}"
run_step "Instalando herramientas de terminal" sudo apt install -y "${PAQUETES_TERMINAL[@]}"
run_step "Instalando aplicaciones útiles para GNOME/Wayland" sudo apt install -y "${PAQUETES_APPS[@]}"
run_step "Instalando plugins ZSH desde APT" sudo apt install -y "${PAQUETES_ZSH[@]}"
run_step "Asegurando instalación de tmux" sudo apt install -y "${PAQUETES_TMUX[@]}"

# ------------------------------------------------------------
# Paquete local opcional lsb.deb
# ------------------------------------------------------------

if [ -f "$RUTA/lsb.deb" ]; then
    run_step "Instalando lsb.deb local" sudo dpkg -i "$RUTA/lsb.deb" || true
    run_step "Corrigiendo dependencias de lsb.deb" sudo apt -f install -y
else
    warn "lsb.deb no encontrado. Saltando."
fi

# ------------------------------------------------------------
# Carpetas base
# ------------------------------------------------------------

mkdir -p "$HOME/github"
mkdir -p "$HOME/Wallpaper"
mkdir -p "$HOME/ScreenShots"
mkdir -p "$HOME/.config"
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/fonts"
mkdir -p "$HOME/.tmux/plugins"

# ------------------------------------------------------------
# Oh My Zsh
# ------------------------------------------------------------

if [ ! -d "$HOME/.oh-my-zsh" ]; then
    run_step "Instalando Oh My Zsh en modo no interactivo" bash -c \
        'RUNZSH=no CHSH=no KEEP_ZSHRC=yes sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"'
else
    run_step "Actualizando Oh My Zsh" git -C "$HOME/.oh-my-zsh" pull
fi

mkdir -p "$HOME/.oh-my-zsh/custom/plugins"

# ------------------------------------------------------------
# Powerlevel10k
# ------------------------------------------------------------

if [ -d "$HOME/.powerlevel10k" ]; then
    run_step "Actualizando Powerlevel10k" git -C "$HOME/.powerlevel10k" pull
else
    run_step "Clonando Powerlevel10k" git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$HOME/.powerlevel10k"
fi

# ------------------------------------------------------------
# Plugins ZSH adicionales
# ------------------------------------------------------------

if [ -d "$HOME/.oh-my-zsh/custom/plugins/zsh-autocomplete" ]; then
    run_step "Actualizando zsh-autocomplete" git -C "$HOME/.oh-my-zsh/custom/plugins/zsh-autocomplete" pull
else
    run_step "Clonando zsh-autocomplete" git clone https://github.com/marlonrichert/zsh-autocomplete.git "$HOME/.oh-my-zsh/custom/plugins/zsh-autocomplete"
fi

sudo mkdir -p /usr/share/zsh-sudo
sudo mkdir -p /usr/share/zsh-web-search

run_step "Instalando plugin sudo.plugin.zsh" sudo wget -q -O /usr/share/zsh-sudo/sudo.plugin.zsh \
    https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/plugins/sudo/sudo.plugin.zsh

run_step "Instalando plugin web-search.plugin.zsh" sudo wget -q -O /usr/share/zsh-web-search/web-search.plugin.zsh \
    https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/plugins/web-search/web-search.plugin.zsh

# ------------------------------------------------------------
# TPM para tmux
# ------------------------------------------------------------

if [ -d "$HOME/.tmux/plugins/tpm" ]; then
    run_step "Actualizando TPM para tmux" git -C "$HOME/.tmux/plugins/tpm" pull
else
    run_step "Clonando TPM para tmux" git clone https://github.com/tmux-plugins/tpm "$HOME/.tmux/plugins/tpm"
fi

# ------------------------------------------------------------
# Atuín
# ------------------------------------------------------------

if command -v atuin >/dev/null 2>&1; then
    ok "Atuin ya está instalado desde APT o binario del sistema."
else
    info "Instalando Atuin mediante instalador oficial..."
    curl --proto '=https' --tlsv1.2 -LsSf https://setup.atuin.sh | sh
fi

# ------------------------------------------------------------
# Fuentes
# ------------------------------------------------------------

if [ -d "$RUTA/fonts" ]; then
    run_step "Instalando fuentes desde $RUTA/fonts" bash -c "
        sudo mkdir -p /usr/share/fonts/truetype/custom
        sudo cp -v \"$RUTA\"/fonts/* /usr/share/fonts/truetype/custom/ || true
        fc-cache -fv
    "
else
    warn "Carpeta fonts no encontrada. Saltando fuentes generales."
fi

if [ -d "$RUTA/Config/polybar/fonts" ]; then
    info "Detectadas fuentes antiguas de Polybar. Se copiarán solo las fuentes, no Polybar."
    run_step "Instalando fuentes desde Config/polybar/fonts" bash -c "
        sudo mkdir -p /usr/share/fonts/truetype/custom
        sudo cp -v \"$RUTA\"/Config/polybar/fonts/* /usr/share/fonts/truetype/custom/ || true
        fc-cache -fv
    "
fi

# ------------------------------------------------------------
# Copia de configuraciones
# ------------------------------------------------------------
# Copia Config/* excepto elementos propios del entorno bspwm/polybar/picom.
#
# Se excluyen:
# - bspwm
# - sxhkd
# - polybar
# - picom
#
# Se copian, si existen, configuraciones como:
# - alacritty
# - kitty
# - rofi
# - ranger
# - fastfetch
# - btop
# - gtk-3.0
# - gtk-4.0
# - nvim
# - cava
# - flameshot
# etc.

EXCLUIR_CONFIGS=(
    "bspwm"
    "sxhkd"
    "polybar"
    "picom"
)

debe_excluir_config() {
    local nombre="$1"
    for item in "${EXCLUIR_CONFIGS[@]}"; do
        if [ "$nombre" = "$item" ]; then
            return 0
        fi
    done
    return 1
}

if [ -d "$RUTA/Config" ]; then
    info "Copiando configuraciones desde $RUTA/Config"

    for dir in "$RUTA"/Config/*; do
        [ -d "$dir" ] || continue

        name="$(basename "$dir")"

        if debe_excluir_config "$name"; then
            warn "Saltando configuración de entorno gráfico no deseado: $name"
            continue
        fi

        rm -rf "$HOME/.config/$name"
        cp -rv "$dir" "$HOME/.config/"
        ok "Configuración de $name copiada a ~/.config/$name"
    done
else
    warn "Carpeta Config no encontrada. Saltando copia de configuraciones."
fi

# ------------------------------------------------------------
# Configuración para root, solo herramientas seguras
# ------------------------------------------------------------

sudo mkdir -p /root/.config

if [ -d "$RUTA/Config/kitty" ]; then
    run_step "Copiando configuración de kitty para root" sudo cp -rv "$RUTA/Config/kitty" /root/.config/
fi

if [ -d "$RUTA/Config/alacritty" ]; then
    run_step "Copiando configuración de alacritty para root" sudo cp -rv "$RUTA/Config/alacritty" /root/.config/
fi

# ------------------------------------------------------------
# Nano
# ------------------------------------------------------------

if [ -d "$RUTA/nanorc" ]; then
    run_step "Instalando sintaxis nanorc globales" bash -c "
        sudo mkdir -p /usr/share/nano
        sudo cp -rv \"$RUTA\"/nanorc/* /usr/share/nano/
    "
fi

if [ -f "$RUTA/.nanorc" ]; then
    cp -v "$RUTA/.nanorc" "$HOME/.nanorc"
    ok ".nanorc instalado"
else
    warn ".nanorc no encontrado en repo"
fi

# ------------------------------------------------------------
# Wallpapers
# ------------------------------------------------------------

if [ -d "$RUTA/Wallpaper" ]; then
    cp -v "$RUTA"/Wallpaper/* "$HOME/Wallpaper/" || true
    ok "Wallpapers copiados a ~/Wallpaper"
else
    warn "Carpeta Wallpaper no encontrada"
fi

# ------------------------------------------------------------
# ZSH, Powerlevel10k y tmux
# ------------------------------------------------------------

if [ -f "$RUTA/.zshrc" ]; then
    cp -v "$RUTA/.zshrc" "$HOME/.zshrc"
    ok ".zshrc instalado"
else
    warn ".zshrc no encontrado en repo"
fi

if [ -f "$RUTA/.p10k.zsh" ]; then
    cp -v "$RUTA/.p10k.zsh" "$HOME/.p10k.zsh"
    ok ".p10k.zsh instalado"
else
    warn ".p10k.zsh no encontrado en repo"
fi

if [ -f "$RUTA/.p10k.zsh-root" ]; then
    sudo cp -v "$RUTA/.p10k.zsh-root" /root/.p10k.zsh
    ok ".p10k.zsh-root instalado en /root/.p10k.zsh"
else
    warn ".p10k.zsh-root no encontrado"
fi

if [ -f "$RUTA/.tmux.conf" ]; then
    cp -v "$RUTA/.tmux.conf" "$HOME/.tmux.conf"
    ok ".tmux.conf instalado"
else
    warn ".tmux.conf no encontrado en repo"
fi

# Asegurar Powerlevel10k en .zshrc si no está
if [ -f "$HOME/.zshrc" ]; then
    if ! grep -q 'powerlevel10k.zsh-theme' "$HOME/.zshrc"; then
        echo 'source ~/.powerlevel10k/powerlevel10k.zsh-theme' >> "$HOME/.zshrc"
        ok "Powerlevel10k añadido a .zshrc"
    fi

    if ! grep -q 'export PATH="$HOME/.atuin/bin:$PATH"' "$HOME/.zshrc"; then
        echo 'export PATH="$HOME/.atuin/bin:$PATH"' >> "$HOME/.zshrc"
        ok "PATH de Atuin añadido a .zshrc"
    fi
fi

# ------------------------------------------------------------
# Compatibilidad Debian: bat y fd
# ------------------------------------------------------------
# En Debian, bat suele instalarse como batcat y fd como fdfind.

mkdir -p "$HOME/.local/bin"

if command -v batcat >/dev/null 2>&1 && ! command -v bat >/dev/null 2>&1; then
    ln -sf "$(command -v batcat)" "$HOME/.local/bin/bat"
    ok "Alias binario creado: ~/.local/bin/bat -> batcat"
fi

if command -v fdfind >/dev/null 2>&1 && ! command -v fd >/dev/null 2>&1; then
    ln -sf "$(command -v fdfind)" "$HOME/.local/bin/fd"
    ok "Alias binario creado: ~/.local/bin/fd -> fdfind"
fi

# ------------------------------------------------------------
# Permisos
# ------------------------------------------------------------

find "$HOME/.config" -type f -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true

if [ -d "$HOME/.config/rofi" ]; then
    find "$HOME/.config/rofi" -type f -exec chmod u+rw {} \; 2>/dev/null || true
fi

# ------------------------------------------------------------
# Cambiar shell a ZSH
# ------------------------------------------------------------

if command -v zsh >/dev/null 2>&1; then
    ZSH_PATH="$(command -v zsh)"

    if [ "$SHELL" != "$ZSH_PATH" ]; then
        run_step "Cambiando shell del usuario a ZSH" sudo chsh -s "$ZSH_PATH" "$USER"
    else
        ok "ZSH ya es la shell del usuario."
    fi

    if [ -f /etc/shells ] && grep -q "$ZSH_PATH" /etc/shells; then
        run_step "Cambiando shell de root a ZSH" sudo chsh -s "$ZSH_PATH" root || true
    fi
fi

# ------------------------------------------------------------
# Verificación Wayland
# ------------------------------------------------------------

echo
echo "------------------------------------------------------------"
echo "[INFO] Verificación de sesión gráfica"
echo "------------------------------------------------------------"
echo "Sesión actual: ${XDG_SESSION_TYPE:-desconocida}"

if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
    ok "Estás usando Wayland."
else
    warn "No parece que estés en Wayland ahora mismo."
    echo "En GDM, selecciona tu usuario, pulsa el engranaje y elige 'GNOME'."
    echo "Evita 'GNOME on Xorg' si quieres Wayland."
fi

# ------------------------------------------------------------
# Mensaje final
# ------------------------------------------------------------

echo
echo "============================================================"
echo "[OK] Personalización completada."
echo "============================================================"
echo
echo "Se ha instalado:"
echo "  - Herramientas base de Debian"
echo "  - ZSH + Oh My Zsh + Powerlevel10k"
echo "  - Plugins ZSH"
echo "  - tmux + TPM"
echo "  - .tmux.conf desde el repo"
echo "  - Configuraciones desde Config/, excluyendo bspwm/sxhkd/polybar/picom"
echo "  - Fuentes"
echo "  - Wallpapers"
echo "  - Herramientas útiles para GNOME/Wayland"
echo
echo "No se ha instalado:"
echo "  - bspwm"
echo "  - sxhkd"
echo "  - polybar"
echo "  - picom"
echo
echo "Siguientes pasos recomendados:"
echo "  1. Cierra sesión y vuelve a entrar."
echo "  2. Comprueba Wayland:"
echo "       echo \$XDG_SESSION_TYPE"
echo "  3. Abre Extension Manager para instalar tus extensiones GNOME."
echo "  4. Abre tmux y pulsa:"
echo "       prefix + I"
echo "     para instalar plugins de TPM."
echo
