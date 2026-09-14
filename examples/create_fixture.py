"""Run with system Python from the repository: python examples/create_fixture.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motion_director.blender.locate import locate_blender  # noqa: E402
from motion_director.blender.runner import run_blender  # noqa: E402

if __name__ == "__main__":
    target = Path(__file__).with_name("humanoid.glb").resolve()
    if target.exists():
        raise SystemExit(f"Fixture already exists: {target}")
    print(run_blender(locate_blender(), {"operation": "fixture", "output": str(target)}))
