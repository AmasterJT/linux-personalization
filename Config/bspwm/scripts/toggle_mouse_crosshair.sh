#!/usr/bin/env bash

set -euo pipefail

if command -v toggle-mouse-crosshair >/dev/null 2>&1; then
    exec toggle-mouse-crosshair toggle
fi

project_toggle="$HOME/Documentos/mouse-crosshair/bin/toggle-mouse-crosshair"
if [[ -x "$project_toggle" ]]; then
    exec "$project_toggle" toggle
fi

printf '%s\n' 'No se encontró toggle-mouse-crosshair.' >&2
exit 1
