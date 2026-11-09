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
        cases = [("shape " + k, bpy.ops.max.create_shape, {"kind": k}) for k, _, _ in SHAPES]
        cases += [("helper " + k, bpy.ops.max.create_helper, {"kind": k}) for k, _, _ in HELPERS]
        cases += [("light " + k, bpy.ops.max.create_light, {"kind": k}) for k, _, _ in LIGHTS if k != "SKYLIGHT"]
        cases += [("camera " + str(t), bpy.ops.max.create_camera, {"target": t}) for t in (False, True)]
        cases += [("vray " + k, bpy.ops.max.vray_light, {"kind": k}) for k in ("PLANE", "DISC", "SPHERE", "DOME", "SUN", "IES")]
        cases += [("vray camera", bpy.ops.max.vray_camera, {}), ("vray plane", bpy.ops.max.vray_plane, {})]
        for label, op, props in cases:
            with self.subTest(label=label):
                bpy.context.scene.cursor.location = (8, 5, 3)
                self.assertEqual(op(**props), {"FINISHED"})
                self.assertEqual(tuple(bpy.context.active_object.location), (0, 0, 0), label)
                self.assertEqual(tuple(bpy.context.scene.cursor.location), (8, 5, 3), label)
        print("CURSOR_TEST creation cases", len(cases), flush=True)

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
