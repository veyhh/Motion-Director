import platform
import sys
import tempfile
from pathlib import Path

from motion_director.blender.runner import run_blender


def doctor(blender: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    for directory in (output, Path(tempfile.gettempdir())):
        with tempfile.TemporaryFile(dir=directory) as stream:
            stream.write(b"motion-director")
    runtime = run_blender(blender, {"operation": "doctor"}, timeout=60)
    ready = (
        sys.version_info >= (3, 11)
        and runtime["background"]
        and tuple(runtime["version_tuple"]) >= (4, 0, 0)
    )
    return {
        "ready": ready,
        "python": platform.python_version(),
        "blender": str(blender),
        "version": runtime["version"],
        "bpy": runtime["bpy"],
        "background": runtime["background"],
        "output_writable": True,
        "temp_writable": True,
    }
