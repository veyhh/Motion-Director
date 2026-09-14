import json
import os
import tempfile
from pathlib import Path

from motion_director.blender.runner import run_blender
from motion_director.gltf import validate_clip
from motion_director.motion.spear_throw import make_plan
from motion_director.paths import input_path, output_paths, sha256


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def metadata(plan, source, digest, result, clip):
    return {
        "schema_version": 1,
        **plan,
        "input": str(source),
        "input_sha256": digest,
        "generator": "motion-director/0.1.0",
        "backend": "local Blender; no external AI",
        "rig_mapping": result["inspection"]["rigs"][0]["mapping"],
        "qa": result["qa"],
        "correction_passes": len(result["passes"]) - 1,
        "passes": result["passes"],
        "export_validation": clip,
        "preview": result.get("preview", {}),
        "limitations": [
            "Right-handed spear throw only; description selects a fixed motion recipe.",
            "No spear mesh or projectile is added to the character export.",
            "Existing clips are replaced in the output; the original input is preserved.",
            "Visual quality depends on skin weights and humanoid proportions.",
        ],
    }


def report_text(data):
    lines = [
        "# Spear Throw Report",
        "",
        f"Animation: **{data['animation']}**",
        f"Duration: {data['duration']:.3f} s at {data['fps']} fps",
        f"Input SHA-256 (unchanged): `{data['input_sha256']}`",
        f"Projectile release: {data['events'][0]['time']:.3f} s / "
        f"frame {data['events'][0]['frame']}",
        f"Self-correction passes: {data['correction_passes']}",
        "",
        "## Key poses",
        "",
    ]
    lines += [f"- {p['name']}: {p['time']:.3f} s (frame {p['frame']})" for p in data["poses"]]
    lines += ["", "## Humanoid mapping", "", "| Role | Bone |", "|---|---|"]
    lines += [f"| {role} | {bone} |" for role, bone in data["rig_mapping"].items()]
    lines += ["", "## QA", ""]
    lines += [
        f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in data["qa"]["checks"].items()
    ]
    for name, value in data["qa"]["metrics"].items():
        if isinstance(value, (int, float)):
            lines.append(f"- {name}: {value:.6f}")
    lines += ["", "## Correction history", ""]
    for index, step in enumerate(data["passes"]):
        failed = [name for name, passed in step["qa"]["checks"].items() if not passed]
        lines.append(
            f"- Pass {index}: {', '.join(failed) if failed else 'all numerical checks passed'}"
        )
    lines += [
        "",
        "## Export verification",
        "",
        f"- SpearThrow clip: {data['export_validation']['duration']:.3f} s",
        f"- Moving bones: {len(data['export_validation']['moving_bones'])}",
        "- GLB decoded independently and reopened in a fresh Blender process.",
        "",
        "## Preview",
        "",
        f"Status: {data['preview'].get('status', 'not_requested')}",
        "Contact sheet (when requested): columns Ready, WindUp, Release, FollowThrough; "
        "rows three-quarter and side view.",
        "",
        "## Limitations",
        "",
    ]
    lines += [f"- {item}" for item in data["limitations"] + data["qa"]["limitations"]]
    return "\n".join(lines) + "\n"


def create_animation(
    source,
    description,
    directory,
    blender,
    *,
    duration=0.9,
    fps=50,
    preview=False,
    mapping=None,
    timeout=900,
):
    source = input_path(source)
    plan = make_plan(description, duration, fps)
    paths = output_paths(source, Path(directory))
    digest = sha256(source)
    directory = paths["model"].parent
    directory.mkdir(parents=True, exist_ok=True)
    # Reject concurrent writers, including ones using different character names.
    lock = directory / ".motion-director.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        output_paths(source, directory)
        with tempfile.TemporaryDirectory(prefix=".motion-director-", dir=directory) as temp:
            staged_model = Path(temp) / paths["model"].name
            job = {
                "operation": "animate",
                "input": str(source),
                "output": str(staged_model),
                "plan": plan,
                "mapping": mapping,
                "preview": preview,
            }
            result = run_blender(blender, job, timeout)
            if not result.get("exported"):
                failure = directory / "spear_throw_failed_qa.json"
                write_json(failure, result)
                raise ValueError(f"Pose QA failed after correction; diagnostic: {failure}")
            clip = validate_clip(staged_model, plan)
            # Reloading exercises skin, animation import, and sampled foot transforms.
            reloaded = run_blender(
                blender,
                {
                    "operation": "validate",
                    "input": str(staged_model),
                    "plan": plan,
                    "mapping": mapping,
                },
                timeout,
            )
            if not reloaded["qa"]["passed"]:
                write_json(directory / "spear_throw_failed_qa.json", reloaded)
                raise ValueError("Export round-trip pose QA failed; see spear_throw_failed_qa.json")
            clip["blender_roundtrip"] = reloaded["qa"]
            if sha256(source) != digest:
                raise RuntimeError("Input changed during generation; refusing to publish output")
            # Rewrite staged preview paths before publishing the artifacts.
            result = json.loads(
                json.dumps(result).replace(
                    str(Path(temp)).replace("\\", "\\\\"), str(directory).replace("\\", "\\\\")
                )
            )
            data = metadata(plan, source, digest, result, clip)
            write_json(Path(temp) / paths["metadata"].name, data)
            (Path(temp) / paths["report"].name).write_text(report_text(data), encoding="utf-8")
            job["output"] = str(paths["model"])
            write_json(Path(temp) / paths["job"].name, job)
            recipe = (
                '"""Reproduce this animation in Blender; requires motion_director on sys.path."""\n'
                "import json\nimport sys\nfrom pathlib import Path\n"
                f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})\n"
                "from motion_director.blender.entry import execute\n"
                f'job = json.loads(Path({str(paths["job"])!r}).read_text(encoding="utf-8"))\n'
                'if Path(job["output"]).exists():\n'
                '    raise FileExistsError("Choose a new output path in the job JSON first")\n'
                "execute(job)\n"
            )
            (Path(temp) / paths["recipe"].name).write_text(recipe, encoding="utf-8")
            artifacts = list(Path(temp).iterdir())
            for artifact in artifacts:
                destination = directory / artifact.name
                if destination.exists():
                    raise FileExistsError(f"Artifact already exists: {destination}")
            for artifact in artifacts:
                destination = directory / artifact.name
                artifact.rename(destination)
            return {
                "paths": {key: str(path) for key, path in paths.items() if path.exists()},
                "metadata": data,
            }
    finally:
        lock.unlink(missing_ok=True)
