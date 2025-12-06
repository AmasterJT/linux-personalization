#!/bin/bash

CONNECTED_COLOR="#43A047"
DISCONNECTED_COLOR="#F6CF59"
ICON_CONNECTED=""
ICON_DISCONNECTED=""


if ping -q -c 1 -W 1 8.8.8.8 > /dev/null; then
    echo "%{F$CONNECTED_COLOR}$ICON_CONNECTED%{F-}" # connected
else
    echo "%{F$DISCONNECTED_COLOR}$ICON_DISCONNECTED%{F-}" # disconnected
fi
