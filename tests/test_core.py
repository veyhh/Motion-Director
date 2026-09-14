import json
from pathlib import Path

import pytest

from motion_director.blender.locate import locate_blender, read_config
from motion_director.gltf import read_gltf
from motion_director.motion.spear_throw import make_plan, sample_pose
from motion_director.motion.validation import validate_plan
from motion_director.paths import input_path, output_paths, sha256
from motion_director.pipeline import metadata
from motion_director.rig.humanoid import REQUIRED, map_humanoid
from motion_director.rig.normalize import normalize_bone


@pytest.mark.parametrize(
    "name,expected",
    [
        ("mixamorig:Hips", "hips"),
        ("Armature|Hips", "hips"),
        ("mixamorig:RightArm", "arm.r"),
        ("mixamorigLeftForeArm", "forearm.l"),
        ("Bip01 R UpperArm", "upperarm.r"),
        ("Bip01_Pelvis", "pelvis"),
        ("UpperArm.L", "upperarm.l"),
        ("LowerArm.R", "lowerarm.r"),
        ("Bip01 L Calf", "calf.l"),
        ("LeftUpLeg", "upleg.l"),
    ],
)
def test_normalization(name, expected):
    assert normalize_bone(name) == expected


def bone_names():
    return ["Hips", "Spine", "Chest", "Head"] + [
        f"{part}.{side}"
        for side in ("L", "R")
        for part in ("UpperArm", "LowerArm", "Hand", "Thigh", "Shin", "Foot")
    ]


def test_humanoid_mapping():
    result = map_humanoid(bone_names())
    assert result["is_humanoid"]
    assert set(REQUIRED) <= result["mapping"].keys()
    assert result["mapping"]["upper_arm.r"] == "UpperArm.R"


def test_mixamo_mapping():
    names = ["Hips", "Spine", "Spine1", "Head"] + [
        f"{side}{part}"
        for side in ("Left", "Right")
        for part in ("Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot")
    ]
    assert map_humanoid([f"mixamorig:{n}" for n in names])["is_humanoid"]


def test_missing_rig_is_not_humanoid():
    result = map_humanoid(["Hips", "Spine", "Head"])
    assert not result["is_humanoid"]
    assert "hand.r" in result["missing"]


def test_ambiguous_mapping_requires_override():
    names = bone_names() + ["Armature|Hips"]
    assert not map_humanoid(names)["is_humanoid"]
    assert map_humanoid(names, {"hips": "Hips"})["is_humanoid"]


def test_invalid_override():
    with pytest.raises(ValueError, match="does not exist"):
        map_humanoid(bone_names(), {"hips": "missing"})
    with pytest.raises(ValueError, match="multiple"):
        map_humanoid(bone_names(), {"hips": "Head"})


def test_blender_override_and_config(tmp_path, monkeypatch):
    executable = tmp_path / "Blender 5.2" / "blender.exe"
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.setenv("MOTION_DIRECTOR_BLENDER", "invalid")
    assert locate_blender(str(executable)) == executable.resolve()
    monkeypatch.delenv("MOTION_DIRECTOR_BLENDER")
    assert locate_blender(config={"blender": str(executable)}) == executable.resolve()
    config = tmp_path / "config.toml"
    config.write_text(f"blender = '{executable}'", encoding="utf-8")
    assert read_config(config)["blender"] == str(executable)


def test_blender_environment(tmp_path, monkeypatch):
    path = tmp_path / "blender.exe"
    path.touch()
    monkeypatch.setenv("MOTION_DIRECTOR_BLENDER", str(path))
    assert locate_blender() == path.resolve()


def test_bad_explicit_blender_never_silently_falls_back(tmp_path):
    with pytest.raises(FileNotFoundError):
        locate_blender(str(tmp_path / "missing.exe"))


def test_windows_version_order(tmp_path, monkeypatch):
    import motion_director.blender.locate as module

    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    monkeypatch.delenv("MOTION_DIRECTOR_BLENDER", raising=False)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path))
    for version in ("4.9", "4.10", "4.2"):
        path = tmp_path / "Blender Foundation" / f"Blender {version}" / "blender.exe"
        path.parent.mkdir(parents=True)
        path.touch()
    assert "4.10" in str(locate_blender())


@pytest.mark.parametrize("duration,fps", [(0.9, 50), (0.8, 60), (1.2, 30), (0.6, 60)])
def test_timing(duration, fps):
    plan = make_plan("Güçlü bir mızrak fırlatma animasyonu yap", duration, fps)
    assert len(plan["poses"]) >= 6
    assert plan["events"][0]["time"] == plan["events"][0]["frame"] / fps
    assert plan["duration"] == plan["frame_end"] / fps
    assert sample_pose(plan, 0) == sample_pose(plan, plan["frame_end"])
    for pose in plan["poses"]:
        assert sample_pose(plan, pose["frame"])["hand"] == pytest.approx(pose["hand"])


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), -1, 0, 6])
def test_bad_duration(duration):
    with pytest.raises(ValueError):
        make_plan("spear throw", duration)


def test_collapsed_timing_rejected():
    with pytest.raises(ValueError, match="collapses"):
        make_plan("spear throw", 0.6, 24)


@pytest.mark.parametrize(
    "prompt", ["sword attack", "walk", "sol elle mızrak at", "left-hand spear throw"]
)
def test_unsupported_request(prompt):
    with pytest.raises(ValueError):
        make_plan(prompt)


def test_path_safety(tmp_path):
    source = tmp_path / "character.glb"
    source.write_bytes(b"original")
    before = sha256(source)
    paths = output_paths(source, tmp_path / "output")
    assert paths["model"] != source
    assert paths["model"].name == "character_spear_throw.glb"
    paths["model"].parent.mkdir()
    paths["model"].write_bytes(b"old animation")
    with pytest.raises(FileExistsError):
        output_paths(source, tmp_path / "output")
    assert sha256(source) == before


def test_symlink_input_safety(tmp_path):
    source = tmp_path / "input.glb"
    source.touch()
    output = tmp_path / "input_spear_throw.glb"
    try:
        output.symlink_to(source)
    except OSError:
        pytest.skip("Creating symlinks requires Windows Developer Mode")
    with pytest.raises(ValueError, match="overwrite"):
        output_paths(source, tmp_path)


def test_unsupported_input(tmp_path):
    source = tmp_path / "character.fbx"
    source.touch()
    with pytest.raises(ValueError, match=".glb"):
        input_path(source)


def test_metadata_generation():
    plan = make_plan("spear throw")
    result = {
        "inspection": {"rigs": [{"mapping": {"hips": "Hips"}}]},
        "qa": {"passed": True},
        "passes": [{}, {}],
    }
    data = metadata(plan, Path("input.glb"), "abc", result, {"passed": True})
    assert data["events"] == [{"name": "projectile_release", "time": 0.38, "frame": 19}]
    assert data["correction_passes"] == 1
    assert data["rig_mapping"] == {"hips": "Hips"}
    assert json.loads(json.dumps(data))["animation"] == "SpearThrow"


@pytest.mark.parametrize("field,value", [("name", "wrong_event"), ("time", 0.2), ("frame", 90)])
def test_invalid_event_metadata(field, value):
    plan = make_plan("spear throw")
    validate_plan(plan)
    plan["events"][0][field] = value
    with pytest.raises(ValueError):
        validate_plan(plan)


@pytest.mark.parametrize("data", [b"", b"glTF", b"glTF" + b"\0" * 40])
def test_reject_corrupt_glb(tmp_path, data):
    path = tmp_path / "bad.glb"
    path.write_bytes(data)
    with pytest.raises(ValueError):
        read_gltf(path)
