#!/bin/bash

# -------------------------------
# BSPWM Installer Mejorado
# -------------------------------

# Salir al primer error
set -e

# Función para manejo de errores
error_exit() {
    echo "[ERROR] Ocurrió un error en la línea $1. Saliendo..."
    notify-send "BSPWM INSTALLER" "Ocurrió un error. Revisa el terminal."
    exit 1
}

# Captura errores
trap 'error_exit $LINENO' ERR

# Función para ejecutar comandos con trazas
run_step() {
    echo -e "\n[INFO] $1..."
    shift
    "$@" >/dev/null 2>&1
    echo "[OK] $1 completado."
}

# -------------------------------
# Comprobación de usuario
# -------------------------------
if [ "$(whoami)" == "root" ]; then
    echo "[ERROR] No ejecutes este script como root."
    exit 1
fi

ruta=$(pwd)

# -------------------------------
# Actualización del sistema
# -------------------------------
run_step "Actualizando sistema" sudo apt update
run_step "Actualizando paquetes" sudo parrot-upgrade -y

# -------------------------------
# Instalando dependencias
# -------------------------------
DEPENDENCIAS_ENTORNO=(
    build-essential git vim xcb libxcb-util0-dev libxcb-ewmh-dev
    libxcb-randr0-dev libxcb-icccm4-dev libxcb-keysyms1-dev
    libxcb-xinerama0-dev libasound2-dev libxcb-xtest0-dev libxcb-shape0-dev
)

run_step "Instalando dependencias de entorno" sudo apt install -y "${DEPENDENCIAS_ENTORNO[@]}"

DEPENDENCIAS_POLYBAR=(
    cmake cmake-data pkg-config python3-sphinx libcairo2-dev
    libxcb1-dev libxcb-util0-dev libxcb-randr0-dev libxcb-composite0-dev python3-xcbgen
    xcb-proto libxcb-image0-dev libxcb-ewmh-dev libxcb-icccm4-dev libxcb-xkb-dev
    libxcb-xrm-dev libxcb-cursor-dev libasound2-dev libpulse-dev libjsoncpp-dev
    libmpdclient-dev libuv1-dev libnl-genl-3-dev curl cava
)

run_step "Instalando dependencias de Polybar" sudo apt install -y "${DEPENDENCIAS_POLYBAR[@]}"

DEPENDENCIAS_PICOM=(
    meson libxext-dev libxcb1-dev libxcb-damage0-dev
    libxcb-xfixes0-dev libxcb-shape0-dev libxcb-render-util0-dev libxcb-render0-dev
    libxcb-composite0-dev libxcb-image0-dev libxcb-present-dev libxcb-xinerama0-dev
    libpixman-1-dev libdbus-1-dev libconfig-dev libgl1-mesa-dev libpcre2-dev
    libevdev-dev uthash-dev libev-dev libx11-xcb-dev libxcb-glx0-dev libpcre3 libpcre3-dev
)

run_step "Instalando dependencias de Picom" sudo apt install -y "${DEPENDENCIAS_PICOM[@]}"

PAQUETES_ADICIONALES=(
    feh flameshot scrub zsh rofi xclip bat locate wmname acpi
    bspwm sxhkd imagemagick ranger caja nautilus pavucontrol lsb alacritty
)

run_step "Instalando paquetes adicionales" sudo apt install -y "${PAQUETES_ADICIONALES[@]}"

# -------------------------------
# Crear repositorios
# -------------------------------
mkdir -p ~/github

# -------------------------------
# Clonando repositorios
# -------------------------------
run_step "Clonando Polybar" git clone --recursive https://github.com/polybar/polybar ~/github/polybar
run_step "Clonando Picom" git clone https://github.com/ibhagwan/picom.git ~/github/picom
run_step "Clonando zscroll" git clone https://github.com/noctuid/zscroll ~/github/zscroll

# -------------------------------
# Instalando Polybar
# -------------------------------
run_step "Instalando Polybar" bash -c "
cd ~/github/polybar
mkdir -p build
cd build
cmake .. >/dev/null
make -j\$(nproc) >/dev/null
sudo make install >/dev/null
"

# -------------------------------
# Instalando Picom
# -------------------------------
run_step "Instalando Picom" bash -c "
cd ~/github/picom
git submodule update --init --recursive >/dev/null
meson --buildtype=release . build >/dev/null
ninja -C build >/dev/null
sudo ninja -C build install >/dev/null
"

# -------------------------------
# Instalando zscroll
# -------------------------------
run_step "Instalando zscroll" bash -c "
cd ~/github/zscroll
sudo python3 setup.py install >/dev/null
"

# -------------------------------
# Instalando Powerlevel10k
# -------------------------------
run_step "Instalando Powerlevel10k" git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/.powerlevel10k
echo 'source ~/.powerlevel10k/powerlevel10k.zsh-theme' >>~/.zshrc
sudo git clone --depth=1 https://github.com/romkatv/powerlevel10k.git /root/.powerlevel10k

# -------------------------------
# Copiando temas Rofi
# -------------------------------
run_step "Copiando temas Rofi" mkdir -p ~/.config/rofi/themes
cp -rv $ruta/Config/rofi/themes/* ~/.config/rofi/themes/

# -------------------------------
# Instalando fuentes
# -------------------------------
run_step "Instalando fuentes" bash -c "
sudo mkdir -p /usr/share/fonts/truetype/custom
sudo cp -v $ruta/fonts/* /usr/share/fonts/truetype/custom/
sudo cp -v $ruta/Config/polybar/fonts/* /usr/share/fonts/truetype/custom/
fc-cache -fv >/dev/null
"

# -------------------------------
# Instalando nanorc
# -------------------------------
run_step "Instalando nanorc" bash -c "
sudo mkdir -p /usr/share/nano
sudo cp -rv $ruta/nanorc/* /usr/share/nano/
"

# -------------------------------
# Wallpaper y Screenshots
# -------------------------------
mkdir -p ~/Wallpaper ~/ScreenShots
cp -v $ruta/Wallpaper/* ~/Wallpaper

# -------------------------------
# Copiando configuración
# -------------------------------
for dir in $ruta/Config/*; do
    name=$(basename "$dir")
    rm -rf ~/.config/$name
    run_step "Copiando $name" cp -rv "$dir" ~/.config/
done

# -------------------------------
# Kitty root
# -------------------------------
sudo cp -rv $ruta/Config/kitty /root/.config/

# -------------------------------
# Zsh y P10K
# -------------------------------
rm -f ~/.zshrc
cp -v $ruta/.zshrc ~/.zshrc
cp -v $ruta/.p10k.zsh ~/.p10k.zsh
sudo cp -v $ruta/.p10k.zsh-root /root/.p10k.zsh

# -------------------------------
# Polybar Spotify
# -------------------------------
run_step "Clonando plugin Polybar Spotify" git clone https://github.com/PrayagS/polybar-spotify.git ~/.config/polybar/scripts/polybar-spotify

# -------------------------------
# Plugins Zsh
# -------------------------------
run_step "Instalando plugins Zsh" sudo apt install -y zsh-syntax-highlighting zsh-autosuggestions zsh-autocomplete web-search.plugin.zsh
sudo mkdir -p /usr/share/zsh-sudo
cd /usr/share/zsh-sudo
sudo wget -q https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/plugins/sudo/sudo.plugin.zsh

# -------------------------------
# Cambiando shell a Zsh
# -------------------------------
run_step "Cambiando shell a Zsh" chsh -s /usr/bin/zsh
sudo usermod --shell /usr/bin/zsh root
sudo ln -sf ~/.zshrc /root/.zshrc

# -------------------------------
# Permisos de Scripts
# -------------------------------
chmod +x ~/.config/bspwm/bspwmrc
chmod +x ~/.config/bspwm/scripts/*
chmod +x ~/.config/zsh/*.zsh
chmod +x ~/.config/polybar/launch.sh

# -------------------------------
# Finalización
# -------------------------------
notify-send "BSPWM y Entorno Instalado Correctamente"
echo "[INFO] Instalación completada exitosamente."
