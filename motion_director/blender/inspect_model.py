import bpy

from motion_director.rig.humanoid import map_humanoid


def load_model(path: str, fps=50):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = fps
    bpy.ops.import_scene.gltf(filepath=path)


def inspect_scene(overrides=None) -> dict:
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    rigs = []
    for arm in armatures:
        bound = [
            obj.name
            for obj in bpy.context.scene.objects
            if obj.type == "MESH"
            and any(mod.type == "ARMATURE" and mod.object == arm for mod in obj.modifiers)
        ]
        weighted = [
            obj.name
            for obj in bpy.context.scene.objects
            if obj.name in bound and any(v.groups for v in obj.data.vertices)
        ]
        mapped = map_humanoid([b.name for b in arm.data.bones], overrides)
        hierarchy_errors = []
        mapping = mapped["mapping"]
        for side in ("l", "r"):
            for chain in (("upper_arm", "lower_arm", "hand"), ("thigh", "shin", "foot")):
                for parent, child in zip(chain, chain[1:], strict=False):
                    p, c = mapping.get(f"{parent}.{side}"), mapping.get(f"{child}.{side}")
                    if p and c and arm.data.bones[p] not in arm.data.bones[c].parent_recursive:
                        hierarchy_errors.append(f"{c} must descend from {p}")
        rigs.append(
            {
                "name": arm.name,
                "bone_count": len(arm.data.bones),
                "roots": [b.name for b in arm.data.bones if not b.parent],
                "bound_meshes": bound,
                "weighted_meshes": weighted,
                "hierarchy_errors": hierarchy_errors,
                "bones": [
                    {
                        "name": b.name,
                        "parent": b.parent.name if b.parent else None,
                        "length": b.length,
                    }
                    for b in arm.data.bones
                ],
                **mapped,
            }
        )
    return {
        "armature_count": len(rigs),
        "rigs": rigs,
        "existing_animations": [a.name for a in bpy.data.actions],
        "mesh_count": sum(o.type == "MESH" for o in bpy.context.scene.objects),
    }


def require_humanoid(inspection: dict):
    if inspection["armature_count"] != 1:
        raise ValueError("Exactly one armature is required; select/export a single character")
    rig = inspection["rigs"][0]
    if not rig["is_humanoid"]:
        raise ValueError(
            f"Incomplete humanoid mapping: missing={rig['missing']}, "
            f"ambiguous={rig['ambiguous']}. Use --mapping JSON overrides."
        )
    if not rig["weighted_meshes"]:
        raise ValueError("No skinned mesh with vertex weights is bound to the armature")
    if rig["hierarchy_errors"]:
        raise ValueError("Unsupported hierarchy: " + "; ".join(rig["hierarchy_errors"]))
    arm = bpy.data.objects[rig["name"]]
    scale = arm.matrix_world.to_scale()
    if min(scale) <= 0 or max(scale) / min(scale) > 1.01 or arm.matrix_world.determinant() <= 0:
        raise ValueError("Armature needs positive uniform object scale")
    return arm, rig["mapping"]
