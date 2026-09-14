import math

import bpy
from mathutils import Vector

from motion_director.blender.export_model import export_glb


def create_fixture(path, variant="standard"):
    """Original MIT-licensed, skinned articulated mannequin; no downloaded assets."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm_data = bpy.data.armatures.new("HumanoidRig")
    arm = bpy.data.objects.new("MotionDirectorMannequin", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    definitions = [
        ("Hips", (0, 0, 1.00), (0, 0, 1.15), None),
        ("Spine", (0, 0, 1.15), (0, 0, 1.35), "Hips"),
        ("Chest", (0, 0, 1.35), (0, 0, 1.53), "Spine"),
        ("Neck", (0, 0, 1.53), (0, 0, 1.64), "Chest"),
        ("Head", (0, 0, 1.64), (0, 0, 1.91), "Neck"),
    ]
    for side, sign in (("L", 1), ("R", -1)):
        definitions.extend(
            [
                (f"Shoulder.{side}", (sign * 0.05, 0, 1.51), (sign * 0.22, 0, 1.51), "Chest"),
                (
                    f"UpperArm.{side}",
                    (sign * 0.22, 0, 1.51),
                    (sign * 0.51, 0, 1.51),
                    f"Shoulder.{side}",
                ),
                (
                    f"LowerArm.{side}",
                    (sign * 0.51, 0, 1.51),
                    (sign * 0.77, 0, 1.51),
                    f"UpperArm.{side}",
                ),
                (
                    f"Hand.{side}",
                    (sign * 0.77, 0, 1.51),
                    (sign * 0.91, 0, 1.51),
                    f"LowerArm.{side}",
                ),
                (f"Thigh.{side}", (sign * 0.12, 0, 1.00), (sign * 0.13, -0.015, 0.56), "Hips"),
                (
                    f"Shin.{side}",
                    (sign * 0.13, -0.015, 0.56),
                    (sign * 0.13, 0, 0.12),
                    f"Thigh.{side}",
                ),
                (
                    f"Foot.{side}",
                    (sign * 0.13, 0, 0.12),
                    (sign * 0.13, -0.22, 0.08),
                    f"Shin.{side}",
                ),
            ]
        )
    renamed = {}
    for name, head, tail, parent in definitions:
        actual = f"mixamorig:{name}" if variant == "rolled" else name
        renamed[name] = actual
        bone = arm_data.edit_bones.new(actual)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = arm_data.edit_bones[renamed[parent]]
        if variant == "rolled":
            bone.roll = math.radians(53)
    bpy.ops.object.mode_set(mode="OBJECT")
    colors = {
        "body": (0.055, 0.20, 0.29, 1),
        "right": (0.94, 0.31, 0.10, 1),
        "left": (0.06, 0.58, 0.57, 1),
        "joint": (0.035, 0.055, 0.075, 1),
    }
    materials = {}
    for name, color in colors.items():
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = color
        mat.use_nodes = True
        mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color
        materials[name] = mat
    meshes = []

    def bind(obj, name, material):
        obj.data.materials.append(materials[material])
        obj.vertex_groups.new(name=renamed[name]).add(
            list(range(len(obj.data.vertices))), 1, "REPLACE"
        )
        meshes.append(obj)

    for name, head, tail, _ in definitions:
        start, end = Vector(head), Vector(tail)
        radius = (
            0.14
            if name in ("Hips", "Spine", "Chest")
            else 0.12
            if name == "Head"
            else 0.065
            if "Thigh" in name
            else 0.047
        )
        if name == "Neck" or "Shoulder" in name:
            radius = 0.05
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, location=(start + end) / 2)
        obj = bpy.context.object
        obj.name = name + "_skin"
        obj.scale = (radius, radius * 0.85, (end - start).length * 0.55)
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(end - start)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bind(
            obj, name, "right" if name.endswith(".R") else "left" if name.endswith(".L") else "body"
        )
        if name not in ("Head", "Hips"):
            bpy.ops.mesh.primitive_uv_sphere_add(
                segments=10, ring_count=6, radius=radius * 0.85, location=start
            )
            bind(bpy.context.object, name, "joint")
    # A forward-facing visor makes heading and head rotation easy to judge.
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, location=(0, -0.102, 1.79))
    visor = bpy.context.object
    visor.scale = (0.095, 0.025, 0.035)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bind(visor, "Head", "left")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    skin = bpy.context.object
    skin.name = "SkinnedMannequin"
    # Join preserves each part's rest transform; bake the combined object transform.
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    skin.parent = arm
    modifier = skin.modifiers.new("Skin", "ARMATURE")
    modifier.object = arm
    for polygon in skin.data.polygons:
        polygon.use_smooth = True
    if variant == "rolled":
        arm.rotation_euler.z = math.radians(37)
        arm.scale = (1.3, 1.3, 1.3)
    export_glb(path)
    return {"output": path, "bones": len(definitions), "license": "MIT", "variant": variant}
