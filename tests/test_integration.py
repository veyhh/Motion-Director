import json
import subprocess
import sys

import pytest

from motion_director.blender.locate import locate_blender, read_config
from motion_director.blender.runner import run_blender
from motion_director.gltf import read_gltf, validate_clip
from motion_director.motion.spear_throw import make_plan
from motion_director.paths import sha256

pytestmark = pytest.mark.integration
PROMPT = "Bu karakter için güçlü bir mızrak fırlatma animasyonu yap."


@pytest.fixture(scope="module")
def blender():
    try:
        return locate_blender(config=read_config())
    except FileNotFoundError:
        pytest.skip("Real Blender not installed; set MOTION_DIRECTOR_BLENDER")


@pytest.fixture(scope="module")
def humanoid(tmp_path_factory, blender):
    path = tmp_path_factory.mktemp("rigged humanoid") / "karakter.glb"
    run_blender(blender, {"operation": "fixture", "output": str(path)})
    return path


@pytest.mark.parametrize("variant,fps", [("standard", 50), ("rolled", 30), ("gltf", 50)])
def test_real_cli_animation(tmp_path, blender, humanoid, variant, fps):
    source = humanoid
    if variant == "rolled":
        source = tmp_path / "rolled.glb"
        run_blender(blender, {"operation": "fixture", "output": str(source), "variant": variant})
    elif variant == "gltf":
        document, buffers = read_gltf(humanoid)
        document["buffers"][0]["uri"] = "character.bin"
        (tmp_path / "character.bin").write_bytes(buffers[0])
        source = tmp_path / "character.gltf"
        source.write_text(json.dumps(document), encoding="utf-8")
    digest = sha256(source)
    source_doc, _ = read_gltf(source)
    assert not source_doc.get("animations")
    directory = tmp_path / "animation output"
    command = [
        sys.executable,
        "-m",
        "motion_director",
        "create-animation",
        str(source),
        PROMPT,
        "--blender",
        str(blender),
        "--output",
        str(directory),
        "--fps",
        str(fps),
    ]
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert process.returncode == 0, process.stderr
    output = directory / f"{source.stem}_spear_throw.glb"
    assert output.is_file() and output.stat().st_size > 1000
    data = json.loads((directory / "spear_throw.motion.json").read_text(encoding="utf-8"))
    clip = validate_clip(output, data)
    assert clip["duration"] == pytest.approx(0.9, abs=0.001)
    assert len(clip["moving_bones"]) >= 15
    assert data["qa"]["passed"]
    assert data["export_validation"]["blender_roundtrip"]["passed"]
    assert data["events"][0]["name"] == "projectile_release"
    assert data["input_sha256"] == digest == sha256(source)
    assert (directory / "spear_throw_report.md").is_file()
    recipe = directory / "spear_throw.blender.py"
    compile(recipe.read_text(encoding="utf-8"), str(recipe), "exec")
    validation = subprocess.run(
        [
            sys.executable,
            "-m",
            "motion_director",
            "validate",
            str(output),
            "--blender",
            str(blender),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert validation.returncode == 0, validation.stderr
    # Reruns must not destroy existing exports.
    old_output = sha256(output)
    rerun = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert rerun.returncode == 1 and sha256(output) == old_output


def test_real_self_correction(tmp_path, blender, humanoid):
    plan = make_plan(PROMPT)
    windup = next(p for p in plan["poses"] if p["name"] == "WindUp")
    windup["hips_yaw"], windup["chest_yaw"] = 82, 0
    result = run_blender(
        blender,
        {
            "operation": "animate",
            "input": str(humanoid),
            "output": str(tmp_path / "corrected.glb"),
            "plan": plan,
        },
    )
    assert len(result["passes"]) == 2
    assert not result["passes"][0]["qa"]["checks"]["torso_rotation"]
    assert result["qa"]["passed"] and result["exported"]
    assert validate_clip(tmp_path / "corrected.glb")["passed"]


def test_real_unrigged_rejected(tmp_path, blender):
    source = tmp_path / "empty.gltf"
    source.write_text(
        json.dumps({"asset": {"version": "2.0"}, "scenes": [{"nodes": []}], "scene": 0}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="one armature"):
        run_blender(
            blender,
            {
                "operation": "animate",
                "input": str(source),
                "output": str(tmp_path / "bad.glb"),
                "plan": make_plan(PROMPT),
            },
        )
    assert not (tmp_path / "bad.glb").exists()


def test_real_background_doctor(blender):
    result = run_blender(blender, {"operation": "doctor"})
    assert result["background"] and result["bpy"]
    assert result["version_tuple"][0] >= 4
