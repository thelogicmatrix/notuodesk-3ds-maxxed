"""Round-two reproductions. Run via run_checks.py tests test_symmetry_scale_performance."""
import statistics
import time
import unittest
import addon_utils
import bmesh
import bpy
from mathutils import Vector

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import symmetry


def evaluated(ob):
    bpy.context.view_layer.update()
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    result = (len(mesh.vertices), len(mesh.polygons),
              sum(e.is_boundary for e in bm.edges),
              sum(not e.is_manifold for e in bm.edges))
    bm.free()
    ev.to_mesh_clear()
    return result


class ScalePerformanceTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        symmetry.reconcile()

    def cylinder(self, radial):
        bpy.ops.mesh.primitive_cylinder_add(vertices=60, radius=2000, depth=4000)
        ob = bpy.context.object
        p = symmetry.settings(symmetry.add(ob))
        p.radial, p.count, p.mirror_symmetry = radial, 7, True
        return ob, p

    def test_large_radial_cut_seam_is_closed(self):
        ob, p = self.cylinder(True)
        p.merge_threshold = 1e-7
        self.assertGreater(evaluated(ob)[2], 0)
        for threshold in (.01, .1, 1.):
            p.merge_threshold = threshold
            verts, faces, boundary, bad = evaluated(ob)
            self.assertGreater(faces, 0)
            print('SCALE RADIAL threshold=%g boundary=%d nonmanifold=%d' %
                  (threshold, boundary, bad), flush=True)
            self.assertEqual((boundary, bad), (0, 0))
        print('SYMMETRY ROUND2 PASS large Radial cut seam closed, permitted threshold repairs numerical separation', flush=True)

    def test_large_planar_cut_seam_is_closed(self):
        ob, p = self.cylinder(False)
        # A rotated plane also checks non-axis-aligned cut roundoff.
        p.mirror_object.rotation_euler = (.2, .3, .4)
        verts, faces, boundary, bad = evaluated(ob)
        self.assertGreater(faces, 0)
        self.assertEqual((boundary, bad), (0, 0))
        print('SYMMETRY ROUND2 PASS large Planar rotated cut seam closed', flush=True)

    def test_large_uncut_thin_detail_stays_separate(self):
        bpy.ops.mesh.primitive_cube_add(size=1)
        ob = bpy.context.object
        for v in ob.data.vertices:
            v.co = Vector((2000+v.co.x, 500+v.co.y, v.co.z*.003))
        ob.data.update()
        p = symmetry.settings(symmetry.add(ob))
        p.merge_threshold = 1.
        self.assertEqual(evaluated(ob), (16, 12, 0, 0))
        p.radial, p.count = True, 6
        self.assertEqual(evaluated(ob), (48, 36, 0, 0))
        print('SYMMETRY ROUND2 PASS large sliced source retains uncut 0.003-unit detail at Weld Threshold 1', flush=True)

    def test_saved_node_engine_upgrade_keeps_geometry_and_parameters(self):
        # Simulate a saved, obsolete graph with the durable marker and sockets.
        # Its obsolete output must be replaced, without changing its user data.
        ob, p = self.cylinder(True)
        p.count = 5
        p.mirror_object.location = (.3, .2, .1)
        expected = evaluated(ob)
        helper = p.mirror_object
        group = p.mod.node_group
        group['max_symmetry_revision'] = 0
        output = next(n for n in group.nodes if n.type == 'GROUP_OUTPUT')
        source = next(n for n in group.nodes if n.type == 'GROUP_INPUT')
        group.links.new(source.outputs['Geometry'], output.inputs[0])
        symmetry.reconcile()
        self.assertEqual(evaluated(ob), expected)
        self.assertEqual((p.count, p.radial, p.mirror_symmetry), (5, True, True))
        self.assertEqual(p.mirror_object, helper)
        print('SYMMETRY ROUND2 PASS obsolete saved graph upgrades with parameters and centre intact', flush=True)

    def test_source_crossing_plane_leaves_retained_fast_path(self):
        bpy.ops.mesh.primitive_cube_add()
        ob = bpy.context.object
        for v in ob.data.vertices:
            v.co.x += 2
        ob.data.update()
        symmetry.add(ob)
        self.assertEqual(evaluated(ob), (16, 12, 0, 0))
        for v in ob.data.vertices:
            if v.co.x == 1:
                v.co.x = -4
        ob.data.update()
        self.assertEqual(evaluated(ob), (12, 10, 0, 0))
        bpy.context.view_layer.update()
        ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ev.to_mesh()
        self.assertLessEqual(max(abs(v.co.x) for v in mesh.vertices), 3)
        ev.to_mesh_clear()
        print('SYMMETRY ROUND2 PASS crossing source leaves fast path and cuts a closed seam', flush=True)

    def test_default_slice_20k_native_vertex_updates_under_50ms(self):
        bpy.ops.mesh.primitive_cube_add()
        ob = bpy.context.object
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.subdivide_edges(bm, edges=list(bm.edges), cuts=57, use_grid_fill=True)
        bm.faces.ensure_lookup_table()
        self.assertEqual(len(bm.faces), 20184)
        bmesh.ops.delete(bm, geom=list(bm.faces)[:184], context='FACES')
        bm.to_mesh(ob.data)
        bm.free()
        for v in ob.data.vertices:
            v.co = Vector((2+v.co.x*.3, .7+v.co.y*.3, v.co.z*.3))
        ob.data.update()
        self.assertEqual(len(ob.data.polygons), 20000)
        p = symmetry.settings(symmetry.add(ob))
        p.radial, p.count = True, 6
        bpy.ops.max.subobject(level=1)
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        for v in bm.verts:
            v.select = False
        bm.verts[0].select = True
        bmesh.update_edit_mesh(ob.data)
        # Match the review timer. Do not include our topology inspection cost.
        def update():
            bpy.context.view_layer.update()
            ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = ev.to_mesh()
            faces = len(mesh.polygons)
            ev.to_mesh_clear()
            return faces
        self.assertEqual(update(), 120000)
        samples = []
        for _ in range(4):
            start = time.perf_counter()
            self.assertEqual(bpy.ops.transform.translate(value=(0, 0, .001)), {'FINISHED'})
            faces = update()
            samples.append(1000*(time.perf_counter()-start))
            self.assertEqual(faces, 120000)
        median = statistics.median(samples)
        print('SYMMETRY ROUND2 20k native transform+evaluation median_ms=%.3f samples_ms=%r' %
              (median, samples), flush=True)
        self.assertLess(median, 50)
        print('SYMMETRY ROUND2 PASS default slice responsive on 20k open segment', flush=True)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ScalePerformanceTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
