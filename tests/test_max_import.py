"""Isolated Blender checks for transactional scene import and texture lookup."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import addon_utils
import bpy

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import max_import as subject


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.scene = bpy.context.scene
        self.sentinel = bpy.data.objects.new('KeepMe', None)
        self.scene.collection.objects.link(self.sentinel)
        self.sentinel.select_set(True)
        bpy.context.view_layer.objects.active = self.sentinel

    def tearDown(self):
        self.tmp.cleanup()

    def fixture(self, name='one.max'):
        path = self.root / name
        path.write_bytes(b'fixture')
        return path

    def test_units_are_exact(self):
        self.assertEqual(subject.UNIT_SCALE, dict(INCHES=.0254, CENTIMETERS=.01,
                         MILLIMETERS=.001, FEET=.3048, METERS=1, GENERIC=1))

    def test_missing_and_unsupported_reader(self):
        with patch.object(subject, '_reader_package', return_value=None):
            with self.assertRaisesRegex(RuntimeError, '1.9.2'):
                subject.require_reader()
        with patch.object(subject, '_reader_package', return_value=type('Reader', (), {'__version__': '9.0'})()):
            with self.assertRaisesRegex(RuntimeError, 'Unsupported'):
                subject.require_reader()

    def test_failed_open_is_atomic(self):
        before = set(bpy.data.objects)
        selection = set(bpy.context.selected_objects)
        path = self.fixture()
        def fail(*args, **kwargs):
            ob = bpy.data.objects.new('PartialImport', None)
            bpy.context.collection.objects.link(ob)
            raise RuntimeError('reader failure')
        with patch.object(subject, 'require_reader'), patch.object(subject, '_read_max', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'reader failure'):
                subject.import_paths(bpy.context, [path], replace=True)
        self.assertEqual(set(bpy.data.objects), before)
        self.assertEqual(bpy.context.scene, self.scene)
        self.assertEqual(set(bpy.context.selected_objects), selection)
        self.assertEqual(bpy.context.view_layer.objects.active, self.sentinel)

    def test_cancelled_open_is_atomic(self):
        with patch.object(subject, 'require_reader'), patch.object(subject, '_read_max', return_value={'CANCELLED'}):
            with self.assertRaisesRegex(RuntimeError, 'cancel'):
                subject.import_paths(bpy.context, [self.fixture()], replace=True)
        self.assertIn(self.sentinel.name, self.scene.objects)

    def test_open_commit_and_merge_partial_failure(self):
        def read(path, **kwargs):
            obj = bpy.data.objects.new(Path(path).stem, None)
            bpy.context.collection.objects.link(obj)
            return {'FINISHED'}
        a, b = self.fixture('alpha.max'), self.fixture('beta.max')
        with patch.object(subject, 'require_reader'), patch.object(subject, '_read_max', side_effect=read):
            result = subject.import_paths(bpy.context, [a, self.root/'absent.max', b])
            self.assertEqual(len(result['imported']), 2)
            self.assertEqual(len(result['errors']), 1)
            self.assertIn(self.sentinel.name, self.scene.objects)
            subject.import_paths(bpy.context, [a], replace=True)
        self.assertNotIn(self.sentinel.name, self.scene.objects)
        self.assertEqual(len(self.scene.objects), 1)

    def test_missing_fbx_and_cancelled_new_scene_preserve_scene(self):
        with self.assertRaisesRegex(RuntimeError, 'not found'):
            subject.import_fbx(bpy.context, self.root/'absent.fbx', replace=True)
        with patch.object(subject, '_read_fbx', return_value={'CANCELLED'}):
            with self.assertRaisesRegex(RuntimeError, 'cancel'):
                subject.import_fbx(bpy.context, self.fixture('cancel.fbx'), replace=True)
        self.assertIn(self.sentinel.name, self.scene.objects)

    def test_ambiguous_textures_are_unresolved(self):
        for folder in ('a', 'b'):
            (self.root/folder).mkdir()
            (self.root/folder/'same.png').write_bytes(b'not an image')
        self.assertIsNone(subject._find_image(subject.texture_index([self.root]), 'same'))
        self.assertIsNone(subject._find_image({'diffused':'wrong.png'}, 'Diffuse'))

    def test_bitmap_load_targets_active_material_and_relink_builds_nodes(self):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.object
        image = bpy.data.images.new('FixtureBitmap', 2, 2)
        image.file_format = 'PNG'
        image.filepath_raw = str(self.root/'albedo.png')
        image.save()
        self.assertEqual(bpy.ops.max.load_bitmap(filepath=image.filepath_raw), {'FINISHED'})
        material = obj.active_material
        self.assertEqual(material['max_bitmap'], 'albedo.png')
        self.assertTrue(any(node.type == 'TEX_IMAGE' and node.image for node in material.node_tree.nodes))
        empty = bpy.data.materials.new('NoNodes')
        empty['max_bitmap'] = 'albedo.png'
        linked, missing = subject.relink_textures([empty], [self.root])
        self.assertEqual(linked, ['albedo.png'])
        self.assertFalse(missing)
        self.assertTrue(empty.use_nodes)
        self.assertEqual(bpy.ops.max.load_bitmap(filepath=str(self.root/'missing.png')), {'CANCELLED'})
        self.assertEqual(obj.active_material, material)

    def test_import_options_reach_reader(self):
        path = self.fixture()
        def read(*args, **kwargs):
            obj = bpy.data.objects.new('FlagFixture', None)
            bpy.context.collection.objects.link(obj)
            return {'FINISHED'}
        with patch.object(subject, 'require_reader'), patch.object(subject, '_read_max', side_effect=read) as reader:
            subject.import_paths(bpy.context, [path], textures=False, materials=False, uvs=False, primitives=False)
            self.assertEqual(reader.call_args.kwargs, dict(textures=False, materials=False, uvs=False, primitives=False))

    def test_fbx_unavailable_and_no_imported_objects(self):
        with patch.object(subject, '_read_fbx', side_effect=RuntimeError('FBX unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                subject.import_fbx(bpy.context, self.fixture('test.fbx'), replace=True)
        with patch.object(subject, 'require_reader'), patch.object(subject, '_read_max', return_value={'FINISHED'}):
            with self.assertRaisesRegex(RuntimeError, 'no supported'):
                subject.import_paths(bpy.context, [self.fixture()], replace=True)
        self.assertIn(self.sentinel.name, self.scene.objects)

    def test_export_unavailable_preserves_units(self):
        from notuodesk_3ds_maxxed import max_export
        before = self.scene.unit_settings.scale_length
        with patch.object(max_export, 'fbx_settings', side_effect=AttributeError('exporter missing')):
            self.assertEqual(bpy.ops.max.export_max_fbx(filepath=str(self.root/'test.fbx')), {'CANCELLED'})
        self.assertEqual(self.scene.unit_settings.scale_length, before)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ImportTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
