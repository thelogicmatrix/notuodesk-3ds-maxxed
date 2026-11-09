"""Cursor-independent creation. Run with an isolated add-on profile:
blender -b --factory-startup --python-exit-code 1 --python tests/test_no_cursor.py
"""
import unittest

import addon_utils
import bpy

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)


class NoCursorTests(unittest.TestCase):
    def test_creation_ignores_displaced_cursor(self):
        from notuodesk_3ds_maxxed.create import SHAPES, HELPERS, LIGHTS
        cases = [("shape " + k, bpy.ops.max.create_shape, {"kind": k}) for k, _, _ in SHAPES if k != "LINE"]
        cases += [("helper " + k, bpy.ops.max.create_helper, {"kind": k}) for k, _, _ in HELPERS]
        cases += [("light " + k, bpy.ops.max.create_light, {"kind": k}) for k, _, _ in LIGHTS if k != "SKYLIGHT"]
        cases += [("camera " + str(t), bpy.ops.max.create_camera, {"target": t}) for t in (False, True)]
        cases += [("vray " + k, bpy.ops.max.vray_light, {"kind": k}) for k in ("PLANE", "DISC", "SPHERE", "SUN")]
        cases += [("vray camera", bpy.ops.max.vray_camera, {}), ("vray plane", bpy.ops.max.vray_plane, {})]
        for label, op, props in cases:
            with self.subTest(label=label):
                bpy.context.scene.cursor.location = (8, 5, 3)
                self.assertEqual(op(**props), {"FINISHED"})
                self.assertEqual(tuple(bpy.context.active_object.location), (0, 0, 0), label)
                self.assertEqual(tuple(bpy.context.scene.cursor.location), (8, 5, 3), label)
        print("CURSOR_TEST creation cases", len(cases), flush=True)
        for kind in ("DOME", "IES"):
            objects = set(bpy.data.objects)
            self.assertEqual(bpy.ops.max.vray_light(kind=kind), {"CANCELLED"})
            self.assertEqual(set(bpy.data.objects), objects)
            self.assertEqual(tuple(bpy.context.scene.cursor.location), (8, 5, 3))
        print("CURSOR_TEST missing environment and unavailable IES preserve objects and cursor", flush=True)

    def test_merged_creation_paths_ignore_displaced_cursor(self):
        from mathutils import Vector
        from notuodesk_3ds_maxxed import create, extended_primitives, get_prefs, keyboard_entry, line_tool, plane_plus, prims
        sentinel = (81, -52, 33)
        prefs = get_prefs()
        prefs.auto_pivot_on_create = "OFF"
        bpy.context.scene.cursor.location = sentinel
        for kind in keyboard_entry.FIELDS:
            values = keyboard_entry.settings(bpy.context, kind)
            values.x, values.y, values.z = 7, -3, 11
            for field, _ in keyboard_entry.FIELDS[kind]:
                setattr(values, field, .5 if field == "radius2" else 4)
            self.assertEqual(bpy.ops.max.keyboard_create(kind=kind), {"FINISHED"}, kind)
            self.assertLess((bpy.context.object.location - Vector((7, -3, 11))).length, 1e-5)
        for kind in extended_primitives.PRIMITIVES:
            ob = create.new_object(bpy.context, kind, bpy.data.meshes.new(kind))
            prims.set_params(ob, kind)
            self.assertEqual(tuple(ob.location), (0, 0, 0))
        line_tool.add_point(bpy.context, (3, -5, 7), "CORNER")
        ob = line_tool.add_point(bpy.context, (9, 1, 13), "CORNER")
        self.assertTrue(line_tool.finish_line(bpy.context))
        actual = [ob.matrix_world @ p.co for p in ob.data.splines[0].bezier_points]
        for point, expected in zip(actual, ((3, -5, 7), (9, 1, 13))):
            self.assertLess((point - Vector(expected)).length, 1e-5)
        for mode in ("OFF", "CENTER", "BOTTOM"):
            prefs.auto_pivot_on_create = mode
            self.assertEqual(bpy.ops.max.plane_plus(), {"FINISHED"})
            ob = bpy.context.object
            self.assertEqual(tuple(ob.location), (0, 0, 0))
            self.assertNotIn("max_pivot_offset", ob)
        prefs.auto_pivot_on_create = "OFF"
        self.assertEqual(tuple(bpy.context.scene.cursor.location), sentinel)
        print("CURSOR_TEST merged paths: 9 Keyboard Entry, 11 Extended Primitives, finished Line, PlanePlus under all AutoPivot modes PASS", flush=True)

    def test_pivot_to_world_preserves_geometry_children_and_cursor(self):
        bpy.ops.mesh.primitive_cube_add(location=(8, 5, 3))
        ob = bpy.context.object
        ob.rotation_euler = (.2, .3, .4)
        ob.scale = (2, 3, 4)
        ob.shape_key_add(name="Basis")
        key = ob.shape_key_add(name="Raised")
        key.data[0].co.z += 2
        shared = bpy.data.objects.new("Shared", ob.data)
        bpy.context.collection.objects.link(shared)
        child = bpy.data.objects.new("Child", None)
        bpy.context.collection.objects.link(child)
        child.parent = ob
        child.location = (1, 2, 3)
        bpy.context.view_layer.update()
        before = [ob.matrix_world @ v.co for v in ob.data.vertices]
        key_before = ob.matrix_world @ key.data[0].co
        child_before = child.matrix_world.copy()
        shared_before = [v.co.copy() for v in shared.data.vertices]
        bpy.context.scene.cursor.location = (21, 22, 23)
        bpy.ops.max.object_cmd(cmd="PIVOT_TO_WORLD")
        bpy.context.view_layer.update()
        self.assertLess(ob.matrix_world.translation.length, 1e-5)
        for a, v in zip(before, ob.data.vertices):
            self.assertLess((a - ob.matrix_world @ v.co).length, 1e-4)
        self.assertLess((key_before - ob.matrix_world @ ob.data.shape_keys.key_blocks[1].data[0].co).length, 1e-4)
        self.assertLess((child_before.translation - child.matrix_world.translation).length, 1e-4)
        self.assertEqual([tuple(v.co) for v in shared.data.vertices], [tuple(v) for v in shared_before])
        self.assertEqual(tuple(bpy.context.scene.cursor.location), (21, 22, 23))
        print("CURSOR_TEST pivot geometry children shape_keys shared_data PASS", flush=True)

    def test_text_pivot_preserves_glyphs_and_editable_text(self):
        bpy.ops.max.create_shape(kind="TEXT")
        ob = bpy.context.object
        ob.location = (8, 5, 3)
        ob.scale = (2, 3, 4)
        ob.data.size = 2
        bpy.context.view_layer.update()
        def glyphs():
            evaluated = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            result = [evaluated.matrix_world @ v.co for v in mesh.vertices]
            evaluated.to_mesh_clear()
            return result
        before = glyphs()
        bpy.context.scene.cursor.location = (21, 22, 23)
        bpy.ops.max.object_cmd(cmd="PIVOT_TO_WORLD")
        bpy.context.view_layer.update()
        self.assertEqual(ob.type, "FONT")
        self.assertEqual(tuple(ob.location), (0, 0, 3))
        after = glyphs()
        self.assertEqual(len(before), len(after))
        for a, b in zip(before, after):
            self.assertLess((a - b).length, 1e-4)
        self.assertEqual(tuple(bpy.context.scene.cursor.location), (21, 22, 23))
        print("CURSOR_TEST editable text pivot glyphs PASS", flush=True)


import sys
result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(unittest.defaultTestLoader.loadTestsFromTestCase(NoCursorTests))
if not result.wasSuccessful():
    raise AssertionError("No-cursor regressions failed")
