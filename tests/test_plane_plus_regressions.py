"""Run with an isolated add-on profile:
blender -b --factory-startup --python-exit-code 1 --python tests/test_plane_plus_regressions.py

Catches lost parameter edits after gray freeze and material edits leaking to copies.
"""
import os
import sys
import tempfile
import unittest

import addon_utils
import bpy

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
from notuodesk_3ds_maxxed import create, freezing, prims


class PlanePlusRegressions(unittest.TestCase):
    def setUp(self):
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)

    def test_gray_frozen_primitive_edits_survive_unfreeze(self):
        ob = create.new_object(bpy.context, "Box", bpy.data.meshes.new("Box"))
        prims.set_params(ob, "BOX")
        source = ob.data
        freezing.freeze(ob, bpy.context.scene)
        ob.max_prim.width = 7
        ob.max_prim.width_segs = 3
        display_count = len(ob.data.vertices)
        freezing.unfreeze(ob, bpy.context.scene)
        self.assertEqual(ob.data, source)
        self.assertAlmostEqual(max(v.co.x for v in ob.data.vertices) -
                               min(v.co.x for v in ob.data.vertices), 7)
        self.assertEqual(len(ob.data.vertices), display_count)
        self.assertEqual(ob.max_prim.kind, "BOX")
        freezing.freeze(ob, bpy.context.scene)
        ob.max_prim.width = 9
        ob.max_show_frozen_gray = False
        self.assertAlmostEqual(max(v.co.x for v in ob.data.vertices) -
                               min(v.co.x for v in ob.data.vertices), 9)
        freezing.unfreeze(ob, bpy.context.scene)
        print("PASS gray-frozen Box width and segmentation survive unfreeze and gray toggle", flush=True)

    def test_copy_opacity_does_not_change_original_material(self):
        bpy.ops.max.plane_plus()
        original = bpy.context.object
        material = original.active_material
        bpy.ops.max.clone(mode="COPY")
        copied = bpy.context.object
        copied.max_plane_plus.opacity = 20
        self.assertAlmostEqual(material.node_tree.nodes["PlanePlus Opacity"].outputs[0].default_value, 1)
        self.assertNotEqual(copied.active_material, material)
        self.assertAlmostEqual(copied.active_material.node_tree.nodes["PlanePlus Opacity"].outputs[0].default_value, .2)
        original.max_plane_plus.opacity = 65
        self.assertAlmostEqual(copied.active_material.node_tree.nodes["PlanePlus Opacity"].outputs[0].default_value, .2)
        print("PASS Copy opacity edits leave the original material unchanged in both directions", flush=True)

    def test_copy_image_does_not_change_original_material(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for name, size in (("Landscape", (32, 16)), ("Portrait", (16, 32))):
                image = bpy.data.images.new(name, width=size[0], height=size[1])
                image.filepath_raw = os.path.join(folder, name + ".png")
                image.file_format = "PNG"
                image.save()
                paths.append(image.filepath_raw)
                bpy.data.images.remove(image)
            bpy.ops.max.plane_plus()
            bpy.ops.max.plane_plus_image(filepath=paths[0])
            original = bpy.context.object
            material = original.active_material
            image = original.max_plane_plus.image
            bpy.ops.max.clone(mode="COPY")
            copied = bpy.context.object
            bpy.ops.max.plane_plus_image(filepath=paths[1])
            self.assertEqual(material.node_tree.nodes["PlanePlus Image"].image, image)
            self.assertEqual(original.max_plane_plus.image, image)
            self.assertEqual(copied.active_material.node_tree.nodes["PlanePlus Image"].image,
                             copied.max_plane_plus.image)
            self.assertNotEqual(copied.active_material, material)
            self.assertAlmostEqual(original.max_plane_plus.width / original.max_plane_plus.length, 2)
            self.assertAlmostEqual(copied.max_plane_plus.width / copied.max_plane_plus.length, .5)
            print("PASS Copy image loading leaves the original shader and aspect unchanged", flush=True)


result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(PlanePlusRegressions))
if not result.wasSuccessful():
    raise AssertionError("PlanePlus fix regressions failed")
print("PLANE_PLUS_REGRESSIONS_OK", flush=True)
