"""Run: blender -b --factory-startup --python-exit-code 1 --python tests/test_xview.py.

Set BLENDER_USER_SCRIPTS to the isolated sb-xview/scripts directory first.
"""

import sys
import unittest

import addon_utils
import bmesh
import bpy

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
from notuodesk_3ds_maxxed import xview


def refresh(**kwargs):
    result = xview.refresh(**kwargs)
    while xview.state_for(bpy.context).jobs or xview.state_for(bpy.context).view_jobs:
        result = xview.refresh(view=kwargs.get("view"))
    return result


def mesh(name, vertices, faces=(), edges=(), uvs=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(vertices, edges, faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.update()
    if uvs is not None:
        layer = me.uv_layers.new()
        for loop, uv in zip(layer.data, uvs):
            loop.uv = uv
    return ob


class Checks(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode == "EDIT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        xview.clear_cache()
        for prop in ("check", "selected_only", "vertex_tolerance", "face_tolerance", "auto_update"):
            if prop in bpy.context.scene.max_xview.bl_rna.properties:
                bpy.context.scene.max_xview.property_unset(prop)

    def verify(self, ob, check, expected, domain, **kwargs):
        result = xview.analyze(ob, check, **kwargs)
        self.assertEqual(result.domain, domain)
        self.assertEqual(result.indices, set(expected))
        xview.select_results(bpy.context, {ob.name: result})
        bm = bmesh.from_edit_mesh(ob.data)
        elements = {"VERT": bm.verts, "EDGE": bm.edges, "FACE": bm.faces}[domain]
        self.assertEqual({e.index for e in elements if e.select}, set(expected))
        print(f"PASS {check}: {len(expected)} {domain}, exact selected indices {sorted(expected)}", flush=True)
        bpy.ops.object.mode_set(mode="OBJECT")
        return result

    def test_face_orientation(self):
        ob = mesh("Orientation", [(0,0,0),(1,0,0),(0,1,0),(2,0,0),(3,0,0),(2,1,0)],
                  [(0,1,2),(3,5,4)])
        self.verify(ob, "FACE_ORIENTATION", {1}, "FACE")
        self.assertEqual(xview.analyze(ob, "FACE_ORIENTATION", view_direction=(0,0,-1)).indices, {0})

    def test_overlapping_faces(self):
        ob = mesh("Overlap", [(0,0,0),(2,0,0),(0,2,0),(.2,.2,0),(1,.2,0),(.2,1,0)],
                  [(0,1,2),(3,4,5)])
        self.verify(ob, "OVERLAPPING_FACES", {0,1}, "FACE")

    def test_open_edges(self):
        ob = mesh("Open", [(0,0,0),(1,0,0),(1,1,0),(0,1,0)], [(0,1,2),(0,2,3)])
        expected = {e.index for e in ob.data.edges if set(e.vertices) != {0,2}}
        self.verify(ob, "OPEN_EDGES", expected, "EDGE")

    def test_multiple_edges(self):
        ob = mesh("Multiple", [(0,0,0),(1,0,0),(0,1,0),(0,-1,0),(0,0,1)],
                  [(0,1,2),(1,0,3),(0,1,4)])
        expected = {e.index for e in ob.data.edges if set(e.vertices) == {0,1}}
        self.verify(ob, "MULTIPLE_EDGES", expected, "EDGE")

    def test_multiple_flipped_boundary(self):
        ob = mesh("Flipped", [(0,0,0),(1,0,0),(1,1,0),(0,1,0)], [(0,1,2),(0,3,2)])
        expected = {e.index for e in ob.data.edges if set(e.vertices) == {0,2}}
        self.verify(ob, "MULTIPLE_EDGES", expected, "EDGE")

    def test_isolated_vertices(self):
        ob = mesh("Stray", [(0,0,0),(1,0,0),(0,1,0),(3,3,3),(4,4,4),(5,4,4)],
                  [(0,1,2)], [(4,5)])
        self.verify(ob, "ISOLATED_VERTICES", {3}, "VERT")

    def test_overlapping_vertices(self):
        ob = mesh("Close", [(0,0,0),(.0001,0,0),(2,0,0)])
        self.verify(ob, "OVERLAPPING_VERTICES", {0,1}, "VERT", tolerance=.001)
        self.assertEqual(xview.analyze(ob, "OVERLAPPING_VERTICES", tolerance=.00001).indices, set())
        ob.scale.x = 20
        bpy.context.view_layer.update()
        self.assertEqual(xview.analyze(ob, "OVERLAPPING_VERTICES", tolerance=.001).indices, set())

    def test_t_vertices(self):
        ob = mesh("T", [(0,0,0),(1,0,0),(0,1,0),(0,0,1)],
                  [(0,2,1),(0,1,3),(0,3,2),(1,2,3)])
        self.verify(ob, "T_VERTICES", {0,1,2,3}, "VERT")

    def test_t_junction_tolerance(self):
        ob = mesh("UnweldedT", [(-1,0,0),(1,0,0),(0,.0001,0),(0,1,0)], edges=[(0,1),(2,3)])
        self.verify(ob, "T_VERTICES", set(), "VERT", tolerance=.001)
        self.assertEqual(xview.analyze(ob, "T_VERTICES", tolerance=.00001).indices, set())

    def test_missing_uvw(self):
        ob = mesh("NoUV", [(0,0,0),(1,0,0),(0,1,0)], [(0,1,2)])
        self.verify(ob, "MISSING_UVW", {0}, "FACE")
        ob.data.uv_layers.new()
        self.assertEqual(xview.analyze(ob, "MISSING_UVW").indices, set())

    def test_flipped_uvw(self):
        ob = mesh("FlipUV", [(0,0,0),(1,0,0),(0,1,0),(2,0,0),(3,0,0),(2,1,0)],
                  [(0,1,2),(3,4,5)], uvs=[(0,0),(1,0),(0,1),(2,0),(2,1),(3,0)])
        self.verify(ob, "FLIPPED_UVW", {1}, "FACE")

    def test_overlapped_uvw(self):
        ob = mesh("OverlapUV", [(0,0,0),(1,0,0),(0,1,0),(2,0,0),(3,0,0),(2,1,0)],
                  [(0,1,2),(3,4,5)], uvs=[(0,0),(1,0),(0,1),(.1,.1),(.5,.1),(.1,.5)])
        self.verify(ob, "OVERLAPPED_UVW", {0,1}, "FACE")

    def test_adjacent_faces_not_overlap(self):
        ob = mesh("Adjacent", [(0,0,0),(1,0,0),(1,1,0),(0,1,0)], [(0,1,2),(0,2,3)],
                  uvs=[(0,0),(1,0),(1,1),(0,0),(1,1),(0,1)])
        for check in ("OVERLAPPING_FACES", "OVERLAPPED_UVW", "MULTIPLE_EDGES"):
            self.assertEqual(xview.analyze(ob, check).indices, set())

    def test_edit_mesh_live(self):
        ob = mesh("Edit", [(0,0,0),(.0001,0,0),(2,0,0)])
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        bm.verts[1].co.x = 1
        bmesh.update_edit_mesh(ob.data)
        self.assertEqual(xview.analyze(ob, "OVERLAPPING_VERTICES").indices, set())
        print("PASS EDIT_MESH: live BMesh coordinates", flush=True)

    def test_cache_updates_only_checked_objects(self):
        ob = mesh("Checked", [(0,0,0),(.0001,0,0)])
        other = mesh("Unrelated", [(4,0,0)])
        ob.select_set(True)
        settings = bpy.context.scene.max_xview
        settings.check = "OVERLAPPING_VERTICES"
        settings.auto_update = True
        first = refresh()[ob.name]
        self.assertEqual(first.indices, {0,1})
        self.assertIs(refresh()[ob.name], first)
        other.data.vertices[0].co.x = 9
        other.data.update()
        bpy.context.view_layer.update()
        self.assertIs(refresh()[ob.name], first)
        ob.data.vertices[1].co.x = 2
        ob.data.update()
        bpy.context.view_layer.update()
        second = refresh()[ob.name]
        self.assertIsNot(first, second)
        self.assertEqual(second.indices, set())
        settings.auto_update = False
        ob.data.vertices[1].co.x = .0001
        ob.data.update()
        bpy.context.view_layer.update()
        self.assertIs(refresh()[ob.name], second)
        self.assertEqual(refresh(force=True)[ob.name].indices, {0,1})
        settings.auto_update = True
        settings.check = "NONE"
        print("PASS CACHE: reused, unrelated edits ignored, checked edits refreshed, Auto Update off held", flush=True)

    def test_selected_only_and_multiobject_selection(self):
        a = mesh("A", [(0,0,0),(.0001,0,0)])
        b = mesh("B", [(2,0,0),(2.0001,0,0)])
        a.select_set(True)
        settings = bpy.context.scene.max_xview
        settings.check = "OVERLAPPING_VERTICES"
        settings.selected_only = True
        self.assertEqual(set(refresh()), {"A"})
        settings.selected_only = False
        results = refresh()
        self.assertEqual(set(results), {"A", "B"})
        xview.select_results(bpy.context, results)
        for ob in (a,b):
            bm = bmesh.from_edit_mesh(ob.data)
            self.assertEqual({v.index for v in bm.verts if v.select}, {0,1})
        settings.selected_only = True
        settings.check = "NONE"
        print("PASS SELECTED_ONLY: selected mesh or all visible meshes, multi-object Select Results", flush=True)

    def test_partial_crossing_and_offset_overlap(self):
        ob = mesh("Cross", [(-2,-1,0),(2,-1,0),(0,2,0),(-2,1,.0005),(0,-2,.0005),(2,1,.0005)],
                  [(0,1,2),(3,4,5)])
        self.assertEqual(xview.analyze(ob, "OVERLAPPING_FACES", tolerance=.001).indices, {0,1})
        self.assertEqual(xview.analyze(ob, "OVERLAPPING_FACES", tolerance=.0001).indices, set())

    def test_orientation_per_view_reuses_mesh_snapshot(self):
        ob = mesh("TwoSides", [(0,0,0),(1,0,0),(0,1,0),(2,0,0),(3,0,0),(2,1,0)],
                  [(0,1,2),(3,5,4)])
        ob.select_set(True)
        bpy.context.scene.max_xview.check = "FACE_ORIENTATION"
        top = ((0.,0.,1.), None)
        bottom = ((0.,0.,-1.), None)
        self.assertEqual(refresh(view=top)[ob.name].indices, {1})
        snapshot = xview.state_for(bpy.context).cache[ob.name][1]
        self.assertEqual(refresh(view=bottom)[ob.name].indices, {0})
        self.assertIs(xview.state_for(bpy.context).cache[ob.name][1], snapshot)
        bpy.context.scene.max_xview.check = "NONE"
        print("PASS FACE_ORIENTATION: independent view results, same mesh snapshot", flush=True)

    def test_selected_elements_keep_normal_edit_poly_color(self):
        ob = mesh("Selected", [(0,0,0),(.0001,0,0)])
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.context.tool_settings.mesh_select_mode = (True, False, False)
        bm = bmesh.from_edit_mesh(ob.data)
        for v in bm.verts:
            v.select_set(True)
        bmesh.update_edit_mesh(ob.data)
        result = xview.analyze(ob, "OVERLAPPING_VERTICES")
        self.assertEqual(result.indices, {0,1})
        self.assertEqual(result.points, [])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    if not outcome.wasSuccessful():
        sys.exit(1)
