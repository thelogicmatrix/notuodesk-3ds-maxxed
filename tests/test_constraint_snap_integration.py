"""Integrated snap transform geometry and clone constraints. Run via run_checks.py."""
import unittest
from types import SimpleNamespace
import addon_utils
import bpy
import bmesh
from mathutils import Matrix, Vector
addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import poly_constraints as pc, snaps, shift_clone

class Integration(unittest.TestCase):
    def setUp(self):
        pc.teardown()
        if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
        for ob in list(bpy.data.objects): bpy.data.objects.remove(ob, do_unlink=True)
        me=bpy.data.meshes.new('Constraint integration')
        me.from_pydata([(0,0,0),(2,0,0),(2,2,0),(0,2,0)],[],[(0,1,2,3)])
        self.ob=bpy.data.objects.new('Constraint integration',me)
        bpy.context.collection.objects.link(self.ob)
        self.ob.select_set(True)
        bpy.context.view_layer.objects.active=self.ob
        bpy.ops.max.subobject(level=1)
        bpy.ops.mesh.select_all(action='DESELECT')
        bm=bmesh.from_edit_mesh(me)
        bm.verts.ensure_lookup_table()
        bm.verts[0].select_set(True)
        bmesh.update_edit_mesh(me)
        self.ob.max_poly.constraints='EDGE'
    def tearDown(self): pc.teardown()
    def point(self,i=0):
        bm=bmesh.from_edit_mesh(self.ob.data)
        bm.verts.ensure_lookup_table()
        return bm.verts[i].co.copy()
    def operator(self,tx):
        return SimpleNamespace(matrices=[],meshes=[(self.ob,[(0,Vector())])],constraint_tx=tx,kind='MOVE',normal_distance=None)
    def test_shared_snap_apply_constrains_requested_positions(self):
        tx=pc.MoveSession(bpy.context)
        op=self.operator(tx)
        snaps.MAX_OT_snap_transform._apply(op,bpy.context,Matrix.Translation((.8,.3,0)))
        self.assertLess((self.point()-Vector((.8,0,0))).length,1e-5)
        tx.cancel()
    def test_clone_uses_original_rails_and_leaves_source(self):
        tx=pc.MoveSession(bpy.context)
        clones=shift_clone.MeshClones(bpy.context)
        tx.retarget_clones(clones)
        tx.apply_targets({},move_delta=Vector((.8,.3,0)))
        bm=bmesh.from_edit_mesh(self.ob.data)
        self.assertLess(self.point().length,1e-5)
        self.assertLess((clones.parts[0].new_verts[0].co-Vector((.8,0,0))).length,1e-5)
        tx.finish()
        clones.cancel()
        self.assertEqual(len(bm.verts),4)
    def test_clone_lifecycle_cancels_constraints_before_topology(self):
        tx=pc.MoveSession(bpy.context)
        clones=shift_clone.MeshClones(bpy.context)
        tx.retarget_clones(clones)
        tx.apply_targets({},move_delta=Vector((.8,.3,0)))
        # Undo/load/disable cancel clones before the constraint handler runs.
        clones.cancel()
        # Avoid a second invalid-index exception while preserving the failure.
        closed=tx.closed
        if not closed:
            tx.finish()
        self.assertTrue(closed, 'Clone lifecycle removed preview topology before closing its constraint session')
        self.assertEqual(len(bmesh.from_edit_mesh(self.ob.data).verts),4)
    def test_clone_cancel_restores_geometry(self):
        tx=pc.MoveSession(bpy.context)
        clones=shift_clone.MeshClones(bpy.context)
        tx.retarget_clones(clones)
        tx.apply_targets({},move_delta=Vector((.8,.3,0)))
        tx.cancel()
        clones.cancel()
        self.assertLess(self.point().length,1e-5)
        self.assertEqual(len(bmesh.from_edit_mesh(self.ob.data).verts),4)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Integration))
    addon_utils.disable('notuodesk_3ds_maxxed')
    if not result.wasSuccessful(): raise SystemExit(1)
