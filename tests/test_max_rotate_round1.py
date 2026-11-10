"""Blender background regressions for review R1-R8. Run with run_checks.py."""
import math
import unittest
from types import SimpleNamespace

import addon_utils
import bpy
from mathutils import Euler, Matrix, Vector

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import max_rotate as r, max_gizmos as g


def scene():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(size=1)
    return bpy.context.object


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.ob = scene()
        self.s = r.settings(bpy.context)
        self.s.reference, self.s.center = 'WORLD', 'PIVOT'

    def test_R1_teardown_restores_live_preview(self):
        tx = r.RotationSession(bpy.context)
        tx.apply(Matrix.Rotation(.35, 3, 'X'))
        owner = SimpleNamespace(tx=tx, clone=None, _closed=False)
        # This is the registry unregister actually clears in the reproduction.
        g._active[123] = owner
        g.unregister()
        self.assertLess(self.ob.matrix_world.to_quaternion().angle, 1e-6,
                        'disable must cancel the preview before losing its owner')
        self.assertTrue(tx.closed)
        self.assertFalse(g._active)
        print('R1 PASS teardown restores preview and closes transaction', flush=True)

    def test_R2_opposite_sphere_grabs_turn_differently(self):
        self.assertTrue(hasattr(r, 'trackball_delta'), 'free rotation needs sphere contact positions')
        snap = SimpleNamespace(angle_snap=False, angle=5)
        rotations = []
        for side in (-1, 1):
            start = Vector((side*80, 0))
            matrix, angles = r.trackball_delta(start, start+Vector((0, 60)), Vector((0, 0)),
                                              100, Matrix.Identity(3), Matrix.Identity(3), snap)
            rotations.append(matrix.to_quaternion())
        self.assertGreater(rotations[0].rotation_difference(rotations[1]).angle, .2)
        self.assertLess(rotations[0].z*rotations[1].z, 0)
        print('R2 PASS opposite sphere grabs produce opposite roll components', flush=True)

    def test_R3_display_and_transaction_share_centres(self):
        self.ob.location.x = -2
        bpy.ops.mesh.primitive_cube_add(size=1, location=(4, 0, 0))
        bpy.context.object.select_set(True)
        self.ob.select_set(True)
        bpy.context.view_layer.objects.active = self.ob
        bpy.context.view_layer.update()
        self.s.reference, self.s.center = 'LOCAL', 'SELECTION'
        tx = r.RotationSession(bpy.context)
        self.assertLess((g._center(bpy.context)-tx.gizmo_center).length, 1e-6)
        tx.cancel()
        self.s.reference, self.s.center = 'WORLD', 'COORDINATE'
        self.assertEqual(tuple(r.transform_center(bpy.context, 'SCALE')), (1, 0, 0))
        self.s.scale_reference = 'LOCAL'
        self.assertLess((r.transform_center(bpy.context, 'SCALE')-self.ob.matrix_world.translation).length, 1e-6,
                        'Local Scale must display its individual pivot before a centre is explicitly chosen')
        print('R3 PASS Local centre and Move/Scale centre contracts agree', flush=True)

    def test_R4_rotate_tripod_is_muted_except_locked_axes(self):
        self.assertTrue(hasattr(g, 'tripod_color'), 'tripod needs independent colour treatment')
        self.assertEqual(g.tripod_color('X', 'Z'), g.GREY)
        self.assertEqual(g.tripod_color('Y', 'Z'), g.GREY)
        self.assertEqual(g.tripod_color('Z', 'Z'), g.COLORS[2])
        print('R4 PASS Rotate-only tripod mutes inactive axes and colours locked axis', flush=True)

    def test_R4_rotate_tripod_is_not_a_ring_hit(self):
        data=dict(operation='ROTATE',lines=[('TRIPOD_X',[Vector((0,0)),Vector((30,0))],g.GREY,1)],
                  faces=[],rings={'FREE':[]},xy=Vector((0,0)),radius=100,ui=1)
        self.assertEqual(g.hit_test(data,Vector((10,0))),'FREE')

    def test_coincident_axis_ring_wins_over_free_trackball_outline(self):
        # In an orthographic principal view the axis ring and trackball outline
        # project to the same circle, with subpixel floating-point differences.
        for gap, expected in ((0, 'Z'), (.2, 'Z'), (2, 'FREE')):
            data = dict(operation='ROTATE', lines=[
                ('Z', [Vector((-50,100+gap)), Vector((50,100+gap))], g.COLORS[2], 1),
                ('FREE', [Vector((-50,100)), Vector((50,100))], g.GREY, 1)],
                faces=[], rings={'FREE': []}, xy=Vector((0,0)), radius=100, ui=1)
            self.assertEqual(g.hit_test(data, Vector((10,100))), expected)
            self.assertEqual(g.hit_test(data, Vector((0,20))), 'FREE')
            self.assertEqual(g.hit_test(data, Vector((0,130))), 'OFF')

    def test_R5_connected_move_and_nested_scale_handles(self):
        self.assertTrue(hasattr(g, 'plane_corners'), 'Move corners must connect to the axes')
        move = g.plane_corners('MOVE', .3, .6)
        self.assertEqual(move, ((0, 0), (.6, 0), (.6, .6), (0, .6)))
        scale = g.plane_corners('SCALE', .3, .6)
        self.assertEqual(scale, ((.3, 0), (.6, 0), (0, .6), (0, .3)))
        print('R5 PASS connected Move corners and nested triangular Scale regions', flush=True)

    def test_R6_live_absolute_and_offset_typein(self):
        self.assertTrue(hasattr(r, 'typein_apply'), 'Type-In must apply editable fields live')
        self.ob.rotation_euler = (0, 0, math.radians(12))
        bpy.context.view_layer.update()
        r.typein_apply(bpy.context, (0, 0, math.radians(37.3)), absolute=True)
        self.assertAlmostEqual(math.degrees(self.ob.matrix_world.to_euler().z), 37.3, places=4)
        r.typein_apply(bpy.context, (0, 0, math.radians(7.3)), absolute=False)
        self.assertAlmostEqual(math.degrees(self.ob.matrix_world.to_euler().z), 44.6, places=4)
        print('R6 PASS live absolute 37.3 and exact offset 7.3 degrees', flush=True)

    def test_R8_reference_systems_and_gizmo_controls(self):
        references = {key for key, *_ in r.REFERENCES}
        self.assertFalse({'GRID', 'WORKING', 'GIMBAL', 'LOCAL_ALIGNED'}-references)
        for name in ('show_labels', 'multiple_gizmos', 'move_size', 'rotate_size', 'scale_size',
                     'plane_offset', 'free_rotation', 'show_tripod', 'screen_handle',
                     'show_pie', 'angle_data', 'rotation_method', 'constant'):
            self.assertTrue(hasattr(self.s, name), name)
        self.s.reference = 'WORKING'
        self.s.working_rotation = (0, 0, math.pi/2)
        self.assertLess((r.reference_basis(bpy.context).col[0]-Vector((0, 1, 0))).length, 1e-5)
        print('R8 PASS reference systems and user-facing gizmo controls', flush=True)

    def test_R8_reference_clone_is_one_way(self):
        # This checks the standalone fallback. Integrated tools use shift_clone,
        # whose Reference sharing contract has its own suite.
        clone = r._ClonePreview(bpy.context)
        copy = bpy.context.active_object
        clone.finish(mode='REFERENCE')
        self.assertNotEqual(copy.data, self.ob.data, 'Reference needs independent downstream edits')
        self.ob.data.vertices[0].co.x = -2
        self.ob.data.update()
        bpy.context.view_layer.update()
        evaluated = copy.evaluated_get(bpy.context.evaluated_depsgraph_get())
        self.assertLess(min(v.co.x for v in evaluated.data.vertices), -1.9)
        self.assertTrue(any(m.type == 'NODES' for m in copy.modifiers))
        print('R8 PASS Reference follows source geometry with independent downstream stack', flush=True)

    def test_R8_multiple_gizmos_have_individual_centres(self):
        self.ob.location.x = -2
        bpy.ops.mesh.primitive_cube_add(size=1, location=(4, 0, 0))
        self.ob.select_set(True)
        bpy.context.view_layer.update()
        self.s.multiple_gizmos = True
        self.assertTrue(hasattr(g, 'centers'), 'multiple gizmos must generate per-object geometry')
        centers = g.centers(bpy.context, 'ROTATE')
        self.assertEqual(sorted(round(p.x) for p in centers), [-2, 4])
        print('R8 PASS multiple selected-object gizmos use individual pivots', flush=True)


suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReviewRegressions)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
addon_utils.disable('notuodesk_3ds_maxxed', default_set=True)
