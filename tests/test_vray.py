"""Isolated Blender checks for supported renderer equivalents and saved camera data."""
import math
from pathlib import Path
import tempfile
import unittest
import addon_utils
import bpy

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import vray


class RenderingTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.mesh.primitive_cube_add()

    def test_presets_are_principled_equivalents(self):
        for preset in ('DEFAULT', 'GLOSSY', 'METAL', 'CHROME', 'GLASS', 'CAR_PAINT', 'EMISSIVE'):
            self.assertEqual(bpy.ops.max.vray_material(preset=preset), {'FINISHED'})
            mat = bpy.context.object.active_material
            self.assertTrue(mat.get('max_vray'))
            self.assertEqual(mat.get('max_type'), 'VRAY')
            self.assertIsNotNone(next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None))
            mat.max_vray_glossiness = .7
            self.assertAlmostEqual(mat.max_vray_glossiness, .7, places=5)

    def test_camera_state_is_per_camera(self):
        bpy.context.scene.camera = None
        vray.sync_camera_exposure()
        bpy.context.scene.view_settings.exposure = .5
        bpy.ops.max.vray_camera()
        a = bpy.context.object.data
        bpy.ops.max.vray_camera()
        b = bpy.context.object.data
        a.max_vray.iso = 400
        b.max_vray.iso = 100
        self.assertNotEqual(vray.camera_exposure(a), vray.camera_exposure(b))
        self.assertEqual(b.max_vray.iso, 100)
        b.max_vray.exposure = False
        self.assertEqual(vray.camera_exposure(b), 0)
        self.assertTrue(math.isfinite(vray.camera_exposure(a)))
        bpy.context.scene.camera = next(obj for obj in bpy.data.objects if obj.type == 'CAMERA' and obj.data == a)
        vray.sync_camera_exposure()
        self.assertAlmostEqual(bpy.context.scene.view_settings.exposure, 2.5, places=5)
        bpy.context.scene.camera = next(obj for obj in bpy.data.objects if obj.type == 'CAMERA' and obj.data == b)
        vray.sync_camera_exposure()
        self.assertAlmostEqual(bpy.context.scene.view_settings.exposure, .5, places=5)

    def test_lifecycle_is_paired(self):
        vray.register_props()
        vray.register_props()
        self.assertEqual(bpy.app.handlers.render_pre.count(vray.sync_camera_exposure), 1)
        vray.unregister_props()
        vray.unregister_props()
        self.assertNotIn(vray.sync_camera_exposure, bpy.app.handlers.render_pre)
        vray.register_props()

    def test_honest_ies_and_missing_environment(self):
        objects, world = set(bpy.data.objects), bpy.context.scene.world
        self.assertEqual(bpy.ops.max.vray_light(kind='IES'), {'CANCELLED'})
        self.assertEqual(bpy.ops.max.vray_light(kind='DOME', filepath='Z:/absent.hdr'), {'CANCELLED'})
        self.assertEqual(set(bpy.data.objects), objects)
        self.assertEqual(bpy.context.scene.world, world)

    def test_environment_uses_an_independent_world(self):
        old_world = bpy.context.scene.world
        old_nodes = len(old_world.node_tree.nodes) if old_world and old_world.node_tree else 0
        objects = set(bpy.data.objects)
        with tempfile.TemporaryDirectory() as folder:
            image = bpy.data.images.new('EnvironmentFixture', 2, 2)
            image.file_format = 'PNG'
            image.filepath_raw = str(Path(folder)/'environment.png')
            image.save()
            self.assertEqual(bpy.ops.max.vray_light(kind='DOME', filepath=image.filepath_raw), {'FINISHED'})
        world = bpy.context.scene.world
        self.assertNotEqual(world, old_world)
        self.assertTrue(world.get('max_vray_dome'))
        self.assertEqual(set(bpy.data.objects), objects)
        self.assertTrue(any(node.type == 'TEX_ENVIRONMENT' and node.image for node in world.node_tree.nodes))
        if old_world and old_world.node_tree:
            self.assertEqual(len(old_world.node_tree.nodes), old_nodes)

    def test_supported_lights_and_plane(self):
        for kind, backend in (('PLANE', 'AREA'), ('DISC', 'AREA'), ('SPHERE', 'POINT'), ('SUN', 'SUN')):
            self.assertEqual(bpy.ops.max.vray_light(kind=kind), {'FINISHED'})
            self.assertEqual(bpy.context.object.data.type, backend)
        self.assertEqual(bpy.ops.max.vray_plane(), {'FINISHED'})
        self.assertEqual(bpy.context.object.type, 'MESH')

    def test_renderer_names_and_quality(self):
        self.assertIn('CYCLES', dict(vray.available_renderers()))
        self.assertIn('BLENDER_WORKBENCH', dict(vray.available_renderers()))
        self.assertIn('EEVEE', dict(vray.available_renderers()).values())
        self.assertEqual(bpy.ops.max.set_renderer(engine='BLENDER_WORKBENCH'), {'FINISHED'})
        self.assertEqual(bpy.ops.max.set_renderer(engine='missing_engine'), {'CANCELLED'})
        self.assertEqual(bpy.ops.max.set_renderer(engine='CYCLES'), {'FINISHED'})
        for quality, (samples, bounces) in vray.QUALITY.items():
            self.assertEqual(bpy.ops.max.vray_render_preset(quality=quality), {'FINISHED'})
            self.assertEqual(bpy.context.scene.cycles.samples, samples)
            self.assertEqual(bpy.context.scene.cycles.max_bounces, bounces)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RenderingTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
