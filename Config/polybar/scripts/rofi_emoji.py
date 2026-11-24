#!/usr/bin/env python3
"""Search, copy and insert an emoji using the existing Polybar Rofi theme."""

from pathlib import Path
import os
import subprocess
import time


THEME = Path.home() / ".config/polybar/scripts/themes/launcher.rasi"
EMOJI_FILES = (
    Path("/usr/share/unicode/emoji/emoji-test.txt"),
    Path("/usr/share/unicode/emoji-test.txt"),
)
THEME_OVERRIDE = """
window { location: north; anchor: north; width: 38%; height: 44%; x-offset: 0px; y-offset: 56px; }
entry { placeholder: "Buscar emoji"; }
listview { columns: 1; }
"""


def load_emojis() -> tuple[list[str], list[str]]:
    source = next((path for path in EMOJI_FILES if path.is_file()), None)
    if source is None:
        raise FileNotFoundError("No se encontró emoji-test.txt")

    emojis: list[str] = []
    rows: list[str] = []
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            if "; fully-qualified" not in line or "#" not in line:
                continue
            comment = line.split("#", 1)[1].strip().split(maxsplit=2)
            if len(comment) < 3:
                continue
            glyph, _version, name = comment
            emojis.append(glyph)
            rows.append(f"{glyph}  {name}")
    return emojis, rows


def copy_and_paste(text: str) -> None:
    subprocess.run(
        ["xclip", "-selection", "clipboard"],
        input=text,
        text=True,
        check=True,
    )
    time.sleep(0.15)
    xdotool = Path.home() / ".local/bin/xdotool"
    command = str(xdotool) if xdotool.is_file() else "xdotool"
    if subprocess.run(["sh", "-c", f"command -v {command!s}"], capture_output=True).returncode == 0:
        subprocess.run([command, "key", "--clearmodifiers", "ctrl+v"], check=False)


def main() -> int:
    try:
        emojis, rows = load_emojis()
    except FileNotFoundError as error:
        subprocess.run(["rofi", "-e", str(error)], check=False)
        return 1

    result = subprocess.run(
        [
            "rofi", "-dmenu", "-i", "-no-custom", "-format", "i",
            "-p", "Emoji", "-theme", str(THEME),
            "-theme-str", THEME_OVERRIDE,
        ],
        input="\n".join(rows),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip().isdigit():
        return 0
    copy_and_paste(emojis[int(result.stdout.strip())])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
