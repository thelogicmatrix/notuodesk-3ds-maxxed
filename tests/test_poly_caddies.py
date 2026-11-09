"""blender -b --factory-startup --python tests/test_poly_caddies.py (isolated profile)."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).parent))
from test_editable_poly_panel import mesh, QUAD, CUBE, CUBE_FACES
from notuodesk_3ds_maxxed import editable_poly as ep
from notuodesk_3ds_maxxed import poly_caddies as caddy


def geometry():
    bm = bmesh.from_edit_mesh(bpy.context.object.data)
    bm.verts.index_update()
    return (tuple((tuple(v.co), v.select, v.hide) for v in bm.verts),
            tuple((tuple(v.index for v in e.verts), e.select, e.hide) for e in bm.edges),
            tuple((tuple(v.index for v in f.verts), f.select, f.hide, f.material_index, f.smooth)
                  for f in bm.faces))


def equivalent_geometry():
    verts, edges, faces = geometry()
    def cycle(indices):
        return min(indices[i:]+indices[:i] for i in range(len(indices)))
    return (verts, sorted((tuple(sorted(e[0])), *e[1:]) for e in edges),
            sorted((cycle(f[0]), *f[1:]) for f in faces))


class CaddyTests(unittest.TestCase):
    def setUp(self):
        self.session = None

    def tearDown(self):
        if self.session:
            self.session.close(bpy.context, cancel=True)
        self.assertFalse(any(me.name.startswith('.max_caddy') for me in bpy.data.meshes))

    def start(self, action):
        self.session = caddy.Session(bpy.context, action)
        return self.session

    def test_live_redo_uses_pristine_geometry_and_persists_on_ok(self):
        mesh(QUAD, faces=[(0, 1, 2, 3)])
        session = self.start('EXTRUDE')
        for height in (.2, .7, -.4, .9):
            session.values.amount = height
            self.assertTrue(session.preview(bpy.context))
            bm = bmesh.from_edit_mesh(bpy.context.object.data)
            self.assertEqual(len(bm.faces), 5)
            self.assertAlmostEqual(sorted({round(v.co.z, 5) for v in bm.verts})[-1 if height > 0 else 0], height)
        session.close(bpy.context)
        self.assertAlmostEqual(ep.settings(bpy.context, 'EXTRUDE').amount, .9)
        self.assertEqual(bpy.ops.max.edit_poly(op='EXTRUDE'), {'FINISHED'})
        self.assertAlmostEqual(max(v.co.z for v in bmesh.from_edit_mesh(bpy.context.object.data).verts), 1.8)
        print('PASS live redo: four changes each produce one extrusion, OK settings reused by main button')

    def test_apply_continue_stacks_and_cancel_keeps_accepted_iteration(self):
        mesh(QUAD, faces=[(0, 1, 2, 3)])
        session = self.start('EXTRUDE')
        session.values.amount = .3
        self.assertTrue(session.preview(bpy.context))
        self.assertTrue(session.apply(bpy.context))
        accepted = geometry()
        self.assertTrue(session.preview(bpy.context))
        bm = bmesh.from_edit_mesh(bpy.context.object.data)
        self.assertEqual(len(bm.faces), 9)
        self.assertAlmostEqual(max(v.co.z for v in bm.verts), .6)
        session.close(bpy.context, cancel=True)
        self.assertEqual(geometry(), accepted)
        self.assertAlmostEqual(ep.settings(bpy.context, 'EXTRUDE').amount, .3)
        print('PASS Apply and Continue: preview stacks two extrusions, Cancel keeps first accepted extrusion')

    def test_cancel_exact_geometry_custom_data_selection_and_settings(self):
        ob, bm = mesh(QUAD + [(5, 5, 5)], faces=[(0, 1, 2, 3)])
        bm.verts.ensure_lookup_table()
        bm.verts[4].hide_set(True)
        uv = bm.loops.layers.uv.new('CaddyUV')
        sg = bm.faces.layers.int.new(ep.SG_ATTRIBUTE)
        for face in bm.faces:
            face[sg] = 17
            face.material_index = 2
            for i, loop in enumerate(face.loops):
                loop[uv].uv = (i / 4, i / 8)
        bmesh.update_edit_mesh(ob.data)
        before = geometry()
        old = ep.settings(bpy.context, 'EXTRUDE').amount
        session = self.start('EXTRUDE')
        session.values.amount = 1.2
        self.assertTrue(session.preview(bpy.context))
        session.close(bpy.context, cancel=True)
        self.assertEqual(before, geometry())
        bm = bmesh.from_edit_mesh(ob.data)
        self.assertEqual([f[bm.faces.layers.int[ep.SG_ATTRIBUTE]] for f in bm.faces], [17])
        self.assertEqual([tuple(l[bm.loops.layers.uv['CaddyUV']].uv) for f in bm.faces for l in f.loops],
                         [(i / 4, i / 8) for i in range(4)])
        self.assertAlmostEqual(ep.settings(bpy.context, 'EXTRUDE').amount, old)
        print('PASS Cancel: exact geometry, UVs, smoothing groups, hidden selection and settings restored')

    def test_all_requested_backends_preview_without_accumulation(self):
        expected = {'EXTRUDE', 'CHAMFER', 'CONNECT', 'BEVEL', 'INSET', 'OUTLINE',
                    'BRIDGE', 'WELD', 'TESSELLATE', 'MSMOOTH', 'RELAX'}
        self.assertEqual(caddy.ACTIONS, expected)
        for action in sorted(expected):
            with self.subTest(action=action):
                if action == 'BRIDGE':
                    verts = QUAD + [(x, y, 2) for x, y, z in QUAD]
                    edges = [(i, (i+1) % 4) for i in range(4)] + [(i+4, (i+1) % 4+4) for i in range(4)]
                    mesh(verts, edges=edges, level=3)
                elif action == 'CHAMFER':
                    mesh(CUBE, faces=CUBE_FACES, level=2)
                elif action == 'WELD':
                    mesh(QUAD + [(0.00001, 0, 0)], faces=[(0, 1, 2, 3)], level=1)
                elif action == 'RELAX':
                    mesh(CUBE, faces=CUBE_FACES, level=1)
                else:
                    mesh(QUAD, faces=[(0, 1, 2, 3)], level=2 if action == 'CONNECT' else 4)
                before = geometry()
                session = self.start(action)
                self.assertTrue(session.preview(bpy.context))
                first = equivalent_geometry()
                self.assertNotEqual(geometry(), before)
                self.assertTrue(session.preview(bpy.context))
                self.assertEqual(equivalent_geometry(), first)
                session.close(bpy.context, cancel=True)
                self.assertEqual(geometry(), before)
        print('PASS all 11 caddies: repeated previews match once, Cancel restores baseline')

    def test_object_level_relax_returns_to_object_mode(self):
        ob, bm = mesh(CUBE, faces=CUBE_FACES, level=1)
        bpy.ops.object.mode_set(mode='OBJECT')
        before = [tuple(v.co) for v in ob.data.vertices]
        session = self.start('RELAX')
        self.assertTrue(session.preview(bpy.context))
        session.close(bpy.context, cancel=True)
        self.assertEqual(bpy.context.mode, 'OBJECT')
        self.assertEqual([tuple(v.co) for v in ob.data.vertices], before)

    def test_ok_is_one_undo_step(self):
        # A real registered operator supplies the same outer UNDO boundary as the modal caddy.
        class CADDY_TEST_OT_accept(bpy.types.Operator):
            bl_idname = 'mesh.caddy_test_accept'
            bl_label = 'Caddy undo test'
            bl_options = {'UNDO'}

            def execute(self, context):
                session = caddy.Session(context, 'EXTRUDE')
                for amount in (.2, .4, .8):
                    session.values.amount = amount
                    assert session.preview(context)
                session.close(context)
                return {'FINISHED'}

        mesh(QUAD, faces=[(0, 1, 2, 3)])
        before = geometry()
        bpy.context.preferences.edit.use_global_undo = True
        bpy.utils.register_class(CADDY_TEST_OT_accept)
        try:
            bpy.ops.ed.undo_push(message='Before caddy')
            self.assertEqual(bpy.ops.mesh.caddy_test_accept('EXEC_DEFAULT', True), {'FINISHED'})
            self.assertNotEqual(geometry(), before)
            self.assertEqual(bpy.ops.ed.undo(), {'FINISHED'})
            self.assertEqual(geometry(), before)
            print('PASS OK: three live changes undone in one undo step')
        finally:
            bpy.utils.unregister_class(CADDY_TEST_OT_accept)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CaddyTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
