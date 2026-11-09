"""Run with the isolated Blender profile, like test_xview.py."""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import test_xview as fixtures

mesh, bpy, xview = fixtures.mesh, fixtures.bpy, fixtures.xview


def drain(context=None, **kwargs):
    context = context or bpy.context
    result = xview.refresh(context, **kwargs)
    while xview.state_for(context).jobs or xview.state_for(context).view_jobs:
        result = xview.refresh(context, view=kwargs.get('view'))
    return result


class Rework(unittest.TestCase):
    setUp = fixtures.Checks.setUp

    def test_quad_overlap_and_coplanar_tolerance(self):
        ob = mesh('Quads', [(0,0,0),(2,0,0),(2,2,0),(0,2,0),
                            (.2,.2,.005),(1,.2,.005),(1,1,.005),(.2,1,.005)],
                  [(0,1,2,3),(4,5,6,7)])
        result = xview.analyze(ob, 'OVERLAPPING_FACES')
        self.assertEqual(result.indices, {0,1})
        self.assertEqual(len(result.triangles), 12)
        self.assertEqual(xview.analyze(ob, 'OVERLAPPING_FACES', tolerance=.001).indices, set())

    def test_default_and_independent_tolerances(self):
        ob = mesh('Default', [(0,0,0), (.005,0,0)])
        self.assertEqual(xview.analyze(ob, 'OVERLAPPING_VERTICES').indices, {0,1})
        s = bpy.context.scene.max_xview
        s.check = 'OVERLAPPING_VERTICES'
        s.tolerance = .002
        s.check = 'OVERLAPPING_FACES'
        self.assertAlmostEqual(s.tolerance, .01)
        s.tolerance = .03
        s.check = 'OVERLAPPING_VERTICES'
        self.assertAlmostEqual(s.tolerance, .002)

    def test_t_vertex_closed_neighborhood(self):
        ob = mesh('ClosedT', [(0,0,0),(1,0,0),(0,1,0),(0,0,1)],
                  [(0,2,1),(0,1,3),(0,3,2),(1,2,3)])
        self.assertEqual(xview.analyze(ob, 'T_VERTICES').indices, {0,1,2,3})
        wire = mesh('WireT', [(0,0,0),(1,0,0),(0,1,0),(0,0,1)], edges=[(0,1),(0,2),(0,3)])
        self.assertEqual(xview.analyze(wire, 'T_VERTICES').indices, set())

    def test_object_mode_uses_evaluated_mesh(self):
        ob = mesh('Weld', [(0,0,0),(0,0,0)])
        ob.modifiers.new('Weld', 'WELD')
        bpy.context.view_layer.update()
        self.assertEqual(xview.analyze(ob, 'OVERLAPPING_VERTICES').indices, set())

    def test_generated_topology_cannot_select_base_indices(self):
        ob = mesh('Solid', [(0,0,0),(1,0,0),(0,1,0)], [(0,1,2)])
        ob.modifiers.new('Solid', 'SOLIDIFY')
        bpy.context.view_layer.update()
        result = xview.analyze(ob, 'MISSING_UVW')
        self.assertTrue(result.indices)
        self.assertFalse(xview.select_results(bpy.context, {ob.name: result}))
        self.assertEqual(ob.mode, 'OBJECT')

    def test_scene_partition_and_unsupported_status(self):
        ob = mesh('Shared', [(0,0,0),(.0001,0,0)])
        ob.select_set(True)
        a = bpy.context.scene
        b = bpy.data.scenes.new('Other')
        b.collection.objects.link(ob)
        bpy.context.window.scene = b
        b.max_xview.check = 'OPEN_EDGES'
        bpy.context.window.scene = a
        a.max_xview.check = 'OVERLAPPING_VERTICES'
        self.assertEqual(drain()[ob.name].indices, {0,1})
        bpy.context.window.scene = b
        try:
            cached = xview.cached_results(bpy.context)
            self.assertEqual(cached, {})
            self.assertEqual(drain()[ob.name].indices, set())
            bpy.context.window.scene = a
            self.assertEqual(xview.cached_results(bpy.context)[ob.name].domain, 'VERT')
            ob.select_set(False)
            curve = bpy.data.objects.new('Curve', bpy.data.curves.new('Curve', 'CURVE'))
            a.collection.objects.link(curve)
            curve.select_set(True)
            drain()
            self.assertEqual(xview.state_for(bpy.context).status, 'Unsupported object type')
        finally:
            bpy.context.window.scene = a
            bpy.data.scenes.remove(b)

    def test_manual_update_preserves_mode_and_selection(self):
        ob = mesh('Manual', [(0,0,0),(.005,0,0)])
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        s = bpy.context.scene.max_xview
        s.check = 'OVERLAPPING_VERTICES'
        s.auto_update = False
        first = drain()[ob.name]
        self.assertEqual(first.indices, {0,1})
        ob.data.vertices[1].co.x = 2
        ob.data.update()
        bpy.context.view_layer.update()
        self.assertIs(drain()[ob.name], first)
        self.assertEqual(bpy.ops.max.xview_update(), {'FINISHED'})
        self.assertEqual(drain()[ob.name].indices, set())
        self.assertEqual(ob.mode, 'OBJECT')
        self.assertTrue(ob.select_get())

    def test_selected_curve_is_unsupported(self):
        curve = bpy.data.objects.new('Curve', bpy.data.curves.new('Curve', 'CURVE'))
        bpy.context.collection.objects.link(curve)
        curve.select_set(True)
        bpy.context.scene.max_xview.check = 'OPEN_EDGES'
        drain()
        status = xview.state_for(bpy.context).status
        self.assertEqual(status, 'Unsupported object type')

    def test_view_draw_reads_only_completed_orientation(self):
        ob = mesh('View', [(0,0,0),(1,0,0),(0,1,0)], [(0,1,2)])
        ob.select_set(True)
        bpy.context.scene.max_xview.check = 'FACE_ORIENTATION'
        top, bottom = ((0.,0.,1.), None), ((0.,0.,-1.), None)
        drain(view=top)
        # A new draw direction must not run a full orientation pass in drawing.
        self.assertEqual(xview.cached_results(bpy.context, bottom)[ob.name].indices, set())
        self.assertEqual(drain(view=bottom)[ob.name].indices, {0})

    def test_cache_respects_changed_edit_poly_selection_level(self):
        ob = mesh('Level', [(0,0,0),(.0001,0,0)])
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.context.tool_settings.mesh_select_mode = (True,False,False)
        bpy.context.scene.max_xview.check = 'OVERLAPPING_VERTICES'
        self.assertEqual(drain()[ob.name].points, [])
        bpy.context.tool_settings.mesh_select_mode = (False,True,False)
        self.assertEqual(len(drain()[ob.name].points), 2)

    def test_activation_yields_and_cancels_stale_jobs(self):
        n = 100
        vertices = [(x,y,0) for y in range(n+1) for x in range(n+1)]
        faces = [(y*(n+1)+x, y*(n+1)+x+1, (y+1)*(n+1)+x) for y in range(n) for x in range(n)]
        ob = mesh('Yield', vertices, faces)
        ob.select_set(True)
        t = time.perf_counter()
        bpy.ops.max.xview_check(check='OVERLAPPING_FACES')
        self.assertLess(time.perf_counter()-t, .05)
        state = xview.state_for(bpy.context)
        self.assertTrue(state.jobs, 'activation must return before full analysis')
        s = bpy.context.scene.max_xview
        s.check = 'OPEN_EDGES'
        result = drain()[ob.name]
        self.assertEqual(result.domain, 'EDGE')
        self.assertEqual(len(result.indices), 3*n*n)
        self.assertFalse(state.jobs)


if __name__ == '__main__':
    names = [name for name in Rework.__dict__ if name.startswith('test_')]
    outcome = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Rework(n) for n in names))
    sys.exit(not outcome.wasSuccessful())
