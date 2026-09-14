import bpy


def export_glb(path: str):
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_frame_range=True,
        export_force_sampling=True,
        export_frame_step=1,
        export_optimize_animation_size=False,
        export_skins=True,
        export_cameras=False,
        export_lights=False,
        export_extras=True,
    )
