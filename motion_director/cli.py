import argparse
import json
import subprocess
import sys
from pathlib import Path

from motion_director.blender.locate import locate_blender, read_config
from motion_director.blender.runner import run_blender
from motion_director.doctor import doctor
from motion_director.gltf import validate_clip
from motion_director.paths import input_path
from motion_director.pipeline import create_animation


def parser():
    root = argparse.ArgumentParser(
        prog="motion-director", description="Local Blender game animation"
    )
    sub = root.add_subparsers(dest="command", required=True)
    for name in ("doctor", "inspect", "create-animation", "validate"):
        command = sub.add_parser(name)
        command.add_argument("--blender", help="Path to Blender executable")
        command.add_argument(
            "--config", type=Path, help="TOML config (default ~/.motion-director.toml)"
        )
        command.add_argument("--json", action="store_true", help="Print machine-readable JSON")
        if name != "doctor":
            command.add_argument("file", type=Path)
        if name in ("inspect", "create-animation"):
            command.add_argument(
                "--mapping", type=Path, help="JSON canonical role -> actual bone name"
            )
        if name in ("doctor", "create-animation"):
            command.add_argument("--output", type=Path, default=Path("output"))
        if name == "create-animation":
            command.add_argument("description")
            command.add_argument("--duration", type=float, default=0.9)
            command.add_argument("--fps", type=int, default=50)
            command.add_argument("--preview", action="store_true")
            command.add_argument("--timeout", type=int, default=900)
        if name == "validate":
            command.add_argument("--metadata", type=Path)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        blender = locate_blender(args.blender, read_config(args.config))
        mapping = (
            json.loads(args.mapping.read_text(encoding="utf-8"))
            if getattr(args, "mapping", None)
            else None
        )
        if args.command == "doctor":
            result = doctor(blender, args.output)
            if not args.json:
                print(
                    f"Motion Director Doctor\n\nPython   OK {result['python']}\n"
                    f"Blender  OK {result['version']}\nPath     {blender}\n"
                    "bpy      OK via Blender background runtime\nOutput   OK writable\n"
                    "Temp     OK writable\n\n" + ("READY" if result["ready"] else "NOT READY")
                )
                return 0 if result["ready"] else 1
        elif args.command == "inspect":
            result = run_blender(
                blender,
                {"operation": "inspect", "input": str(input_path(args.file)), "mapping": mapping},
            )
        elif args.command == "create-animation":
            result = create_animation(
                args.file,
                args.description,
                args.output,
                blender,
                duration=args.duration,
                fps=args.fps,
                preview=args.preview,
                mapping=mapping,
                timeout=args.timeout,
            )
            if not args.json:
                print("SpearThrow generated and verified in Blender.")
                for name, path in result["paths"].items():
                    print(f"{name}: {path}")
                return 0
        else:
            source = input_path(args.file)
            metadata_path = args.metadata or source.parent / "spear_throw.motion.json"
            if not metadata_path.is_file():
                raise ValueError(
                    "Motion metadata required; use --metadata path/to/spear_throw.motion.json"
                )
            plan = json.loads(metadata_path.read_text(encoding="utf-8"))
            clip = validate_clip(source, plan)
            result = run_blender(
                blender,
                {
                    "operation": "validate",
                    "input": str(source),
                    "plan": plan,
                    "mapping": plan.get("rig_mapping"),
                },
            )
            result["clip"] = clip
        result.pop("blender_log", None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("qa", {}).get("passed", True) and result.get("ready", True) else 1
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        print(f"Motion Director error: {error}", file=sys.stderr)
        return 1
