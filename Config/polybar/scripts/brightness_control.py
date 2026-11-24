#!/usr/bin/env python3
"""Hardware brightness controller with a rootless XRandR fallback."""

import re
import shutil
import subprocess
import sys


MINIMUM = 5
MAXIMUM = 100


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=5)


def connected_output() -> str | None:
    result = run("xrandr", "--query")
    primary = None
    fallback = None
    for line in result.stdout.splitlines():
        match = re.match(r"^(\S+) connected(?: primary)?", line)
        if not match:
            continue
        fallback = fallback or match.group(1)
        if " connected primary " in f" {line} ":
            primary = match.group(1)
    return primary or fallback


def xrandr_value(output: str) -> int:
    result = run("xrandr", "--verbose")
    active = False
    for line in result.stdout.splitlines():
        if line and not line[0].isspace():
            active = line.startswith(f"{output} connected")
        elif active:
            match = re.search(r"Brightness:\s*([0-9.]+)", line)
            if match:
                return round(float(match.group(1)) * 100)
    return 100


def backend() -> str:
    return "hardware" if shutil.which("brightnessctl") else "xrandr"


def get_value() -> int:
    if backend() == "hardware":
        result = run("brightnessctl", "-m")
        match = re.search(r",(\d+)%", result.stdout)
        if match:
            return int(match.group(1))
    output = connected_output()
    return xrandr_value(output) if output else 100


def set_value(value: int) -> bool:
    value = max(MINIMUM, min(MAXIMUM, value))
    if backend() == "hardware":
        return run("brightnessctl", "-q", "set", f"{value}%").returncode == 0
    output = connected_output()
    if not output:
        return False
    return run("xrandr", "--output", output, "--brightness", f"{value / 100:.2f}").returncode == 0


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "status":
        print("󰃠")
        return 0
    if action == "get":
        print(get_value())
        return 0
    if action == "backend":
        print(backend())
        return 0
    if action == "set" and len(sys.argv) == 3:
        return 0 if set_value(round(float(sys.argv[2]))) else 1
    if action == "change" and len(sys.argv) == 3:
        return 0 if set_value(get_value() + int(sys.argv[2])) else 1
    print("Uso: brightness_control.py status|get|backend|set N|change N", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"No se pudo controlar el brillo: {error}", file=sys.stderr)
        raise SystemExit(1)
