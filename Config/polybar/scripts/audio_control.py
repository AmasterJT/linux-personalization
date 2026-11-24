#!/usr/bin/env python3
"""Shared perceptual audio controls for the BSPWM panel and multimedia keys."""

import re
import subprocess


VOLUME_PATTERN = re.compile(r"Volume:\s+([0-9.]+)")
CURVE_EXPONENT = 3.0
DEFAULT_MAXIMUM = 150


def sink_icon(value: int, muted: bool) -> str:
    """Return the shared speaker glyph used by Polybar and both GTK panels."""
    if muted:
        return "󰖁"
    return "󰕿" if value < 45 else "󰕾"


def source_icon(muted: bool) -> str:
    return "󰍭" if muted else ""


def run_wpctl(*arguments: str, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["wpctl", *arguments], text=True, capture_output=True,
            timeout=timeout, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(["wpctl", *arguments], 1, "", str(error))


def wpctl_to_percent(value: float) -> float:
    """Convert WirePlumber's cubic control value to a linear slider value."""
    return max(0.0, value) ** CURVE_EXPONENT * 100.0


def percent_to_wpctl(value: float) -> float:
    """Convert a linear slider value to WirePlumber's cubic control value."""
    return (max(0.0, value) / 100.0) ** (1.0 / CURVE_EXPONENT)


def volume_state(target: str, maximum: int = DEFAULT_MAXIMUM) -> tuple[int, bool]:
    output = run_wpctl("get-volume", target, timeout=4).stdout
    match = VOLUME_PATTERN.search(output)
    raw_value = float(match.group(1)) if match else 0.0
    value = round(wpctl_to_percent(raw_value))
    return max(0, min(value, maximum)), "[MUTED]" in output


def set_volume_percent(target: str, value: float, maximum: int = DEFAULT_MAXIMUM) -> bool:
    value = max(0.0, min(float(value), float(maximum)))
    raw_value = percent_to_wpctl(value)
    raw_limit = percent_to_wpctl(maximum)
    result = run_wpctl(
        "set-volume", "-l", f"{raw_limit:.6f}", target, f"{raw_value:.6f}", timeout=5,
    )
    return result.returncode == 0


def change_volume(target: str, delta: int, maximum: int = DEFAULT_MAXIMUM) -> int:
    value, _muted = volume_state(target, maximum)
    new_value = max(0, min(maximum, value + delta))
    set_volume_percent(target, new_value, maximum)
    run_wpctl("set-mute", target, "0", timeout=4)
    return new_value


def toggle_mute(target: str, maximum: int = DEFAULT_MAXIMUM) -> tuple[int, bool]:
    run_wpctl("set-mute", target, "toggle", timeout=4)
    return volume_state(target, maximum)
