#!/bin/bash

# -------------------------------
# BSPWM Installer Pro - Fix Edition
# -------------------------------

# Salir al primer error
set -e

# Obtener la ruta real del script independientemente de dónde se ejecute
RUTA="$(dirname "$(readlink -f "$0")")"

# Funcion para manejo de errores
error_exit() {
    echo -e "\n[ERROR] Ocurrió un error en la línea $1. Saliendo..."
    exit 1
}

trap 'error_exit $LINENO' ERR

# Funcio para ejecutar comandos con trazas (se quita redirección total para ver sudo)
run_step() {
    local msg="$1"
    shift
    echo -e "\n[INFO] $msg..."
    "$@" || { echo "[ERROR] Falló: $msg"; exit 1; }
    echo "[OK] $msg completado."
}

# -------------------------------
# Comprobacion de usuario
# -------------------------------
if [ "$EUID" -eq 0 ]; then
    echo "[ERROR] No ejecutes este script como root. Usa tu usuario normal."
    exit 1
fi

# -------------------------------
# Actualizacion del sistema
# -------------------------------
run_step "Actualizando sistema" sudo apt update
# run_step "Actualizando paquetes" sudo parrot-upgrade -y

# -------------------------------
# Instalando todas las dependencias
# -------------------------------
# He unificado listas y añadido ninja-build para picom
DEP_GENERALES=(
    build-essential git vim xcb libxcb-util0-dev libxcb-ewmh-dev
    libxcb-randr0-dev libxcb-icccm4-dev libxcb-keysyms1-dev
    libxcb-xinerama0-dev libasound2-dev libxcb-xtest0-dev libxcb-shape0-dev
    cmake cmake-data pkg-config python3-sphinx libcairo2-dev
    libxcb1-dev libxcb-composite0-dev python3-xcbgen xcb-proto
    libxcb-image0-dev libxcb-xkb-dev libxcb-xrm-dev libxcb-cursor-dev
    libpulse-dev libjsoncpp-dev libmpdclient-dev libuv1-dev libnl-genl-3-dev
    meson libxext-dev libxcb-damage0-dev libxcb-xfixes0-dev
    libxcb-render-util0-dev libxcb-render0-dev libxcb-present-dev
    libpixman-1-dev libdbus-1-dev libconfig-dev libgl1-mesa-dev libpcre2-dev
    libevdev-dev uthash-dev libev-dev libx11-xcb-dev libxcb-glx0-dev
    libpcre3-dev libpcre2-dev ninja-build curl cava lsd atuin
)

run_step "Instalando dependencias base y de compilación" sudo apt install -y "${DEP_GENERALES[@]}"

PAQUETES_ADICIONALES=(
    feh flameshot scrub zsh rofi xclip bat locate wmname acpi
    bspwm sxhkd imagemagick ranger caja nautilus pavucontrol alacritty
)

# Instalando paquete lsb.deb local
if [ -f "$RUTA/lsb.deb" ]; then
    run_step "Instalando lsb.deb" sudo dpkg -i "$RUTA/lsb.deb"
    run_step "Corrigiendo dependencias de lsb.deb" sudo apt -f install -y
fi

run_step "Instalando paquetes adicionales" sudo apt install -y "${PAQUETES_ADICIONALES[@]}"

# -------------------------------
# Clonando y compilando desde GitHub
# -------------------------------
mkdir -p ~/github
cd ~/github

# -------------------------------
# Clonando repositorios
# -------------------------------
# Clonando Polybar
if [ -d ~/github/polybar ]; then
    run_step "Actualizando Polybar" git -C ~/github/polybar pull
else
    run_step "Clonando Polybar" git clone --recursive https://github.com/polybar/polybar ~/github/polybar
fi

# Clonando Picom
if [ -d ~/github/picom ]; then
    run_step "Actualizando Picom" git -C ~/github/picom pull
else
    run_step "Clonando Picom" git clone https://github.com/ibhagwan/picom.git ~/github/picom
fi

# Clonando zscroll
if [ -d ~/github/zscroll ]; then
    run_step "Actualizando zscroll" git -C ~/github/zscroll pull
else
    run_step "Clonando zscroll" git clone https://github.com/noctuid/zscroll ~/github/zscroll
fi

# Picom (ibhagwan)
if [ ! -d "picom" ]; then
    run_step "Clonando Picom" git clone https://github.com/ibhagwan/picom.git
fi
run_step "Compilando Picom" bash -c "cd picom && git submodule update --init --recursive && meson --buildtype=release . build && ninja -C build && sudo ninja -C build install"

# zscroll
if [ ! -d "zscroll" ]; then
    run_step "Clonando zscroll" git clone https://github.com/noctuid/zscroll
fi
run_step "Instalando zscroll" bash -c "cd zscroll && sudo python3 setup.py install"

# -------------------------------
# Instalando Powerlevel10k
# -------------------------------
# Instalando Powerlevel10k
if [ -d ~/.powerlevel10k ]; then
    run_step "Actualizando Powerlevel10k" git -C ~/.powerlevel10k pull
else
    run_step "Clonando Powerlevel10k" git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/.powerlevel10k
fi

# Fuente para Zsh
if ! grep -q 'source ~/.powerlevel10k/powerlevel10k.zsh-theme' ~/.zshrc; then
    echo 'source ~/.powerlevel10k/powerlevel10k.zsh-theme' >> ~/.zshrc
fi


# -------------------------------
# Configuracin y Fuentes
# -------------------------------
# Copiar fuentes (comprueba si la carpeta existe primero)
if [ -d "$RUTA/fonts" ]; then
    run_step "Instalando fuentes" bash -c "
    sudo mkdir -p /usr/share/fonts/truetype/custom
    sudo cp -v $RUTA/fonts/* /usr/share/fonts/truetype/custom/
    [ -d $RUTA/Config/polybar/fonts ] && sudo cp -v $RUTA/Config/polybar/fonts/* /usr/share/fonts/truetype/custom/
    fc-cache -fv
    "
fi

# -------------------------------
# Copiando carpetas de Configuracin
# -------------------------------
for dir in "$RUTA"/Config/*; do
    [ -d "$dir" ] || continue
    name=$(basename "$dir")
    rm -rf ~/.config/"$name"
    cp -rv "$dir" ~/.config/
    echo "[OK] Configuracion de $name copiada."
done



# Caso especial Root (solo si existen)
[ -d "$RUTA/Config/kitty" ] && sudo cp -rv "$RUTA/Config/kitty" /root/.config/
[ -d "$RUTA/nanorc" ] && sudo mkdir -p /usr/share/nano && sudo cp -rv "$RUTA/nanorc"/* /usr/share/nano/

# -------------------------------
# Wallpapers y ZSH
# -------------------------------
mkdir -p ~/Wallpaper ~/ScreenShots
[ -d "$RUTA/Wallpaper" ] && cp -v "$RUTA"/Wallpaper/* ~/Wallpaper/

#Nano Config
cp -v "$RUTA/.nanorc" ~/.nanorc 2>/dev/null || echo "[WARN] .nanorc no encontrado en repo"

# Zsh Config
cp -v "$RUTA/.zshrc" ~/.zshrc 2>/dev/null || echo "[WARN] .zshrc no encontrado en repo"
cp -v "$RUTA/.p10k.zsh" ~/.p10k.zsh 2>/dev/null || echo "[WARN] .p10k.zsh no encontrado en repo"
sudo cp -v "$RUTA/.p10k.zsh-root" /root/.p10k.zsh 2>/dev/null || echo "[WARN] .p10k.zsh-root no encontrado"

# -------------------------------
# Plugins Zsh y Aplicaciones
# -------------------------------

# Instalar plugins APT si existen
run_step "Instalando plugin zsh-syntax-highlighting" sudo apt install -y zsh-syntax-highlighting || true
run_step "Instalando plugin zsh-autosuggestions" sudo apt install -y zsh-autosuggestions || true

# Crear carpetas de plugins
mkdir -p ~/.oh-my-zsh/custom/plugins
sudo mkdir -p /usr/share/zsh-sudo
sudo mkdir -p /usr/share/zsh-web-search

# zsh-autocomplete
if [ ! -d ~/.oh-my-zsh/custom/plugins/zsh-autocomplete ]; then
    run_step "Clonando zsh-autocomplete" git clone https://github.com/marlonrichert/zsh-autocomplete.git ~/.oh-my-zsh/custom/plugins/zsh-autocomplete
else
    run_step "Actualizando zsh-autocomplete" git -C ~/.oh-my-zsh/custom/plugins/zsh-autocomplete pull
fi

# web-search.plugin.zsh
if [ ! -f /usr/share/zsh-web-search/web-search.plugin.zsh ]; then
    run_step "Descargando web-search.plugin.zsh" sudo wget -q -O /usr/share/zsh-web-search/web-search.plugin.zsh \
        https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/plugins/web-search/web-search.plugin.zsh
else
    run_step "Actualizando web-search.plugin.zsh" sudo wget -q -O /usr/share/zsh-web-search/web-search.plugin.zsh \
        https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/plugins/web-search/web-search.plugin.zsh
fi

# sudo.plugin.zsh
if [ ! -f /usr/share/zsh-sudo/sudo.plugin.zsh ]; then
    run_step "Descargando sudo.plugin.zsh" sudo wget -q -O /usr/share/zsh-sudo/sudo.plugin.zsh \
        https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/plugins/sudo/sudo.plugin.zsh
else
    run_step "Actualizando sudo.plugin.zsh" sudo wget -q -O /usr/share/zsh-sudo/sudo.plugin.zsh \
        https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/plugins/sudo/sudo.plugin.zsh
fi

# -------------------------------
# Instalando Atuín (historial avanzado)
# -------------------------------
if [ ! -d ~/.atuin ]; then
    curl --proto '=https' --tlsv1.2 -LsSf https://setup.atuin.sh | sh
else
    run_step "Actualizando Atuín" echo ""
fi

# Asegurar que ~/.atuin/bin esté en PATH
if ! grep -q 'export PATH="$HOME/.atuin/bin:$PATH"' ~/.zshrc; then
    echo 'export PATH="$HOME/.atuin/bin:$PATH"' >> ~/.zshrc
fi



# -------------------------------
# Permisos y Shell
# -------------------------------
run_step "Cambiando shell a Zsh" sudo chsh -s /usr/bin/zsh "$USER"
sudo chsh -s /usr/bin/zsh root

# Asegurar permisos de ejecución
chmod +x ~/.config/bspwm/bspwmrc 2>/dev/null || true
chmod +x ~/.config/bspwm/scripts/* 2>/dev/null || true
chmod +x ~/.config/polybar/launch.sh 2>/dev/null || true

echo -e "\n[INFO] Instalación completada. Reinicia para aplicar todos los cambios."
