"""Run with isolated BLENDER_USER_* paths:
blender -b --factory-startup --python-exit-code 1 --python tests/test_keyboard_entry.py
"""

import math
import os

import addon_utils
import bpy
from mathutils import Vector

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
from notuodesk_3ds_maxxed import keyboard_entry, prims


def close(actual, expected, tolerance=1e-4):
    assert len(actual) == len(expected)
    assert all(abs(a - e) < tolerance for a, e in zip(actual, expected)), (tuple(actual), expected)


FIELDS = {
    "BOX": ["Length", "Width", "Height"],
    "SPHERE": ["Radius"], "GEOSPHERE": ["Radius"],
    "CYLINDER": ["Radius", "Height"],
    "CONE": ["Radius 1", "Radius 2", "Height"],
    "TUBE": ["Radius 1", "Radius 2", "Height"],
    "TORUS": ["Radius 1", "Radius 2"],
    "PYRAMID": ["Width", "Depth", "Height"],
    "PLANE": ["Length", "Width"],
}
DEFAULTS = {
    "BOX": {"length_segs": 1, "width_segs": 1, "height_segs": 1},
    "CONE": {"sides": 24, "height_segs": 5},
    "SPHERE": {"sides": 32}, "GEOSPHERE": {"sides": 4},
    "CYLINDER": {"sides": 18, "height_segs": 5},
    "TUBE": {"sides": 18, "height_segs": 5},
    "TORUS": {"sides": 24, "height_segs": 12},
    "PYRAMID": {"length_segs": 1, "width_segs": 1, "height_segs": 1},
    "PLANE": {"length_segs": 4, "width_segs": 4},
}
assert set(keyboard_entry.FIELDS) == set(FIELDS)
for kind, labels in FIELDS.items():
    assert [label for prop, label in keyboard_entry.FIELDS[kind]] == labels
    values = keyboard_entry.settings(bpy.context, kind)
    assert values.method == keyboard_entry.DEFAULT_METHODS[kind]
    values.x, values.y, values.z = (2, -3, 4)
    values.length, values.width, values.height = (6, 4, 8)
    values.radius1, values.radius2 = (3, 1)
    # Creation Method must not change keyboard coordinates or sizes.
    values.method = keyboard_entry.METHODS[kind][0][0]
    for repeat in range(2):
        assert bpy.ops.max.keyboard_create(kind=kind) == {"FINISHED"}
        ob = bpy.context.active_object
        bpy.context.view_layer.update()
        close(ob.location, (2, -3, 4))
        close(ob.scale, (1, 1, 1))
        assert ob.max_prim.kind == kind
        for key, expected in DEFAULTS[kind].items():
            assert getattr(ob.max_prim, key) == expected, (kind, key)
        if kind in {"BOX", "PYRAMID", "PLANE"}:
            close(ob.dimensions, (4, 6, 0 if kind == "PLANE" else 8))
        elif kind == "TORUS":
            close(ob.dimensions, (8, 8, 2))
        elif kind == "CYLINDER":
            close(ob.dimensions, (6 * math.sin(math.radians(80)), 6, 8))
        elif kind == "TUBE":
            close(ob.dimensions, (6, 6 * math.sin(math.radians(80)), 8))
        elif kind == "CONE":
            close(ob.dimensions, (6, 6, 8))
        else:
            close(ob.dimensions, (6, 6, 6), tolerance=0.03)
            assert all(abs(v.co.length - 3) < 1e-4 for v in ob.data.vertices)
        if kind in {"BOX", "PYRAMID", "CONE", "CYLINDER", "TUBE"}:
            assert abs(min(v.co.z for v in ob.data.vertices)) < 1e-5
        original = ob.dimensions.copy()
        values.x = 90
        bpy.context.view_layer.update()
        close(ob.dimensions, original)
        close(ob.location, (2, -3, 4))
        values.x = 2
        prop = keyboard_entry.FIELDS[kind][0][0]
        previous = getattr(values, prop)
        setattr(values, prop, previous * 1.25)
        bpy.context.view_layer.update()
        close(ob.dimensions, original)
        setattr(values, prop, previous)
        setattr(ob.max_prim, prop, previous * 1.25)
        bpy.context.view_layer.update()
        assert any(abs(a - b) > 1e-4 for a, b in zip(ob.dimensions, original))
        setattr(ob.max_prim, prop, previous)
        bpy.context.view_layer.update()
        close(ob.dimensions, original)
    print("KEYBOARD PASS", kind, "location, dimensions, defaults, parametric, repeat", flush=True)

# Negative height starts at the specified base and extends below the grid.
values = keyboard_entry.settings(bpy.context, "BOX")
values.height = -8
bpy.ops.max.keyboard_create(kind="BOX")
ob = bpy.context.active_object
assert abs(min(v.co.z for v in ob.data.vertices) + 8) < 1e-4
assert abs(max(v.co.z for v in ob.data.vertices)) < 1e-4
print("KEYBOARD PASS negative height from base", flush=True)

values = keyboard_entry.settings(bpy.context, "CONE")
values.radius1, values.radius2 = (0, 2)
bpy.ops.max.keyboard_create(kind="CONE")
ob = bpy.context.active_object
assert ob.max_prim.radius1 == 0
assert max(v.co.xy.length for v in ob.data.vertices if abs(v.co.z) < 1e-5) < 1e-6
print("KEYBOARD PASS inverted cone with zero Radius 1", flush=True)
bpy.context.scene.max_keyboard_kind = "BOX"

count = len(bpy.data.objects)
keyboard_entry.settings(bpy.context, "BOX").width = 0
assert bpy.ops.max.keyboard_create(kind="BOX") == {"CANCELLED"}
assert len(bpy.data.objects) == count
keyboard_entry.settings(bpy.context, "BOX").width = 4
assert bpy.ops.max.keyboard_create(kind="MISSING") == {"CANCELLED"}
assert len(bpy.data.objects) == count
print("KEYBOARD PASS invalid and zero-size requests create no objects", flush=True)

# All creation methods share a geometry check, independent of viewport pixels.
start, point = Vector((2, 3, 0)), Vector((6, 5, 0))
u, v = Vector((1, 0, 0)), Vector((0, 1, 0))
for kind in ("SPHERE", "GEOSPHERE", "CYLINDER", "CONE", "TUBE", "TORUS"):
    key = "DIAMETER" if kind == "GEOSPHERE" else "EDGE"
    center, scale = keyboard_entry.base_size(kind, key, start, point, u, v, 0)
    close(center, (4, 4, 0))
    assert abs(scale.x - math.sqrt(5)) < 1e-5
    center, scale = keyboard_entry.base_size(kind, "CENTER", start, point, u, v, 0)
    close(center, start)
    assert abs(scale.x - math.sqrt(20)) < 1e-5
center, scale = keyboard_entry.base_size("BOX", "CUBE", start, point, u, v, 0)
close(center, start)
close(scale, (8, 8, 8))
assert not keyboard_entry.has_height("BOX", "CUBE")
center, scale = keyboard_entry.base_size("PYRAMID", "CENTER", start, point, u, v, 0)
close(center, start)
close(scale, (8, 4, 0.0001))
center, scale = keyboard_entry.base_size("PLANE", "SQUARE", start, point, u, v, 0)
close(center, (4, 5, 0))
close(scale, (4, 4, 1))
print("KEYBOARD PASS all creation method sizing rules", flush=True)

# Last picked type survives stopping the modal tool and values are per type.
assert bpy.context.scene.max_keyboard_kind == "BOX"
assert keyboard_entry.settings(bpy.context, "SPHERE").radius1 == 3
assert keyboard_entry.settings(bpy.context, "BOX").height == -8
print("KEYBOARD PASS per-type persistent settings", flush=True)

state_file = os.path.join(os.environ["BLENDER_USER_CONFIG"], "keyboard-state.blend")
bpy.ops.wm.save_as_mainfile(filepath=state_file)
bpy.ops.wm.open_mainfile(filepath=state_file)
assert keyboard_entry.settings(bpy.context, "BOX").height == -8
assert keyboard_entry.settings(bpy.context, "SPHERE").radius1 == 3
assert bpy.context.scene.max_keyboard_kind == "BOX"
print("KEYBOARD PASS settings survive save and reload", flush=True)

addon_utils.disable("notuodesk_3ds_maxxed", default_set=True)
assert not hasattr(bpy.types.Scene, "max_keyboard_entries")
addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
print("KEYBOARD PASS unregister and re-register", flush=True)
print("KEYBOARD ALL PASS", flush=True)
