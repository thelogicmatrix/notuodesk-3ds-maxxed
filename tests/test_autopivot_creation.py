"""Run with isolated BLENDER_USER_* dirs:
blender -b --factory-startup --python-exit-code 1 --python tests/test_autopivot_creation.py
"""

import math
import sys
import unittest
from types import SimpleNamespace

import addon_utils
import bpy
from mathutils import Matrix, Vector

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
from notuodesk_3ds_maxxed import create, extended_primitives, get_prefs, keyboard_entry, line_tool, prims


def world_vertices(ob):
    bpy.context.view_layer.update()
    evaluated = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return [evaluated.matrix_world @ v.co for v in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()


def keyboard_box():
    values = keyboard_entry.settings(bpy.context, "BOX")
    values.x, values.y, values.z = 7, -3, 11
    values.width, values.length, values.height = 4, 8, -6
    assert bpy.ops.max.keyboard_create(kind="BOX") == {"FINISHED"}
    return bpy.context.active_object


def finished_line():
    line_tool.add_point(bpy.context, (3, -5, 7), "CORNER")
    line_tool.add_point(bpy.context, (9, 1, 13), "CORNER")
    ob = line_tool.add_point(bpy.context, (5, 4, 9), "CORNER")
    # The interactive operator's finish_current uses this same completion path.
    assert line_tool.finish_line(bpy.context)
    assert line_tool.pending(bpy.context) is None
    return ob


def staged_chamferbox():
    ob = create.new_object(bpy.context, "ChamferBox", bpy.data.meshes.new("ChamferBox"))
    prims.set_params(ob, "CHAMFERBOX", width=4, length=8, height=6, fillet=.4)
    ob.matrix_world = Matrix.Translation((7, -3, 11)) @ Matrix.Rotation(math.pi / 6, 4, "X")
    # Advance beyond the last interactive stage into the early-return _bake path.
    tool = SimpleNamespace(kind="CHAMFERBOX", obj=ob,
                           stage_index=len(extended_primitives.STAGES["CHAMFERBOX"]) - 1,
                           _status=lambda context: None)
    tool._bake = lambda context: create.MAX_OT_create._bake(tool, context)
    create.MAX_OT_create._next_creation_stage(tool, bpy.context, None)
    assert tool.obj is None and tool.state == "WAIT"
    return ob


class AutoPivotCreationTests(unittest.TestCase):
    def tearDown(self):
        get_prefs().auto_pivot_on_create = "OFF"

    def check_creation(self, creator):
        get_prefs().auto_pivot_on_create = "OFF"
        original = creator()
        before = world_vertices(original)
        low = Vector([min(p[i] for p in before) for i in range(3)])
        high = Vector([max(p[i] for p in before) for i in range(3)])
        for mode in ("CENTER", "BOTTOM"):
            with self.subTest(mode=mode):
                get_prefs().auto_pivot_on_create = mode
                ob = creator()
                after = world_vertices(ob)
                expected = (low + high) / 2
                if mode == "BOTTOM":
                    expected.z = low.z
                self.assertLess((ob.matrix_world.translation - expected).length, 1e-4,
                                f"{creator.__name__} {mode} origin must match world bounds")
                self.assertEqual(len(before), len(after))
                self.assertLess(max((a - b).length for a, b in zip(before, after)), 1e-4,
                                "AutoPivot must preserve world geometry")
                print(f"AUTOPIVOT PASS {creator.__name__} {mode} origin=world_bounds geometry=unchanged", flush=True)

    def test_keyboard_box(self):
        self.check_creation(keyboard_box)

    def test_finished_line(self):
        self.check_creation(finished_line)

    def test_staged_chamferbox(self):
        self.check_creation(staged_chamferbox)


result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(AutoPivotCreationTests))
if not result.wasSuccessful():
    raise SystemExit(1)
print("AUTOPIVOT CREATION TESTS PASS", flush=True)
