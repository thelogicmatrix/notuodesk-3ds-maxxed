"""Clean-room primitive acceptance. Run through run_checks.py tests test_prims."""
import sys
import unittest
from pathlib import Path

import addon_utils
import bpy
from mathutils import Matrix, Vector

HISTORICAL_FIXTURE = Path(__file__).resolve().parent / 'fixtures/pre-rewrite-primitives.blend'


class PrimitiveContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1] / 'notuodesk_3ds_maxxed'
        assert (root / 'prims.py').is_file(), 'Replacement primitive service is missing'
        addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
        from notuodesk_3ds_maxxed import prims
        cls.prims = prims

    def box(self):
        ob = bpy.data.objects.new('Contract box', bpy.data.meshes.new('Contract box'))
        bpy.context.collection.objects.link(ob)
        self.prims.set_params(ob, 'BOX', width=4, length=6, height=-8)
        return ob

    def test_same_vertex_count_edits_stop_rebuild(self):
        # Removing edit detection would erase this vertex move without changing vcount.
        ob = self.box()
        ob.data.vertices[0].co.x = 23
        ob.max_prim.height = 9
        self.assertEqual(ob.data.vertices[0].co.x, 23)
        self.assertEqual(ob.max_prim.kind, '')

    def test_parameter_edit_preserves_object_material_and_modifier(self):
        ob = self.box()
        mat = bpy.data.materials.new('Contract material')
        ob.data.materials.append(mat)
        mod = ob.modifiers.new('Keep selected modifier', 'BEVEL')
        ob.matrix_world = Matrix.Translation((7, 8, 9))
        ob.max_prim.width = 10
        self.assertEqual(ob.data.materials[0], mat)
        self.assertEqual(ob.modifiers[0], mod)
        self.assertEqual(tuple(ob.location), (7, 8, 9))
        self.assertAlmostEqual(max(v.co.x for v in ob.data.vertices), 5)
        self.assertAlmostEqual(min(v.co.z for v in ob.data.vertices), -8)

    def test_shared_mesh_and_shape_keys_are_safe(self):
        ob = self.box()
        other = bpy.data.objects.new('Shared', ob.data)
        bpy.context.collection.objects.link(other)
        before = [tuple(v.co) for v in other.data.vertices]
        ob.max_prim.width = 10
        self.assertEqual([tuple(v.co) for v in other.data.vertices], before)
        ob.shape_key_add(name='Basis')
        ob.shape_key_add(name='Keep this key').data[0].co.z += 2
        before = [tuple(v.co) for v in ob.data.vertices]
        ob.max_prim.height = 5
        self.assertEqual([tuple(v.co) for v in ob.data.vertices], before)
        self.assertEqual(len(ob.data.shape_keys.key_blocks), 2)

    def test_invalid_dimensions_leave_geometry(self):
        ob = self.box()
        before = [tuple(v.co) for v in ob.data.vertices]
        self.prims.set_params(ob, 'TUBE', radius1=2, radius2=2)
        self.assertEqual([tuple(v.co) for v in ob.data.vertices], before)
        self.assertFalse(self.prims.rebuild(ob))

    def test_legacy_geometry_must_match_before_adoption(self):
        ob = self.box()
        del ob.data['_max_base_positions']
        del ob.data['_max_base_topology']
        self.assertTrue(self.prims.adopt_legacy(ob))
        ob.max_prim.width = 10
        self.assertAlmostEqual(max(v.co.x for v in ob.data.vertices), 5)
        del ob.data['_max_base_positions']
        del ob.data['_max_base_topology']
        ob.data.vertices[0].co.x = 23
        self.assertFalse(self.prims.adopt_legacy(ob))
        self.assertEqual(ob.data.vertices[0].co.x, 23)

    def historical_objects(self):
        with bpy.data.libraries.load(str(HISTORICAL_FIXTURE)) as (source, target):
            target.objects = source.objects
        objects = {ob.max_prim.kind: ob for ob in target.objects if ob.type == 'MESH'}
        self.assertTrue({'CONE', 'CYLINDER'} <= objects.keys())
        return objects

    def test_historical_cone_and_cylinder_remain_editable(self):
        # An exact new-tessellation match must not reject genuine saved base objects.
        objects = self.historical_objects()
        for kind in ('CONE', 'CYLINDER'):
            with self.subTest(kind=kind):
                ob = objects[kind]
                bpy.context.collection.objects.link(ob)
                self.assertEqual(ob.max_prim.radius1, 2)
                self.assertEqual(ob.max_prim.radius2, .5)
                self.assertEqual(ob.max_prim.height, 3)
                before = [tuple(v.co) for v in ob.data.vertices]
                self.assertTrue(self.prims.adopt_legacy(ob), kind)
                self.assertEqual([tuple(v.co) for v in ob.data.vertices], before)
                ob.max_prim.height = 7
                self.assertEqual(ob.max_prim.kind, kind)
                self.assertAlmostEqual(max(v.co.z for v in ob.data.vertices), 7)
                self.assertAlmostEqual(min(v.co.z for v in ob.data.vertices), 0)
                self.assertEqual(ob.max_prim.radius1, 2)
                self.assertEqual(ob.max_prim.radius2, .5)
                print('F3 PASS historical', kind, 'adopts unchanged and height remains editable', flush=True)

    def test_historical_same_count_edits_are_preserved(self):
        objects = self.historical_objects()
        for kind in ('CONE', 'CYLINDER'):
            with self.subTest(kind=kind):
                ob = objects[kind]
                bpy.context.collection.objects.link(ob)
                ob.data.vertices[0].co.x += .25
                before = [tuple(v.co) for v in ob.data.vertices]
                self.assertFalse(self.prims.adopt_legacy(ob), kind)
                ob.max_prim.height = 7
                self.assertEqual(ob.max_prim.kind, '')
                self.assertEqual([tuple(v.co) for v in ob.data.vertices], before)
                print('F3 PASS edited historical', kind, 'refuses adoption and preserves geometry', flush=True)


result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(PrimitiveContractTests))
if not result.wasSuccessful():
    raise SystemExit(1)
print('CLEANROOM PRIMS PASS', flush=True)
