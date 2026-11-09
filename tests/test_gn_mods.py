"""Run with run_checks.py tests test_gn_mods, in a fresh isolated Blender."""
import importlib.util
import math
import os
from pathlib import Path
import sys
import unittest

import bpy
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _w11 import load, evaluated


class DeformerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert importlib.util.find_spec('_maxxed_w11.gn_mods'), 'clean-room geometry service is missing'
        cls.gn = load('gn_mods')

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        self.ob = bpy.context.object

    def test_adapter_and_independent_inputs(self):
        g = self.gn.G('Contract check')
        g.inp('Distance', default=.25, lo=-10, hi=10)
        x, y, z = g.xyz(g.position())
        g.out(g.set_position(g.g('Geometry'), position=g.combine(g.m('ADD', x, g.g('Distance')), y, z)))
        a = self.ob.modifiers.new('One', 'NODES')
        a.node_group = g.ng
        b = self.ob.modifiers.new('Two', 'NODES')
        b.node_group = g.ng
        self.assertTrue(self.gn.set_input(a, 'Distance', .5))
        self.assertTrue(self.gn.set_input(b, 'Distance', -.25))
        self.assertFalse(self.gn.set_input(a, 'Missing', 5))
        points, _, _ = evaluated(self.ob)
        self.assertAlmostEqual(min(p[0] for p in points), -.75)
        identifier = dict((label, ident) for ident, label in self.gn.inputs(a))['Distance']
        owner, path = self.gn.input_ref(a, identifier)
        self.assertAlmostEqual(owner.path_resolve(path), .5)
        self.assertTrue(owner.keyframe_insert(data_path=path, frame=1))
        self.gn.set_input(a, 'Distance', 1.5)
        owner.keyframe_insert(data_path=path, frame=11)
        bpy.context.scene.frame_set(1)
        self.assertAlmostEqual(owner.path_resolve(path), .5)

    def test_each_deformer_and_degenerate_geometry(self):
        for kind in ('Melt', 'Skew', 'Squeeze', 'Noise', 'Push', 'Spherify'):
            with self.subTest(kind=kind):
                self.ob.modifiers.clear()
                mod = self.gn.add(self.ob, kind)
                self.assertTrue(self.gn.inputs(mod))
                points, _, _ = evaluated(self.ob)
                self.assertEqual(len(points), 8)
                self.assertTrue(all(math.isfinite(c) for p in points for c in p))
                self.ob.scale = (2, .5, 3)
                self.ob.rotation_euler.z = .4
                self.assertEqual(points, evaluated(self.ob)[0])
        self.ob.data.clear_geometry()
        self.assertEqual(evaluated(self.ob)[0], [])
        self.ob.data.from_pydata([(0, 0, 0), (1, 0, 0)], [(0, 1)], [])
        self.assertTrue(all(math.isfinite(c) for p in evaluated(self.ob)[0] for c in p))

    def test_push_and_skew_numeric_result(self):
        mod = self.gn.add(self.ob, 'Skew')
        self.gn.set_input(mod, 'Amount', 1)
        pts, _, _ = evaluated(self.ob)
        self.assertAlmostEqual(min(p[0] for p in pts if p[2] > 0), 0)
        self.ob.modifiers.clear()
        self.gn.add(self.ob, 'Push')
        pts, _, _ = evaluated(self.ob)
        self.assertGreater(max(p[0] for p in pts), 1)

    def test_slice_inserts_plane_vertices_and_removes_lower_side(self):
        mod = self.gn.add(self.ob, 'Slice')
        self.gn.set_input(mod, 'Slice Height', 0)
        pts, faces, _ = evaluated(self.ob)
        self.assertTrue(any(abs(p[2]) < 1e-5 for p in pts))
        self.assertGreater(len(faces), 6)
        self.gn.set_input(mod, 'Remove Bottom', True)
        pts, _, _ = evaluated(self.ob)
        self.assertGreaterEqual(min(p[2] for p in pts), -1e-5)

    def test_saved_named_inputs_and_animation(self):
        mod = self.gn.add(self.ob, 'Melt')
        names = {label for _, label in self.gn.inputs(mod)}
        self.assertEqual(names, {'Amount', '% of Melt Spread', 'Solidity', 'Irregularity', 'Drip Size', 'Seed', 'Flip Axis'})
        self.gn.set_input(mod, 'Amount', .123)
        path = str(Path(os.environ['MAXXED_OUT']) / 'w11-inputs.blend')
        name = self.ob.name
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
        mod = bpy.data.objects[name].modifiers[0]
        identifier = next(i for i, n in self.gn.inputs(mod) if n == 'Amount')
        owner, prop = self.gn.input_ref(mod, identifier)
        self.assertAlmostEqual(owner.path_resolve(prop), .123, places=5)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DeformerTests))
    print('W11 GN tests=%d failures=%d errors=%d' % (result.testsRun, len(result.failures), len(result.errors)), flush=True)
    if not result.wasSuccessful():
        raise SystemExit(1)
