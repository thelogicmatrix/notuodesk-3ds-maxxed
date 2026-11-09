"""Extended Keyboard Entry creates one editable object at an exact entered position."""
import math
import addon_utils
import bpy
from mathutils import Vector

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import keyboard_entry, get_prefs
get_prefs().auto_pivot_on_create = 'OFF'

cases = {
    'HEDRA': dict(radius1=2),
    'CHAMFERBOX': dict(width=4, length=6, height=-3, fillet=.2),
    'OILTANK': dict(radius1=2, height=5, cap_height=.3, blend=0),
    'SPINDLE': dict(radius1=2, height=-5, cap_height=.3, blend=0),
    'GENGON': dict(radius1=2, fillet=.1, height=-3),
    'PRISM': dict(side1=3, side2=4, side3=5, height=6),
    'TORUS_KNOT': dict(radius1=3, radius2=.2),
    'CHAMFERCYL': dict(radius1=2, height=-5, fillet=.2),
    'CAPSULE': dict(radius1=2, height=5),
    'L_EXT': dict(side_length=4, front_length=3, side_width=.2, front_width=.2, height=-5),
    'C_EXT': dict(back_length=3, side_length=4, front_length=3, back_width=.2,
                  side_width=.2, front_width=.2, height=5),
}
for kind, params in cases.items():
    values = keyboard_entry.settings(bpy.context, kind)
    values.x, values.y, values.z = .31, -.47, .63
    for name, value in params.items():
        setattr(values, name, value)
    before = len(bpy.data.objects)
    assert bpy.ops.max.keyboard_create(kind=kind) == {'FINISHED'}, kind
    ob = bpy.context.object
    assert len(bpy.data.objects) == before + 1
    assert ob.max_prim.kind == kind
    assert (ob.location - Vector((.31, -.47, .63))).length < 1e-5
    assert ob.data.polygons and all(math.isfinite(c) for v in ob.data.vertices for c in v.co)
    old = max(v.co.z for v in ob.data.vertices)
    if kind not in {'HEDRA', 'TORUS_KNOT'}:
        ob.max_prim.height *= 1.2
        assert max(abs(v.co.z) for v in ob.data.vertices) > abs(params['height'])
    print('EXTENDED KEYBOARD PASS', kind, 'one object, exact position, editable base', flush=True)
print('EXTENDED KEYBOARD ALL PASS (11 kinds)', flush=True)
