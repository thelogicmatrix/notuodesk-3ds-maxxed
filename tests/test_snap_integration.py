"""Magnetic integration and exact entry. Run via isolated run_checks.py tests."""
import addon_utils
import bpy
from mathutils import Vector, Matrix
from types import SimpleNamespace
from unittest.mock import patch
addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
from notuodesk_3ds_maxxed import snaps, create, prims, keyboard_entry, extended_primitives
s = snaps.settings(bpy.context)
s.mode = "3D"
s.grid_spacing = 1
s.snap_radius = 20
s.preview_radius = 30
for key, _ in snaps.TYPES:
    setattr(s, key, key == "grid_points")
bpy.context.scene.tool_settings.use_snap = True
region = SimpleNamespace(width=1000, height=1000)
rv = SimpleNamespace(perspective_matrix=Matrix.Diagonal((.4, .4, .1, 1)), is_perspective=False)
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)

# Every dimensional stage must stay free outside radius and attract within it.
for kind, stages in extended_primitives.STAGES.items():
    ob = create.new_object(bpy.context, kind, bpy.data.meshes.new(kind))
    prims.set_params(ob, kind, radius1=8, width=8, length=8, front_length=8, back_length=8, side_length=8, height=8)
    for stage in stages:
        for raw, want in ((1.3, 1.3), (1.04, 1.0)):
            prims.set_params(ob, kind, radius1=8, width=8, length=8, front_length=8, back_length=8, side_length=8, height=8)
            op = SimpleNamespace(obj=ob, region=region, rv3d=rv, p0=Vector(),
                                 n=Vector((0,0,1)), u=Vector((1,0,0)),
                                 release_co=Vector((500,500)), stage_prop=stage,
                                 _co=lambda event, raw=raw: Vector((500,500+200*raw)),
                                 _redraw=lambda context: None)
            with patch.object(create.view3d_utils, "region_2d_to_location_3d",
                              side_effect=lambda region, rv, co, base: Vector((co.x/200,co.y/200,0))):
                create.MAX_OT_create._update_creation_stage(op,bpy.context,None)
            got = ob.max_prim.side_width if stage == "wall_width" else getattr(ob.max_prim,stage)
            assert abs(got-want) < 1e-4, (kind,stage,raw,got,want)
    bpy.data.objects.remove(ob, do_unlink=True)
print("BATCH6 dimensional stages magnetic near/far PASS", flush=True)

# Spinner Snap also must not alter the exact typed Create path.
s.spinner_snap = True
s.spinner_increment = 1
values = keyboard_entry.settings(bpy.context,"BOX")
values.x, values.y, values.z = .31, .47, .63
values.width, values.length, values.height = 1.23, 2.34, -3.45
assert bpy.ops.max.keyboard_create(kind="BOX") == {"FINISHED"}
ob=bpy.context.object
assert (ob.location-Vector((.31,.47,.63))).length < 1e-5
assert abs(ob.max_prim.width-1.23)<1e-5 and abs(ob.max_prim.length-2.34)<1e-5 and abs(ob.max_prim.height+3.45)<1e-5
print("BATCH6 typed Keyboard Entry exact with Grid Points and Spinner Snap PASS",flush=True)
