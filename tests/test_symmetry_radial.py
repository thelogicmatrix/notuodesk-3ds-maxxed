"""Radial geometry acceptance. Run via run_checks.py tests test_symmetry_radial."""
import math
import unittest
import addon_utils
import bpy
from mathutils import Matrix, Vector

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import symmetry


def meshinfo(ob):
    import bmesh
    bpy.context.view_layer.update()
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    result = ([v.co.copy() for v in mesh.vertices], len(mesh.polygons),
              sum(not e.is_manifold for e in bm.edges))
    bm.free()
    ev.to_mesh_clear()
    return result


class RadialTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        symmetry.reconcile()
        bpy.ops.mesh.primitive_cube_add(size=.2, location=(2, .4, 0))
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
        self.ob = bpy.context.object
        self.mod = symmetry.settings(symmetry.add(self.ob))

    def radial(self, count, **values):
        p = symmetry.settings(self.mod)
        p.radial = True
        p.count = count
        p.radial_axis = 2
        for key, value in values.items():
            setattr(p, key, value)
        return p

    def test_counts_and_live_edit_all_levels(self):
        import bmesh
        for count in (2, 3, 5, 6, 7, 12):
            p = self.radial(count, slice=False, weld=False)
            coords, faces, _ = meshinfo(self.ob)
            self.assertEqual((len(coords), faces), (8*count, 6*count))
            for level in range(1, 6):
                bpy.ops.max.subobject(level=level)
                bm = bmesh.from_edit_mesh(self.ob.data)
                bm.verts.ensure_lookup_table()
                bm.verts[0].co.z += .01
                source = bm.verts[0].co.copy()
                bmesh.update_edit_mesh(self.ob.data)
                coords, _, _ = meshinfo(self.ob)
                for i in range(count):
                    wanted = Matrix.Rotation(i*math.tau/count, 4, 'Z') @ source
                    self.assertTrue(any((v-wanted).length < 1e-4 for v in coords))
                bpy.ops.object.mode_set(mode='OBJECT')
            print('RADIAL PASS count=%d live levels=1,2,3,4,5' % count, flush=True)

    def test_axis_and_transformed_centre(self):
        p = self.radial(3, slice=False, weld=False)
        for axis in range(3):
            p.radial_axis = axis
            centre = symmetry.plane(self.mod)
            centre.location = (.3, -.2, .1)
            centre.rotation_euler = (.2, .3, .4)
            bpy.context.view_layer.update()
            frame = centre.matrix_basis.copy()
            coords, _, _ = meshinfo(self.ob)
            source = self.ob.data.vertices[0].co
            for i in range(3):
                target = frame @ Matrix.Rotation(i*math.tau/3, 4, 'XYZ'[axis]) @ frame.inverted() @ source
                self.assertTrue(any((v-target).length < 2e-4 for v in coords))
        print('RADIAL PASS X/Y/Z and moved rotated centre', flush=True)

    def test_slice_weld_and_mirror_segments(self):
        # A rotationally matching cylinder crossing both radial boundaries.
        # Cutting must produce
        # open segment sides, not internal Boolean caps or overlapping solids.
        for v in self.ob.data.vertices:
            v.co *= 0
        bpy.data.objects.remove(self.ob, do_unlink=True)
        symmetry.reconcile()
        bpy.ops.mesh.primitive_cylinder_add(vertices=60, radius=2, depth=4)
        self.ob = bpy.context.object
        self.mod = symmetry.settings(symmetry.add(self.ob))
        for count in (2, 3, 5, 6, 12):
            for mirror in (False, True):
                p = self.radial(count, mirror_symmetry=mirror)
                coords, faces, bad = meshinfo(self.ob)
                self.assertGreater(faces, 0)
                self.assertEqual(bad, 0, (count, mirror, len(coords), faces, bad))
                rounded = [tuple(round(x, 4) for x in v) for v in coords]
                self.assertEqual(len(set(rounded)), len(rounded))
                p.weld = False
                self.assertGreater(meshinfo(self.ob)[2], 0)
                p.weld = True
            print('RADIAL PASS count=%d sliced seams manifold, weld off opens seams' % count, flush=True)

    def test_mirror_flip_and_arbitrary_segment_seams(self):
        bpy.data.objects.remove(self.ob, do_unlink=True)
        symmetry.reconcile()
        bpy.ops.mesh.primitive_cube_add(size=4)
        self.ob = bpy.context.object
        for v in self.ob.data.vertices:
            v.co.y += .4
            v.co.x += .3*v.co.y
        self.ob.data.update()
        self.mod = symmetry.settings(symmetry.add(self.ob))
        for count in (3, 5, 6, 12):
            p = self.radial(count, mirror_symmetry=True)
            p.radial_flip = False
            first, _, bad = meshinfo(self.ob)
            self.assertEqual(bad, 0)
            p.radial_flip = True
            second, _, bad = meshinfo(self.ob)
            self.assertEqual(bad, 0)
            self.assertNotEqual(sorted(tuple(round(x, 4) for x in v) for v in first),
                                sorted(tuple(round(x, 4) for x in v) for v in second))
        print('RADIAL PASS Mirror Symmetry closes arbitrary segment seams, Flip changes source half', flush=True)

    def test_collapse_and_cleanup(self):
        self.radial(6, slice=False)
        expected = meshinfo(self.ob)[:2]
        symmetry.enter(bpy.context, self.mod)
        self.assertEqual(bpy.ops.max.object_cmd(cmd='CONVERT_POLY'), {'FINISHED'})
        self.assertFalse(self.ob.modifiers)
        self.assertEqual(meshinfo(self.ob)[:2], expected)
        self.assertFalse(any(o.get(symmetry.HELPER) for o in bpy.data.objects))
        print('RADIAL PASS collapse from Mirror preserves geometry and removes dependencies', flush=True)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RadialTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
