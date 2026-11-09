"""Run in isolated Blender with run_checks.py tests test_poly_constraints_fixes."""
import math
import statistics
import time
import unittest

import addon_utils
import bpy
import bmesh
from mathutils import Matrix, Vector

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import poly_constraints as pc


def fixture(verts, faces, selected=(0,)):
    pc.teardown()
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    me = bpy.data.meshes.new('Fix regression')
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new('Fix regression', me)
    bpy.context.collection.objects.link(ob)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.max.subobject(level=1)
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(me)
    bm.verts.ensure_lookup_table()
    for i in selected:
        bm.verts[i].select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    ob.max_poly.constraints = 'EDGE'
    return ob, bm


QUAD = [(0,0,0), (2,0,0), (2,2,0), (0,2,0)]


class Fixes(unittest.TestCase):
    def tearDown(self):
        pc.teardown()

    def vector(self, actual, expected):
        self.assertLess((Vector(actual)-Vector(expected)).length, 1e-5)

    def test_R5_edge_straight_drag_keeps_short_rail(self):
        ob, bm = fixture([(0,0,0),(.2,0,0),(.2,2,0),(0,2,0)], [(0,1,2,3)])
        s = pc.MoveSession(bpy.context)
        for delta in ((.4,.2,0),(1.6,.8,0),(4,2,0)):
            s.apply(delta)
            self.vector(bm.verts[0].co, (.2,0,0))
        # A deliberate direction change selects Y, without dependence on length.
        s.apply((.1,.8,0))
        self.vector(bm.verts[0].co, (0,.8,0))
        print('PASS R5 straight Edge drag holds X endpoint, deliberate turn selects Y', flush=True)

    def test_R3_face_cannot_jump_to_disconnected_quad(self):
        ob, bm = fixture(QUAD + [(x,y,.1) for x,y,z in QUAD], [(0,1,2,3),(4,5,6,7)])
        ob.max_poly.constraints = 'FACE'
        s = pc.MoveSession(bpy.context)
        s.apply((.3,.3,.08))
        self.vector(bm.verts[0].co, (.3,.3,0))
        print('PASS R3 Face stays on original incident polygon at Z=0', flush=True)

    def test_R4_normal_opposed_islands_and_closed_mesh(self):
        ob, bm = fixture(QUAD + [(x,y,.1) for x,y,z in QUAD], [(0,1,2,3),(7,6,5,4)], (0,4))
        ob.max_poly.constraints = 'NORMAL'
        s = pc.MoveSession(bpy.context)
        s.apply((0,0,1))
        self.vector(bm.verts[0].co, (0,0,1))
        self.vector(bm.verts[4].co, (0,0,-.9))
        s.cancel()
        verts = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
        ob, bm = fixture(verts, [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], range(8))
        ob.max_poly.constraints = 'NORMAL'
        normals = [v.normal.copy() for v in bm.verts]
        s = pc.MoveSession(bpy.context)
        s.apply((1,0,0))
        for v, start, normal in zip(bm.verts, verts, normals):
            self.vector(v.co, Vector(start)+normal)
        print('PASS R4 opposing islands and fully selected cube move along individual normals', flush=True)

    def test_R2_current_rotate_and_scale_respect_edge(self):
        ob, bm = fixture(QUAD, [(0,1,2,3)], (0,1))
        # Missing operator falls back to the old native path to reproduce the defect.
        op = getattr(bpy.ops.max, 'poly_transform')
        available = hasattr(bpy.types, 'MAX_OT_poly_transform')
        if available:
            op(kind='ROTATE', angle=.4, pivot=(0,0,0), axis=(0,0,1))
        else:
            bpy.ops.transform.rotate(value=.4, orient_axis='Z', center_override=(0,0,0))
        self.vector(bm.verts[1].co, (2, 2*math.sin(.4), 0))
        ob, bm = fixture(QUAD, [(0,1,2,3)], (0,1))
        if available:
            op(kind='SCALE', factors=(.5,1.5,2), pivot=(-1,-1,-1))
        else:
            bpy.ops.transform.resize(value=(.5,1.5,2), center_override=(-1,-1,-1))
        self.vector(bm.verts[0].co, (0,.5,0))
        self.vector(bm.verts[1].co, (.5,0,0))
        print('PASS R2 current Rotate and Scale project per-vertex displacement onto Edge', flush=True)

    def test_R6_dense_edge_preview_budget(self):
        n = 224
        verts = [(x,y,0) for y in range(n+1) for x in range(n+1)]
        faces = [(y*(n+1)+x,y*(n+1)+x+1,(y+1)*(n+1)+x+1,(y+1)*(n+1)+x) for y in range(n) for x in range(n)]
        ob, bm = fixture(verts, faces, range(len(verts)))
        begin = time.perf_counter()
        s = pc.MoveSession(bpy.context)
        init = time.perf_counter()-begin
        times = []
        for i in range(7):
            begin = time.perf_counter()
            s.apply((.1+i*.02,.04,0))
            times.append((time.perf_counter()-begin)*1000)
        median = statistics.median(times)
        print(f'R6 TIMING selected=50625 faces=50176 median_ms={median:.3f} init_s={init:.3f} samples=7', flush=True)
        self.assertLess(median, 80, 'Dense Edge geometry preview exceeds 80 ms on Reborn')
        self.assertGreater(bm.verts[1000].co.x, verts[1000][0])
        print('PASS R6 dense Edge median geometry preview below 80 ms', flush=True)

    def test_shared_targets_hook_uses_frozen_starts_and_restores(self):
        for mode, target in [('EDGE', (.3,0,0)), ('FACE', (.3,.2,0)), ('NORMAL', (0,0,.4))]:
            ob, bm = fixture(QUAD, [(0,1,2,3)])
            ob.matrix_world = Matrix.Diagonal((2,3,.5,1))
            ob.max_poly.constraints = mode
            s = pc.MoveSession(bpy.context)
            for _ in range(3):
                s.apply_targets({ob: {0: Vector((.3,.2,.4))}})
                self.vector(ob.matrix_world @ bm.verts[0].co, target)
            s.cancel()
            self.vector(bm.verts[0].co, (0,0,0))
        print('PASS shared apply_targets hook uses frozen world positions and cancels every constraint', flush=True)


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Fixes))
if not result.wasSuccessful():
    raise SystemExit(1)
print('PASS Poly Constraints fix regressions', flush=True)
