"""Run with an isolated Blender profile:

blender -b --factory-startup --python-exit-code 1 --python tests/test_line_tool.py
"""

import addon_utils
import bpy
import math
from mathutils import Vector


addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
assert hasattr(bpy.types.WindowManager, "max_line"), "Line Keyboard Entry is missing"

settings = bpy.context.window_manager.max_line
assert settings.initial_type == "CORNER"
assert settings.drag_type == "BEZIER"


def add(co):
    settings.x, settings.y, settings.z = co
    assert bpy.ops.max.line_keyboard(action="ADD") == {"FINISHED"}
    return bpy.context.active_object


ob = add((1, 2, 3))
assert bpy.ops.max.line_keyboard(action="FINISH") == {"CANCELLED"}
assert add((4, 2, 3)) == ob
assert add((4, 6, 5)) == ob
assert bpy.ops.max.line_keyboard(action="FINISH") == {"FINISHED"}
sp = ob.data.splines[0]
assert not sp.use_cyclic_u
assert [tuple(p.co) for p in sp.bezier_points] == [(1, 2, 3), (4, 2, 3), (4, 6, 5)]
assert all(p.handle_left_type == p.handle_right_type == "VECTOR" for p in sp.bezier_points)
print("LINE_TEST keyboard open count=3 positions=exact handles=VECTOR cyclic=False", flush=True)

settings.initial_type = "SMOOTH"
closed = add((0, 0, 0))
assert closed != ob
add((3, 0, 0))
add((0, 3, 0))
assert bpy.ops.max.line_keyboard(action="CLOSE") == {"FINISHED"}
sp = closed.data.splines[0]
assert len(sp.bezier_points) == 3 and sp.use_cyclic_u
assert all(p.handle_left_type == p.handle_right_type == "AUTO" for p in sp.bezier_points)
print("LINE_TEST keyboard closed count=3 handles=AUTO cyclic=True new_object=True", flush=True)

assert bpy.ops.max.line_keyboard(action="CLOSE") == {"CANCELLED"}

from notuodesk_3ds_maxxed import line_tool
object_count, group_count = len(bpy.data.objects), len(bpy.data.node_groups)
add((0, 0, 0))
line_tool.discard_line(bpy.context)
assert len(bpy.data.objects) == object_count
assert len(bpy.data.node_groups) == group_count
print("LINE_TEST discard single_point=True no_orphan_curve_or_node_group=True", flush=True)

# A straight radial spline makes topology and cross-section size measurable.
settings.initial_type = "CORNER"
radial = add((0, 0, 0))
add((4, 0, 0))
assert bpy.ops.max.line_keyboard(action="FINISH") == {"FINISHED"}
p = radial.data.max_spline
p.thickness = 2
p.sides = 4
p.viewport = True


def evaluated():
    bpy.context.view_layer.update()
    ob_eval = radial.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ob_eval.to_mesh()
    positions = [v.co.copy() for v in mesh.vertices]
    faces = len(mesh.polygons)
    ob_eval.to_mesh_clear()
    return positions, faces


positions, faces = evaluated()
assert len(positions) == 8 and faces == 6, (len(positions), faces)
assert abs(max(v.y for v in positions) - min(v.y for v in positions) - 2) < 1e-5
p.angle = math.pi / 4
rotated, _ = evaluated()
assert len(radial.modifiers) == 1, "Rendering updates must reuse their modifier"
assert abs(max(v.y for v in rotated) - min(v.y for v in rotated) - math.sqrt(2)) < 1e-5
print("LINE_TEST radial thickness=diameter sides=4 angle=45deg vertices=8 faces=6", flush=True)

p.angle = 0
p.optimize = False
unoptimized, _ = evaluated()
assert len(unoptimized) > len(positions), (len(unoptimized), len(positions))
p.adaptive = True
assert radial.data.resolution_u == 64
p.adaptive = False
p.steps = 2
assert radial.data.resolution_u == 3
p.optimize = True
p.viewport = False
assert evaluated()[1] == 0
print("LINE_TEST interpolation Optimize_changes_topology=True Steps=2 resolution=3 Adaptive_resolution=64", flush=True)

# Check the actual render branch, not just the node input values.
for ob in bpy.data.objects:
    if ob != radial:
        ob.hide_render = True
camera = bpy.data.objects.new("Line test camera", bpy.data.cameras.new("Line test camera"))
bpy.context.collection.objects.link(camera)
camera.location = (2, -8, 4)
camera.rotation_euler = (Vector((2, 0, 0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 7
scene = bpy.context.scene
scene.camera = camera
scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = 1
scene.render.resolution_x = scene.render.resolution_y = 32
scene.render.resolution_percentage = 100
scene.render.film_transparent = True


def render_alpha(name):
    import os
    import tempfile
    path = os.path.join(tempfile.mkdtemp(prefix="maxxed-line-"), name + ".png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(path, check_existing=False)
    alpha = sum(list(image.pixels)[3::4])
    bpy.data.images.remove(image)
    return alpha


p.renderer = False
p.viewport = True
assert render_alpha("maxxed-line-render-disabled") == 0
p.renderer = True
p.viewport = False
assert evaluated()[1] == 0
assert render_alpha("maxxed-line-render-enabled") > 0
print("LINE_TEST rendering renderer_off_viewport_on=transparent renderer_on_viewport_off=visible", flush=True)

# The untouched shape path still creates its original poly rectangle.
assert bpy.ops.max.create_shape(kind="RECTANGLE") == {"FINISHED"}
rectangle = bpy.context.active_object
assert len(rectangle.modifiers) == 0
assert len(rectangle.data.splines[0].points) == 4
assert rectangle.data.splines[0].use_cyclic_u
rectangle.data.bevel_depth = 0.25
rectangle.data.max_spline.steps = 4
assert rectangle.data.bevel_depth == 0.25
assert len(rectangle.modifiers) == 0
print("LINE_TEST other_shapes rectangle=unchanged", flush=True)

addon_utils.disable("notuodesk_3ds_maxxed", default_set=True)
assert not hasattr(bpy.types.WindowManager, "max_line")
addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
assert hasattr(bpy.types.WindowManager, "max_line")
print("LINE_TEST register disable_enable=clean", flush=True)
print("LINE_TEST PASS", flush=True)
