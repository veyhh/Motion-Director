"""Executed by Blender, including when the package is installed in another Python."""

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def execute(job):
    import bpy

    from motion_director.blender.inspect_model import inspect_scene, load_model, require_humanoid

    if job["operation"] == "doctor":
        return {
            "version": bpy.app.version_string,
            "background": bpy.app.background,
            "bpy": True,
            "version_tuple": list(bpy.app.version),
        }
    if job["operation"] == "fixture":
        from motion_director.blender.fixture import create_fixture

        if Path(job["output"]).exists():
            raise FileExistsError("Fixture output already exists")

        return create_fixture(job["output"], job.get("variant", "standard"))
    if job["operation"] == "animate":
        output = Path(job["output"]).resolve()
        if output == Path(job["input"]).resolve() or output.exists():
            raise FileExistsError("Animation output must be a new path, different from the input")
    if job["operation"] in ("animate", "validate"):
        from motion_director.motion.validation import validate_plan

        validate_plan(job["plan"])
    load_model(job["input"], job.get("plan", {}).get("fps", 50))
    inspection = inspect_scene(job.get("mapping"))
    if job["operation"] == "inspect":
        return inspection
    arm, mapping = require_humanoid(inspection)
    from motion_director.qa.poses import validate_poses

    if job["operation"] == "validate":
        return {"inspection": inspection, "qa": validate_poses(arm, mapping, job["plan"])}
    if job["operation"] != "animate":
        raise ValueError("Unknown operation")
    from motion_director.blender.animate import generate
    from motion_director.blender.export_model import export_glb

    passes = []
    for correction in range(2):
        generated = generate(arm, mapping, job["plan"], correction)
        qa = validate_poses(arm, mapping, job["plan"])
        passes.append({"generation": generated, "qa": qa})
        if qa["passed"]:
            break
    if not qa["passed"]:
        return {"inspection": inspection, "passes": passes, "qa": qa, "exported": False}
    export_glb(job["output"])
    preview = {"status": "not_requested"}
    if job.get("preview"):
        try:
            from motion_director.blender.preview import render_preview

            preview = render_preview(arm, mapping, job["plan"], Path(job["output"]).parent)
        except Exception as error:
            preview = {"status": "failed", "reason": str(error)}
    return {
        "inspection": inspection,
        "passes": passes,
        "qa": qa,
        "exported": True,
        "preview": preview,
    }


if __name__ == "__main__":
    request, response = map(Path, sys.argv[sys.argv.index("--") + 1 :])
    try:
        result = execute(json.loads(request.read_text(encoding="utf-8")))
        response.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        response.write_text(
            json.dumps({"error": str(exc), "traceback": traceback.format_exc()}), encoding="utf-8"
        )
        raise
