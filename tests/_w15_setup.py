"""Isolated W1.5 installation, without wave 2 host edits."""
import addon_utils
import bpy

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
from notuodesk_3ds_maxxed import max_layers, scene_explorer

max_layers.install()
scene_explorer.install()


def empty_scene():
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def box(name):
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    obj.name = name
    return obj
