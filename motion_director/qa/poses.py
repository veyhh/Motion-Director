import math

import bpy

from motion_director.blender.animate import axes


def angle(a, b):
    return math.degrees(a.angle(b)) if a.length > 1e-9 and b.length > 1e-9 else 0


def validate_poses(arm, mapping, plan):
    right, forward, up, height = axes(arm, mapping)
    baseline, baseline_tail, previous = {}, {}, {}
    max_slide = max_lift = max_jump = max_twist = max_head_turn = max_shoulder_lift = 0.0
    min_elbow, max_elbow = 180.0, 0.0
    nonfinite, scale_errors = [], []
    activity = {role: 0.0 for role in mapping}
    first_rot = {}
    release_extension = 0.0
    release_frame = plan["events"][0]["frame"]
    for frame in range(plan["frame_end"] + 1):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        for role, name in mapping.items():
            bone = arm.pose.bones[name]
            values = [v for row in bone.matrix for v in row]
            if not all(math.isfinite(v) for v in values):
                nonfinite.append(f"{name}@{frame}")
            if max(abs(v - 1) for v in bone.scale) > 0.02:
                scale_errors.append(f"{name}@{frame}")
            quat = bone.rotation_quaternion.normalized()
            first_rot.setdefault(role, quat.copy())
            activity[role] = max(
                activity[role], math.degrees(first_rot[role].rotation_difference(quat).angle)
            )
            if role in previous:
                dot = min(1.0, abs(quat.dot(previous[role])))
                max_jump = max(max_jump, math.degrees(2 * math.acos(dot)))
            previous[role] = quat.copy()
        for side in ("l", "r"):
            foot = arm.pose.bones[mapping[f"foot.{side}"]]
            baseline.setdefault(side, foot.head.copy())
            baseline_tail.setdefault(side, foot.tail.copy())
            for point, initial in ((foot.head, baseline[side]), (foot.tail, baseline_tail[side])):
                delta = point - initial
                max_slide = max(max_slide, (delta - up * delta.dot(up)).length / height)
                max_lift = max(max_lift, abs(delta.dot(up)) / height)
            shoulder, elbow, wrist = [
                arm.pose.bones[mapping[f"{r}.{side}"]].head.copy()
                for r in ("upper_arm", "lower_arm", "hand")
            ]
            bend = angle(shoulder - elbow, wrist - elbow)
            max_shoulder_lift = max(max_shoulder_lift, angle(elbow - shoulder, -up))
            min_elbow, max_elbow = min(min_elbow, bend), max(max_elbow, bend)
            if frame == release_frame and side == "r":
                release_extension = (wrist - shoulder).length / (
                    (elbow - shoulder).length + (wrist - elbow).length
                )
        chest = arm.pose.bones[mapping.get("chest", mapping["spine"])].matrix.to_quaternion()
        rest = arm.data.bones[mapping.get("chest", mapping["spine"])].matrix_local.to_quaternion()
        rotated = (chest @ rest.inverted()) @ forward
        max_twist = max(
            max_twist, abs(math.degrees(math.atan2(rotated.dot(right), rotated.dot(forward))))
        )
        head = arm.pose.bones[mapping["head"]]
        head_delta = head.matrix.to_quaternion() @ head.bone.matrix_local.to_quaternion().inverted()
        max_head_turn = max(max_head_turn, angle(head_delta @ forward, forward))
    checks = {
        "finite_transforms": not nonfinite,
        "unit_bone_scale": not scale_errors,
        "elbow_range": min_elbow >= 12 and max_elbow <= 177,
        "release_arm_extension": 0.85 <= release_extension <= 0.99,
        "torso_rotation": max_twist <= 75,
        "head_facing": max_head_turn <= 70,
        "shoulder_elevation": max_shoulder_lift <= 150,
        "foot_stability": max_slide <= 0.012 and max_lift <= 0.012,
        "rotation_continuity": max_jump <= 125,
        "whole_body_participation": all(
            activity[r] > 1
            for r in (
                "hips",
                "spine",
                "upper_arm.r",
                "lower_arm.r",
                "upper_arm.l",
                "lower_arm.l",
                "thigh.l",
                "thigh.r",
                "shin.l",
                "shin.r",
            )
        ),
        "duration": 0.6 <= plan["duration"] <= 1.5,
        "release_timing": 0 < release_frame < plan["frame_end"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "elbow_min_degrees": min_elbow,
            "elbow_max_degrees": max_elbow,
            "release_arm_extension_ratio": release_extension,
            "max_torso_yaw_degrees": max_twist,
            "max_head_turn_degrees": max_head_turn,
            "max_shoulder_elevation_degrees": max_shoulder_lift,
            "max_foot_slide_height_fraction": max_slide,
            "max_foot_lift_height_fraction": max_lift,
            "max_frame_rotation_degrees": max_jump,
            "bone_activity_degrees": activity,
        },
        "anomalies": nonfinite + scale_errors,
        "limitations": [
            "Mesh self-intersection and shoulder skin deformation need visual review.",
            "Foot checks measure drift from the planted first pose, not arbitrary scene terrain.",
        ],
    }
