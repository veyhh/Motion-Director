import os
import re
import shutil
import sys
import tomllib
from pathlib import Path


def read_config(path: Path | None = None) -> dict:
    path = path or Path.home() / ".motion-director.toml"
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def locate_blender(override: str | None = None, config: dict | None = None) -> Path:
    explicit = override or os.getenv("MOTION_DIRECTOR_BLENDER") or (config or {}).get("blender")
    if explicit:
        candidate = Path(explicit).expanduser()
        if not candidate.is_file():
            raise FileNotFoundError(f"Configured Blender executable does not exist: {candidate}")
        return candidate.resolve()
    on_path = shutil.which("blender")
    if on_path:
        return Path(on_path).resolve()
    candidates = []
    if sys.platform == "win32":
        for base in {
            os.getenv("ProgramFiles", r"C:\Program Files"),
            os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        }:
            candidates.extend(Path(base).glob("Blender Foundation/Blender */blender.exe"))
    elif sys.platform == "darwin":
        candidates = list(Path("/Applications").glob("Blender*.app/Contents/MacOS/Blender"))
    else:
        candidates = [Path("/usr/bin/blender"), Path("/snap/bin/blender")]
    candidates = [p for p in candidates if p.is_file()]
    if candidates:
        return max(candidates, key=lambda p: tuple(map(int, re.findall(r"\d+", str(p))))).resolve()
    raise FileNotFoundError("Blender not found. Set --blender or MOTION_DIRECTOR_BLENDER.")
