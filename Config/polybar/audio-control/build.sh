#!/bin/sh

set -eu
source_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
output=${1:-"${XDG_CONFIG_HOME:-$HOME/.config}/polybar/scripts/audio-control"}

dependencies="gtk+-3.0 libpulse libpulse-mainloop-glib"
if ! pkg-config --exists $dependencies; then
    printf '%s\n' 'Faltan las dependencias de audio-control: libgtk-3-dev libpulse-dev.' >&2
    exit 1
fi

mkdir -p -- "$(dirname -- "$output")"
temporary=$(mktemp "${output}.XXXXXX")
trap 'unlink "$temporary" 2>/dev/null || true' EXIT
trap 'exit 1' HUP INT TERM
"${CC:-cc}" -std=c11 -O2 -Wall -Wextra -Wpedantic \
    $(pkg-config --cflags $dependencies) "$source_dir/audio-control.c" \
    -o "$temporary" $(pkg-config --libs $dependencies) -lm
chmod 755 "$temporary"
mv -f -- "$temporary" "$output"
