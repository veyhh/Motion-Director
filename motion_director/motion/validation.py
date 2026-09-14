import math


def validate_plan(plan):
    """Reject contradictory event/frame metadata instead of validating the wrong pose."""
    if plan.get("animation") != "SpearThrow":
        raise ValueError("Motion metadata must describe SpearThrow")
    fps, end, duration = plan["fps"], plan["frame_end"], plan["duration"]
    if not isinstance(fps, int) or not 24 <= fps <= 120:
        raise ValueError("Invalid metadata FPS")
    if not isinstance(end, int) or end <= 0 or plan.get("frame_start") != 0:
        raise ValueError("Invalid metadata frame range")
    if not math.isfinite(duration) or abs(duration - end / fps) > 1e-6:
        raise ValueError("Metadata duration and frame range disagree")
    events = [e for e in plan["events"] if e.get("name") == "projectile_release"]
    if len(events) != 1:
        raise ValueError("Exactly one projectile_release event is required")
    event = events[0]
    frame, time = event["frame"], event["time"]
    if not isinstance(frame, int) or not 0 < frame < end:
        raise ValueError("Release frame is outside the animation")
    if not math.isfinite(time) or abs(time - frame / fps) > 1e-6:
        raise ValueError("Release time and frame disagree")
    release = [p for p in plan["poses"] if p["name"] == "Release"]
    if len(release) != 1 or release[0]["frame"] != frame:
        raise ValueError("Release event does not coincide with the release pose")
