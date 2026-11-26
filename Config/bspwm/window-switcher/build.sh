#!/bin/sh

set -eu
source_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
output=${1:-"${XDG_CONFIG_HOME:-$HOME/.config}/bspwm/scripts/window-switcher"}

dependencies="gtk+-3.0 libwnck-3.0 x11 xcomposite xrender cairo-xlib-xrender"
if ! pkg-config --exists $dependencies; then
    printf '%s\n' 'Faltan las dependencias de compilación del selector de ventanas.' >&2
    printf '%s\n' 'En Debian: libgtk-3-dev libwnck-3-dev libx11-dev libxcomposite-dev libxrender-dev' >&2
    exit 1
fi

mkdir -p -- "$(dirname -- "$output")"
temporary=$(mktemp "${output}.XXXXXX")
trap 'unlink "$temporary" 2>/dev/null || true' EXIT
trap 'exit 1' HUP INT TERM
"${CC:-cc}" -std=c11 -O2 -Wall -Wextra -Wpedantic \
    $(pkg-config --cflags $dependencies) "$source_dir/window-switcher.c" \
    -o "$temporary" $(pkg-config --libs $dependencies)
chmod 755 "$temporary"
mv -f -- "$temporary" "$output"
