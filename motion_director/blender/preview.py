from pathlib import Path

import bpy
from mathutils import Vector

from motion_director.blender.animate import axes


def render_preview(arm, mapping, plan, directory: Path):
    scene = bpy.context.scene
    right, forward, up, height = axes(arm, mapping)
    transform = arm.matrix_world
    center = transform @ (arm.data.bones[mapping["hips"]].head_local + up * height * 0.03)
    world_up = (transform.to_3x3() @ up).normalized()
    world_forward = (transform.to_3x3() @ forward).normalized()
    world_right = (transform.to_3x3() @ right).normalized()
    height *= transform.to_scale().length / (3**0.5)
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = height * 1.65
    camera.data.lens = 50
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    scene.world = bpy.data.worlds.new("PreviewWorld")
    scene.world.color = (0.055, 0.07, 0.09)
    scene.render.resolution_x = scene.render.resolution_y = 384
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    # Neutral floor is a preview object only: the GLB has already been exported.
    scene.frame_set(0)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ground_height = float("inf")
    for obj in scene.objects:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        for vertex in mesh.vertices:
            ground_height = min(ground_height, (evaluated.matrix_world @ vertex.co).dot(world_up))
        evaluated.to_mesh_clear()
    ground = center + world_up * (ground_height - center.dot(world_up))
    bpy.ops.mesh.primitive_plane_add(size=height * 6, location=ground)
    floor = bpy.context.object
    floor.rotation_mode = "QUATERNION"
    floor.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(world_up)
    floor_mat = bpy.data.materials.new("PreviewFloor")
    floor_mat.diffuse_color = (0.16, 0.19, 0.23, 1)
    floor.data.materials.append(floor_mat)
    bpy.ops.object.light_add(type="AREA", location=center + world_up * height * 3)
    bpy.context.object.data.energy = 700
    bpy.context.object.data.shape = "DISK"
    bpy.context.object.data.size = height * 3

    def view(side):
        camera.location = (
            center
            + (
                world_forward * (2.6 if side == 0 else 0.4)
                + world_right * (2.4 if side == 0 else 3.2)
                + world_up * 0.9
            )
            * height
        )
        camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()

    # Contact sheet: ready, wind-up, release, follow-through; two fixed viewpoints.
    selected = [
        p for p in plan["poses"] if p["name"] in ("Ready", "WindUp", "Release", "FollowThrough")
    ]
    tiles = directory / "preview_poses"
    tiles.mkdir(exist_ok=True)
    import numpy as np  # Bundled with Blender; not a system Python dependency.

    sheet = np.zeros((768, 1536, 4), dtype=np.float32)
    files = []
    for row in range(2):
        view(row)
        for column, pose in enumerate(selected):
            scene.frame_set(pose["frame"])
            target = tiles / f"view{row}_{pose['name']}.png"
            scene.render.filepath = str(target)
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(str(target), check_existing=False)
            pixels = np.empty(384 * 384 * 4, dtype=np.float32)
            img.pixels.foreach_get(pixels)
            sheet[(1 - row) * 384 : (2 - row) * 384, column * 384 : (column + 1) * 384] = (
                pixels.reshape(384, 384, 4)
            )
            bpy.data.images.remove(img)
            files.append(str(target))
    contact = bpy.data.images.new("SpearThrow contact sheet", width=1536, height=768)
    contact.pixels.foreach_set(sheet.ravel())
    contact.filepath_raw = str(directory / "spear_throw_poses.png")
    contact.file_format = "PNG"
    contact.save()
    view(0)
    video_path = directory / "spear_throw_preview.mp4"
    try:
        if hasattr(scene.render.image_settings, "media_type"):
            scene.render.image_settings.media_type = "VIDEO"
        else:
            scene.render.image_settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
        scene.render.filepath = str(video_path)
        bpy.ops.render.render(animation=True)
        if not video_path.is_file():
            raise RuntimeError("Blender did not write the expected MP4")
        return {
            "status": "mp4",
            "video": str(video_path),
            "contact_sheet": contact.filepath_raw,
            "pose_images": files,
        }
    except (TypeError, RuntimeError) as error:
        if hasattr(scene.render.image_settings, "media_type"):
            scene.render.image_settings.media_type = "IMAGE"
        scene.render.image_settings.file_format = "PNG"
        sequence = directory / "preview_frames"
        sequence.mkdir(exist_ok=True)
        scene.render.filepath = str(sequence / "frame_")
        bpy.ops.render.render(animation=True)
        return {
            "status": "png_sequence",
            "reason": str(error),
            "sequence": str(sequence),
            "contact_sheet": contact.filepath_raw,
            "pose_images": files,
        }
