#!/usr/bin/env python3
"""Private X11 clipboard history with text and image previews in Rofi."""

from datetime import datetime
from pathlib import Path
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time


STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "linux-personalization"
HISTORY_FILE = STATE_DIR / "clipboard-history.json"
LOCK_FILE = STATE_DIR / "clipboard-history.lock"
IMAGES_DIR = STATE_DIR / "clipboard-images"
THEME = Path.home() / ".config/polybar/scripts/themes/clipboard.rasi"
MAX_ITEMS = 100
MAX_TEXT_BYTES = 200_000
MAX_IMAGE_BYTES = 20_000_000
IMAGE_TARGETS = ("image/png", "image/jpeg", "image/jpg", "image/bmp")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_item(item: object) -> dict[str, str] | None:
    # Migrate the original string-only history without losing any entries.
    if isinstance(item, str) and item.strip():
        return {"type": "text", "text": item, "copied_at": ""}
    if not isinstance(item, dict):
        return None
    kind = item.get("type")
    if kind == "text" and isinstance(item.get("text"), str):
        return {
            "type": "text",
            "text": item["text"],
            "copied_at": str(item.get("copied_at", "")),
        }
    if kind == "image" and all(isinstance(item.get(key), str) for key in ("file", "mime", "digest")):
        entry = {
            "type": "image",
            "file": item["file"],
            "mime": item["mime"],
            "digest": item["digest"],
            "copied_at": str(item.get("copied_at", "")),
        }
        return entry if image_path(entry).is_file() else None
    return None


def load_history() -> list[dict[str, str]]:
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    history: list[dict[str, str]] = []
    for raw_item in data:
        item = normalize_item(raw_item)
        if item is not None:
            history.append(item)
    return history


def image_path(item: dict[str, str]) -> Path:
    return STATE_DIR / item["file"]


def cleanup_images(history: list[dict[str, str]]) -> None:
    if not IMAGES_DIR.is_dir():
        return
    referenced = {
        image_path(item).resolve()
        for item in history
        if item.get("type") == "image"
    }
    for path in IMAGES_DIR.iterdir():
        if path.is_file() and path.resolve() not in referenced:
            path.unlink()


def save_history(history: list[dict[str, str]]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE_DIR.chmod(0o700)
    stored = history[:MAX_ITEMS]
    temporary = HISTORY_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(HISTORY_FILE)
    cleanup_images(stored)


def xclip_output(target: str | None = None, timeout: float = 2) -> bytes | None:
    command = ["xclip", "-selection", "clipboard", "-o"]
    if target:
        command[3:3] = ["-t", target]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 and result.stdout else None


def clipboard_targets() -> set[str]:
    raw = xclip_output("TARGETS", timeout=1)
    if raw is None:
        return set()
    return {line.strip() for line in raw.decode("utf-8", errors="ignore").splitlines() if line.strip()}


def read_clipboard() -> dict[str, object] | None:
    targets = clipboard_targets()
    for mime in IMAGE_TARGETS:
        if mime not in targets:
            continue
        data = xclip_output(mime)
        if data and len(data) <= MAX_IMAGE_BYTES:
            return {
                "type": "image",
                "mime": "image/jpeg" if mime == "image/jpg" else mime,
                "digest": hashlib.sha256(data).hexdigest(),
                "data": data,
            }

    data = xclip_output()
    if data is None or len(data) > MAX_TEXT_BYTES or b"\0" in data:
        return None
    text = data.decode("utf-8", errors="replace")
    if not text.strip():
        return None
    return {"type": "text", "text": text}


def persist_value(value: dict[str, object]) -> dict[str, str]:
    if value["type"] == "text":
        return {"type": "text", "text": str(value["text"]), "copied_at": now_iso()}

    mime = str(value["mime"])
    digest = str(value["digest"])
    extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/bmp": ".bmp"}.get(mime, ".img")
    IMAGES_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    IMAGES_DIR.chmod(0o700)
    path = IMAGES_DIR / f"{digest}{extension}"
    if not path.exists():
        path.write_bytes(value["data"] if isinstance(value["data"], bytes) else bytes())
    path.chmod(0o600)
    return {
        "type": "image",
        "file": str(path.relative_to(STATE_DIR)),
        "mime": mime,
        "digest": digest,
        "copied_at": now_iso(),
    }


def identity(item: dict[str, str]) -> tuple[str, str]:
    if item["type"] == "image":
        return "image", item["digest"]
    return "text", item["text"]


def daemon() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    LOCK_FILE.touch(mode=0o600, exist_ok=True)
    LOCK_FILE.chmod(0o600)
    with LOCK_FILE.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        previous: tuple[str, str] | None = None
        while True:
            value = read_clipboard()
            if value is not None:
                fingerprint = (
                    "image", str(value["digest"])
                ) if value["type"] == "image" else ("text", str(value["text"]))
                if fingerprint != previous:
                    entry = persist_value(value)
                    history = [item for item in load_history() if identity(item) != identity(entry)]
                    save_history([entry, *history])
                    previous = fingerprint
            time.sleep(0.6)


def summary(text: str) -> str:
    compact = " ↵ ".join(part.strip() for part in text.splitlines() if part.strip())
    compact = compact.replace("\t", " ")
    return compact[:140] + ("…" if len(compact) > 140 else "")


def display_time(value: str) -> str:
    try:
        copied = datetime.fromisoformat(value).astimezone()
        return copied.strftime("%d/%m/%Y  ·  %H:%M:%S")
    except (ValueError, TypeError):
        return "Fecha desconocida"


def menu_row(item: dict[str, str], selected: bool) -> bytes:
    marker = "●" if selected else " "
    if item["type"] == "image":
        label = f"{marker}  {display_time(item.get('copied_at', ''))}"
        metadata = f"\0icon\x1f{image_path(item)}"
        return (label + metadata).encode("utf-8")
    label = f"{marker}  {summary(item['text'])}"
    return (label + "\0icon\x1fedit-paste-symbolic").encode("utf-8")


def paste(item: dict[str, str]) -> None:
    if item["type"] == "image":
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", item["mime"], "-i"],
            input=image_path(item).read_bytes(),
            check=True,
        )
    else:
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=item["text"], text=True, check=True,
        )
    time.sleep(0.15)
    local_xdotool = Path.home() / ".local/bin/xdotool"
    command = str(local_xdotool) if local_xdotool.is_file() else "xdotool"
    try:
        subprocess.run([command, "key", "--clearmodifiers", "ctrl+v"], check=False)
    except FileNotFoundError:
        pass


def menu() -> int:
    while True:
        history = load_history()
        if not history:
            subprocess.run(["rofi", "-e", "El historial del portapapeles está vacío"], check=False)
            return 0

        rows = b"\n".join(menu_row(item, index == 0) for index, item in enumerate(history))
        result = subprocess.run(
            [
                "rofi", "-dmenu", "-i", "-no-custom", "-format", "i",
                "-p", "", "-theme", str(THEME), "-show-icons",
                "-mesg", "Enter: pegar   •   Mayús+Supr: eliminar   •   Ctrl+Mayús+Supr: limpiar",
                "-kb-delete-entry", "",
                "-kb-custom-1", "Shift+Delete",
                "-kb-custom-2", "Control+Shift+Delete",
            ],
            input=rows,
            capture_output=True,
            check=False,
        )
        selected = result.stdout.decode("utf-8", errors="ignore").strip()
        if result.returncode == 0 and selected.isdigit():
            paste(history[int(selected)])
            return 0
        if result.returncode == 10 and selected.isdigit():
            del history[int(selected)]
            save_history(history)
            continue
        if result.returncode == 11:
            save_history([])
        return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--daemon":
        return daemon()
    if len(sys.argv) == 2 and sys.argv[1] == "--menu":
        return menu()
    print(f"Uso: {sys.argv[0]} --daemon|--menu", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
