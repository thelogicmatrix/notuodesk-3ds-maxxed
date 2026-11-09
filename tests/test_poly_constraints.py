"""Run with isolated Blender: blender -b --factory-startup --python tests/test_poly_constraints.py."""
import importlib.util
import os
import unittest

import addon_utils
import bpy
import bmesh
from mathutils import Matrix, Vector

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
assert importlib.util.find_spec("notuodesk_3ds_maxxed.poly_constraints"), "Editable Poly move constraints are not implemented"
from notuodesk_3ds_maxxed import poly_constraints as pc


def fixture(verts, faces=(), edges=(), selected=(0,), level=1):
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    me = bpy.data.meshes.new("Constraint fixture")
    me.from_pydata(verts, edges, faces)
    ob = bpy.data.objects.new("Constraint fixture", me)
    bpy.context.collection.objects.link(ob)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.max.subobject(level=level)
    bpy.ops.mesh.select_all(action="DESELECT")
    bm = bmesh.from_edit_mesh(me)
    bm.verts.ensure_lookup_table()
    for i in selected:
        bm.verts[i].select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(me)
    return ob, bm


QUAD = [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)]


class Constraints(unittest.TestCase):
    def assertVector(self, actual, expected):
        self.assertLess((Vector(actual) - Vector(expected)).length, 1e-5)

    def test_edge_each_vertex_stays_on_original_edge(self):
        ob, bm = fixture(QUAD, [(0, 1, 2, 3)], selected=(0, 2))
        ob.max_poly.constraints = "EDGE"
        originals = {v.index: (v.co.copy(), [e.other_vert(v).co.copy() for e in v.link_edges]) for v in bm.verts if v.select}
        session = pc.MoveSession(bpy.context)
        session.apply(Vector((.65, .17, .8)))
        for i, (start, ends) in originals.items():
            self.assertTrue(any((bm.verts[i].co-start).cross(end-start).length < 1e-5 for end in ends))
        self.assertGreater((bm.verts[0].co-originals[0][0]).length, .1)
        session.finish()

    def test_edge_selection_uses_unselected_rails(self):
        ob, bm = fixture(QUAD, [(0, 1, 2, 3)], level=2)
        bm.edges.ensure_lookup_table()
        edge = next(e for e in bm.edges if {v.index for v in e.verts} == {0, 1})
        edge.select_set(True)
        bm.select_flush_mode()
        ob.max_poly.constraints = "EDGE"
        session = pc.MoveSession(bpy.context)
        session.apply(Vector((.4, .6, .8)))
        self.assertVector(bm.verts[0].co, (0, .6, 0))
        self.assertVector(bm.verts[1].co, (2, .6, 0))
        session.finish()

    def test_edge_clamps_to_boundary_and_cancel_restores(self):
        ob, bm = fixture(QUAD, [(0, 1, 2, 3)])
        ob.max_poly.constraints = "EDGE"
        session = pc.MoveSession(bpy.context)
        session.apply(Vector((12, .1, 0)))
        self.assertVector(bm.verts[0].co, (2, 0, 0))
        session.cancel()
        self.assertVector(bm.verts[0].co, QUAD[0])

    def test_face_projects_individual_vertices_to_frozen_surface(self):
        # Two perpendicular faces, selected vertices must keep their original surface.
        ob, bm = fixture(QUAD + [(2, 0, 2), (2, 2, 2)], [(0,1,2,3), (1,4,5,2)], selected=(0, 5))
        ob.max_poly.constraints = "FACE"
        session = pc.MoveSession(bpy.context)
        session.apply(Vector((.3, .2, .4)))
        self.assertVector(bm.verts[0].co, (.3, .2, 0))
        self.assertVector(bm.verts[5].co, (2, 2, 2))
        # Preview is always evaluated against the pre-move mesh, never its last preview.
        session.apply(Vector((.4, .4, .7)))
        self.assertVector(bm.verts[0].co, (.4, .4, 0))
        session.finish()

    def test_face_projection_uses_world_space_under_nonuniform_scale(self):
        ob, bm = fixture(QUAD, [(0,1,2,3)])
        ob.matrix_world = Matrix.Diagonal((2, 3, .5, 1))
        ob.max_poly.constraints = "FACE"
        session = pc.MoveSession(bpy.context)
        session.apply(Vector((.6, .6, 1)))
        self.assertVector(ob.matrix_world @ bm.verts[0].co, (.6, .6, 0))
        session.finish()

    def test_normal_uses_averaged_original_vertex_normal(self):
        ob, bm = fixture([(0,0,0), (2,0,0), (2,2,0), (0,2,0), (0,0,2), (2,0,2)], [(0,1,2,3), (0,4,5,1)])
        bm.normal_update()
        normal = bm.verts[0].normal.copy()
        start = bm.verts[0].co.copy()
        ob.max_poly.constraints = "NORMAL"
        session = pc.MoveSession(bpy.context)
        session.apply(Vector((1, 2, 3)), normal_distance=.5)
        self.assertVector(bm.verts[0].co, start + normal * .5)
        session.finish()

    def test_none_is_ordinary_translation(self):
        ob, bm = fixture(QUAD, [(0,1,2,3)], selected=(0,1))
        self.assertEqual(ob.max_poly.constraints, "NONE")
        session = pc.MoveSession(bpy.context)
        delta = Vector((.2, .3, .4))
        session.apply(delta)
        for i in (0,1):
            self.assertVector(bm.verts[i].co, Vector(QUAD[i]) + delta)
        self.assertVector(bm.verts[2].co, QUAD[2])
        session.finish()

    def test_settings_are_per_object_and_survive_level_changes(self):
        ob, bm = fixture(QUAD, [(0,1,2,3)])
        ob.max_poly.constraints = "EDGE"
        for level in (2, 3, 4, 5, 0, 1):
            bpy.ops.max.subobject(level=level)
            self.assertEqual(ob.max_poly.constraints, "EDGE")
        other = bpy.data.objects.new("Other", ob.data.copy())
        bpy.context.collection.objects.link(other)
        self.assertEqual(other.max_poly.constraints, "NONE")

    def test_snap_settings_restored_after_finish_and_cancel(self):
        for mode in ("EDGE", "FACE", "NORMAL"):
            for cancel in (False, True):
                ob, bm = fixture(QUAD, [(0,1,2,3)])
                ob.max_poly.constraints = mode
                ts = bpy.context.tool_settings
                ts.use_snap, ts.snap_elements, ts.snap_target = True, {"VERTEX", "EDGE"}, "CENTER"
                ts.use_snap_self = False
                saved = pc.snap_settings(ts)
                session = pc.MoveSession(bpy.context)
                session.apply(Vector((.3,.2,.1)))
                # A competing snap tool can change these while its transform is active.
                ts.snap_elements, ts.use_snap_self = {"FACE"}, True
                session.cancel() if cancel else session.finish()
                self.assertEqual(pc.snap_settings(ts), saved)

    def test_saved_objects_keep_independent_constraints(self):
        ob, bm = fixture(QUAD, [(0,1,2,3)])
        ob.max_poly.constraints = "EDGE"
        other = bpy.data.objects.new("Other", ob.data.copy())
        bpy.context.collection.objects.link(other)
        other.max_poly.constraints = "NORMAL"
        path = os.path.join(os.environ["MAXXED_SANDBOX"], "temp", "constraints-persistence.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
        self.assertEqual(bpy.data.objects["Constraint fixture"].max_poly.constraints, "EDGE")
        self.assertEqual(bpy.data.objects["Other"].max_poly.constraints, "NORMAL")

    def test_operator_one_step_undo_redo(self):
        ob, bm = fixture(QUAD, [(0,1,2,3)])
        ob.max_poly.constraints = "EDGE"
        bpy.context.preferences.edit.use_global_undo = True
        bpy.ops.ed.undo_push(message="Before constrained move")
        self.assertEqual(bpy.ops.max.poly_move(value=(.5, .1, .2)), {"FINISHED"})
        self.assertVector(bmesh.from_edit_mesh(bpy.context.object.data).verts[0].co, (.5,0,0))
        # Timer-driven GUI also checks the operator's automatic undo boundary.
        bpy.ops.ed.undo_push(message="After constrained move")
        self.assertEqual(bpy.ops.ed.undo(), {"FINISHED"})
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        bm.verts.ensure_lookup_table()
        self.assertVector(bm.verts[0].co, QUAD[0])
        self.assertEqual(bpy.ops.ed.redo(), {"FINISHED"})
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        bm.verts.ensure_lookup_table()
        self.assertVector(bm.verts[0].co, (.5,0,0))


suite = unittest.defaultTestLoader.loadTestsFromTestCase(Constraints)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
print("PASS Poly Constraints geometry, per-object settings, snap restoration and undo", flush=True)
