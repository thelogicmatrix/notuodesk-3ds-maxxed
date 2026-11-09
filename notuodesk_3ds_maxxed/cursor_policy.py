"""Keep the 3D cursor out of the 3ds Max workspace."""

import bpy
from bpy.app.handlers import persistent

from .operators import WS_NAME


def reset_scene(scene):
    if scene.cursor.location.length_squared:
        scene.cursor.location = (0, 0, 0)
    if any(scene.cursor.rotation_euler):
        scene.cursor.rotation_euler = (0, 0, 0)


def enforce():
    """Cover new editors and scene switches without rebuilding the layout."""
    ws = bpy.data.workspaces.get(WS_NAME)
    if ws is not None:
        for screen in ws.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if space.type == "VIEW_3D" and space.overlay.show_cursor:
                        space.overlay.show_cursor = False
                        area.tag_redraw()
        for wm in bpy.data.window_managers:
            for window in wm.windows:
                if window.workspace == ws:
                    reset_scene(window.scene)
    return 0.2


@persistent
def on_load(_):
    enforce()


def register():
    if on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load)
    if not bpy.app.background and not bpy.app.timers.is_registered(enforce):
        bpy.app.timers.register(enforce, first_interval=0.2, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(enforce):
        bpy.app.timers.unregister(enforce)
    if on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load)
