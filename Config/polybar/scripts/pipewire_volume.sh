#!/usr/bin/env sh

# Stable Polybar volume control for PipeWire/WirePlumber. Unlike Polybar's
# internal ALSA module, this recovers automatically if audio starts late.
set -u

sink='@DEFAULT_AUDIO_SINK@'

volume_status() {
    state=$(wpctl get-volume "$sink" 2>/dev/null) || {
        # Keep the module visible while WirePlumber is still starting.
        printf '%%{T13}%%{F#757575}󰖁%%{F-}%%{T-}\n'
        return
    }

    volume=$(printf '%s\n' "$state" | awk '{print $2}')
    muted=$(printf '%s\n' "$state" | grep -c '\[MUTED\]' || true)
    level=$(awk -v value="$volume" 'BEGIN {
        n = int((value * 8) + 0.5)
        if (n < 0) n = 0
        if (n > 8) n = 8
        print n
    }')

    if [ "$muted" -gt 0 ]; then
        icon='󰖁'
        color='#757575'
        level=0
    else
        if [ "$level" -le 2 ]; then icon='󰕿'; else icon='󰕾'; fi
        color='#FFFFFF'
    fi

    printf '%%{T13}%%{F%s}%s%%{F-}%%{T-}\n' "$color" "$icon"
}

case "${1:-status}" in
    status)
        volume_status
        ;;
    *)
        printf 'Usage: %s status\n' "$0" >&2
        exit 2
        ;;
esac
