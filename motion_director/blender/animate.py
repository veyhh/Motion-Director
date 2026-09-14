import math

import bpy
from mathutils import Matrix, Quaternion, Vector

from motion_director.motion.spear_throw import sample_pose


def axes(arm, mapping):
    bones = arm.data.bones
    right = (
        bones[mapping["upper_arm.r"]].head_local - bones[mapping["upper_arm.l"]].head_local
    ).normalized()
    up = (bones[mapping["head"]].head_local - bones[mapping["hips"]].head_local).normalized()
    right = (right - up * right.dot(up)).normalized()
    forward = up.cross(right).normalized()
    height = (
        bones[mapping["head"]].tail_local
        - (bones[mapping["foot.l"]].head_local + bones[mapping["foot.r"]].head_local) / 2
    ).dot(up)
    if height <= 1e-5 or right.length < 0.9:
        raise ValueError("Degenerate humanoid rest geometry")
    return right, forward, up, height


def update():
    bpy.context.view_layer.update()


def two_bone_joint(start, target, length_a, length_b, pole):
    """Small analytic two-segment solver, no rig constraints or general IK system."""
    delta = target - start
    distance = delta.length
    if min(length_a, length_b, distance) < 1e-8:
        raise ValueError("Degenerate limb length or target")
    direction = delta.normalized()
    reach = min(max(distance, abs(length_a - length_b) + 1e-5), (length_a + length_b) * 0.985)
    along = (length_a**2 - length_b**2 + reach**2) / (2 * reach)
    perpendicular = pole - direction * pole.dot(direction)
    if perpendicular.length < 1e-6:
        perpendicular = direction.orthogonal()
    joint = (
        start
        + direction * along
        + perpendicular.normalized() * math.sqrt(max(0, length_a**2 - along**2))
    )
    return joint, start + direction * reach, abs(reach - distance)


def aim(bone, rest_direction, direction):
    if direction.length < 1e-8:
        raise ValueError(f"Zero-length aim direction: {bone.name}")
    rotation = rest_direction.rotation_difference(direction.normalized())
    orientation = rotation @ bone.bone.matrix_local.to_quaternion()
    bone.matrix = Matrix.LocRotScale(bone.head.copy(), orientation, Vector((1, 1, 1)))
    update()


def local_delta(bone, rotation):
    rest = bone.bone.matrix_local.to_quaternion()
    bone.rotation_quaternion = rest.inverted() @ rotation @ rest
    update()


def fcurves(action):
    if hasattr(action, "layers") and len(action.layers):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    yield from bag.fcurves
    elif hasattr(action, "fcurves"):
        yield from action.fcurves


def generate(arm, mapping, plan, correction=0):
    right, forward, up, height = axes(arm, mapping)

    def canonical(values):
        return right * values[0] + forward * values[1] + up * values[2]

    # Clear imported animation bindings only in the disposable Blender process.
    for obj in bpy.context.scene.objects:
        obj.animation_data_clear()
        if obj.type == "MESH" and obj.data.shape_keys:
            obj.data.shape_keys.animation_data_clear()
    for old in list(bpy.data.actions):
        bpy.data.actions.remove(old)
    arm.animation_data_create()
    action = bpy.data.actions.new("SpearThrow")
    arm.animation_data.action = action
    arm.data.pose_position = "POSE"
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="POSE")
    pb = arm.pose.bones
    for bone in pb:
        if bone.constraints:
            raise ValueError("Imported pose constraints are not supported")
        bone.rotation_mode = "QUATERNION"
        bone.matrix_basis.identity()
    update()
    rest_heads = {role: arm.data.bones[name].head_local.copy() for role, name in mapping.items()}
    anchors = {}
    for side in ("l", "r"):
        # A fixed split stance; no moving root and no sliding foot targets.
        anchors[side] = rest_heads[f"foot.{side}"] + forward * height * (
            0.065 if side == "l" else -0.065
        )
    scene = bpy.context.scene
    scene.render.fps = plan["fps"]
    scene.frame_start, scene.frame_end = 0, plan["frame_end"]
    for event in plan["events"]:
        scene.timeline_markers.new(event["name"], frame=event["frame"])
    previous = {}
    max_reach_error = 0
    for frame in range(plan["frame_end"] + 1):
        scene.frame_set(frame)
        for bone in pb:
            bone.matrix_basis.identity()
        update()
        pose = sample_pose(plan, frame)
        attenuation = 0.7 if correction else 1.0
        hips = pb[mapping["hips"]]
        offset = forward * pose["shift"] * height * attenuation - up * pose["drop"] * height
        # Pose location is expressed in the bone rest basis.
        hips.location = hips.bone.matrix_local.to_3x3().inverted() @ offset
        local_delta(hips, Quaternion(up, math.radians(pose["hips_yaw"] * attenuation)))
        spine_roles = [role for role in ("spine", "chest") if role in mapping]
        for role in spine_roles:
            rotation = Quaternion(
                up, math.radians(pose["chest_yaw"] * attenuation / len(spine_roles))
            ) @ Quaternion(right, math.radians(-pose["lean"] / len(spine_roles)))
            local_delta(pb[mapping[role]], rotation)
        for role in ("neck", "head"):
            if role in mapping:
                local_delta(
                    pb[mapping[role]],
                    Quaternion(
                        up,
                        math.radians(
                            -(pose["hips_yaw"] + pose["chest_yaw"])
                            * attenuation
                            * (0.25 if role == "neck" else 0.45)
                        ),
                    ),
                )
        for side in ("l", "r"):
            if f"shoulder.{side}" in mapping:
                local_delta(
                    pb[mapping[f"shoulder.{side}"]],
                    Quaternion(
                        up, math.radians(pose["chest_yaw"] * 0.12 * (1 if side == "r" else -1))
                    ),
                )
            upper, lower, hand = [
                pb[mapping[f"{role}.{side}"]] for role in ("upper_arm", "lower_arm", "hand")
            ]
            a = (rest_heads[f"lower_arm.{side}"] - rest_heads[f"upper_arm.{side}"]).length
            b = (rest_heads[f"hand.{side}"] - rest_heads[f"lower_arm.{side}"]).length
            values = pose["hand"] if side == "r" else pose["support"]
            target = upper.head + canonical(values) * (a + b) * (0.96 if correction else 1)
            pole = canonical(pose["pole"] if side == "r" else [-1, 0, -0.5])
            joint, endpoint, _ = two_bone_joint(upper.head.copy(), target, a, b, pole)
            aim(
                upper,
                (rest_heads[f"lower_arm.{side}"] - rest_heads[f"upper_arm.{side}"]).normalized(),
                joint - upper.head,
            )
            aim(
                lower,
                (rest_heads[f"hand.{side}"] - rest_heads[f"lower_arm.{side}"]).normalized(),
                endpoint - lower.head,
            )
            # Keep the hand aligned with the forearm and add a small local wrist snap.
            local_delta(hand, Quaternion(right, math.radians(pose["wrist"] if side == "r" else 0)))
        for side in ("l", "r"):
            thigh, shin, foot = [
                pb[mapping[f"{role}.{side}"]] for role in ("thigh", "shin", "foot")
            ]
            a = (rest_heads[f"shin.{side}"] - rest_heads[f"thigh.{side}"]).length
            b = (rest_heads[f"foot.{side}"] - rest_heads[f"shin.{side}"]).length
            joint, target, error = two_bone_joint(thigh.head.copy(), anchors[side], a, b, forward)
            max_reach_error = max(max_reach_error, error / height)
            aim(
                thigh,
                (rest_heads[f"shin.{side}"] - rest_heads[f"thigh.{side}"]).normalized(),
                joint - thigh.head,
            )
            aim(
                shin,
                (rest_heads[f"foot.{side}"] - rest_heads[f"shin.{side}"]).normalized(),
                target - shin.head,
            )
            foot.matrix = Matrix.LocRotScale(
                foot.head.copy(), foot.bone.matrix_local.to_quaternion(), Vector((1, 1, 1))
            )
            update()
        for bone in pb:
            # Quaternion signs are equivalent geometrically, but must be continuous for glTF.
            quat = bone.rotation_quaternion.copy().normalized()
            if bone.name in previous and quat.dot(previous[bone.name]) < 0:
                quat.negate()
            bone.rotation_quaternion = quat
            previous[bone.name] = quat.copy()
            bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=bone.name)
            bone.keyframe_insert(data_path="location", frame=frame, group=bone.name)
    for curve in fcurves(action):
        for key in curve.keyframe_points:
            key.interpolation = "LINEAR"
    bpy.ops.object.mode_set(mode="OBJECT")
    scene.frame_set(0)
    return {
        "action": action.name,
        "baked_frames": plan["frame_end"] + 1,
        "keyframe_channels": sum(1 for _ in fcurves(action)),
        "max_leg_reach_error_fraction": max_reach_error,
        "correction_pass": correction,
    }
