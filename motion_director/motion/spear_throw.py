import math
import re

# Distances are fractions of arm length; body offsets are fractions of character height.
# Canonical coordinates: anatomical right, forward (throw direction), up.
POSES = [
    {
        "name": "Ready",
        "time": 0.00,
        "hips_yaw": -8,
        "chest_yaw": -8,
        "lean": 2,
        "shift": -0.006,
        "drop": 0.025,
        "hand": [0.48, 0.45, 0.05],
        "support": [-0.48, 0.46, -0.22],
        "pole": [1, -0.3, -0.2],
        "wrist": -10,
    },
    {
        "name": "Anticipation",
        "time": 0.16,
        "hips_yaw": -18,
        "chest_yaw": -18,
        "lean": -4,
        "shift": -0.025,
        "drop": 0.04,
        "hand": [0.48, -0.32, 0.38],
        "support": [-0.35, 0.76, 0.03],
        "pole": [1, -0.5, 0],
        "wrist": -18,
    },
    {
        "name": "WindUp",
        "time": 0.30,
        "hips_yaw": -22,
        "chest_yaw": -24,
        "lean": -7,
        "shift": -0.035,
        "drop": 0.045,
        "hand": [0.30, -0.48, 0.53],
        "support": [-0.22, 0.84, 0.08],
        "pole": [1, -0.4, -0.1],
        "wrist": -25,
    },
    {
        "name": "Drive",
        "time": 0.34,
        "hips_yaw": 12,
        "chest_yaw": -17,
        "lean": 1,
        "shift": 0.004,
        "drop": 0.03,
        "hand": [0.36, -0.23, 0.58],
        "support": [-0.50, 0.45, -0.13],
        "pole": [1, -0.25, -0.1],
        "wrist": -20,
    },
    {
        "name": "Release",
        "time": 0.38,
        "hips_yaw": 22,
        "chest_yaw": 10,
        "lean": 10,
        "shift": 0.03,
        "drop": 0.025,
        "hand": [0.08, 0.95, 0.17],
        "support": [-0.48, 0.16, -0.45],
        "pole": [1, 0, -0.6],
        "wrist": 8,
    },
    {
        "name": "FollowThrough",
        "time": 0.50,
        "hips_yaw": 25,
        "chest_yaw": 18,
        "lean": 15,
        "shift": 0.035,
        "drop": 0.035,
        "hand": [-0.48, 0.65, -0.46],
        "support": [-0.48, -0.12, -0.52],
        "pole": [0.7, 0.5, -0.8],
        "wrist": 22,
    },
    {
        "name": "Settle",
        "time": 0.66,
        "hips_yaw": 10,
        "chest_yaw": 6,
        "lean": 7,
        "shift": 0.01,
        "drop": 0.03,
        "hand": [-0.1, 0.56, -0.48],
        "support": [-0.5, 0.23, -0.40],
        "pole": [1, 0, -0.5],
        "wrist": 5,
    },
    {
        "name": "Recovery",
        "time": 0.90,
        "hips_yaw": -8,
        "chest_yaw": -8,
        "lean": 2,
        "shift": -0.006,
        "drop": 0.025,
        "hand": [0.48, 0.45, 0.05],
        "support": [-0.48, 0.46, -0.22],
        "pole": [1, -0.3, -0.2],
        "wrist": -10,
    },
]


def make_plan(description: str, duration: float = 0.9, fps: int = 50) -> dict:
    text = description.casefold()
    if not re.search(r"mızrak|mizrak|spear|javelin", text):
        raise ValueError(
            "Only spear throw is supported. Request 'mızrak fırlatma' or 'spear throw'."
        )
    if re.search(r"sol el|sol kol|left.hand|left.arm", text):
        raise ValueError("MVP supports right-handed spear throws only.")
    if not math.isfinite(duration) or not 0.6 <= duration <= 1.5 or not 24 <= fps <= 120:
        raise ValueError("Duration must be 0.6–1.5 seconds; fps must be 24–120")
    end = round(duration * fps)
    poses = [{**pose, "frame": round(pose["time"] / 0.9 * end)} for pose in POSES]
    if len({p["frame"] for p in poses}) != len(poses):
        raise ValueError("Timing collapses key poses; increase fps or duration")
    for pose in poses:
        pose["time"] = pose["frame"] / fps
    release = next(p for p in poses if p["name"] == "Release")
    return {
        "animation": "SpearThrow",
        "description": description,
        "fps": fps,
        "duration": end / fps,
        "frame_start": 0,
        "frame_end": end,
        "handedness": "right",
        "poses": poses,
        "events": [
            {"name": "projectile_release", "time": release["time"], "frame": release["frame"]}
        ],
        "interpolation": "smoothstep anticipation/recovery; linear drive/release; baked quaternion",
    }


def sample_pose(plan: dict, frame: int) -> dict:
    poses = plan["poses"]
    for start, end in zip(poses, poses[1:], strict=False):
        if start["frame"] <= frame <= end["frame"]:
            t = (frame - start["frame"]) / (end["frame"] - start["frame"])
            if start["name"] not in ("WindUp", "Drive", "Release"):
                t = t * t * (3 - 2 * t)
            result = {}
            for key in ("hips_yaw", "chest_yaw", "lean", "shift", "drop", "wrist"):
                result[key] = start[key] * (1 - t) + end[key] * t
            for key in ("hand", "support", "pole"):
                result[key] = [
                    a * (1 - t) + b * t for a, b in zip(start[key], end[key], strict=False)
                ]
            return result
    raise ValueError(f"Frame outside plan: {frame}")
