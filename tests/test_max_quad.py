"""Run through run_checks.py --changed main tests in an isolated profile."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy
import bmesh

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import max_quad, quad_sets, operators, symmetry, modifier_ui


class QuadMenuTests(unittest.TestCase):
    def setUp(self):
        max_quad.close_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()

    def tearDown(self):
        max_quad.close_all()

    def test_modifier_set_matrix(self):
        self.assertEqual([quad_sets.choose_set(ctrl=c, alt=a, shift=s)
                          for c, a, s in ((0,0,0),(0,0,1),(1,0,0),(0,1,0),(1,1,0),
                                          (1,0,1),(0,1,1),(1,1,1))],
                         ['DEFAULT','SNAP','MODELING','ANIMATION','LIGHTING',
                          'UNASSIGNED','UNASSIGNED','UNASSIGNED'])

    def test_reference_palette_and_compact_cells(self):
        self.assertEqual(max_quad.COLORS['body'], (70/255,)*3+(1,))
        self.assertEqual(max_quad.COLORS['title'], (60/255,)*3+(1,))
        self.assertEqual(max_quad.COLORS['centre'], (60/255,130/255,220/255,1))
        self.assertEqual((max_quad.WIDTH,max_quad.ROW), (179,15))
        ctx=quad_sets.QuadContext('MESH',4,True,True,tool='SELECT')
        self.assertFalse(any(row.checked for row in quad_sets.build(ctx)[3].entries))
        self.assertFalse(any(row.checked for row in quad_sets.build(ctx,'ANIMATION')[1].entries))

    def test_mesh_authority_and_empty_selection_at_every_level(self):
        for level in range(6):
            if operators.current_level(bpy.context) != level:
                bpy.ops.max.subobject(level=level)
            for selected in (False, True):
                if level:
                    bpy.ops.mesh.select_all(action='SELECT' if selected else 'DESELECT')
                else:
                    bpy.context.active_object.select_set(selected)
                snapshot = quad_sets.capture(bpy.context)
                self.assertEqual(snapshot.level, level)
                self.assertEqual(snapshot.selected, selected)
                for name in quad_sets.SET_NAMES:
                    quads = quad_sets.build(snapshot, name)
                    self.assertEqual(len(quads), 4)
                    for q in quads:
                        for row in q.entries:
                            if row.command and row.command.operator == 'max.edit_poly':
                                self.assertFalse(row.enabled and not selected)

    def test_symmetry_uses_owner_and_has_no_mesh_operations(self):
        obj = bpy.context.object
        mod = symmetry.add(obj)
        modifier_ui.select_modifier(obj, symmetry.raw(mod))
        snapshot = quad_sets.capture(bpy.context)
        self.assertTrue(snapshot.symmetry)
        q = quad_sets.build(snapshot)
        self.assertEqual(q[0].entries[0].command.operator, 'max.symmetry_action')
        self.assertEqual(dict(q[0].entries[0].command.values)['name'], symmetry.raw(mod).name)
        self.assertFalse(q[2].entries)

    def test_stack_base_selection_overrides_native_modifier_pointer(self):
        obj=bpy.context.object
        mod=symmetry.add(obj)
        modifier_ui.select_modifier(obj, symmetry.raw(mod))
        self.assertTrue(quad_sets.capture(bpy.context).symmetry)
        obj.max_stack_index=-1
        self.assertFalse(quad_sets.capture(bpy.context).symmetry)

    def test_object_class_changes_context(self):
        for kind in ('CAMERA', 'LIGHT', 'CURVE', ''):
            q = quad_sets.build(quad_sets.QuadContext(object_class=kind))
            self.assertFalse(q[0].entries)
            self.assertFalse(q[2].entries)
        q = quad_sets.build(quad_sets.QuadContext(object_class='MESH', objects_selected=True))
        self.assertTrue(q[0].entries)
        q=quad_sets.build(quad_sets.QuadContext('MESH',0,True,True,modifier='Bend'))
        self.assertFalse(q[0].entries)
        self.assertFalse(q[2].entries)

    def test_animation_reference_image_catalogue(self):
        q = quad_sets.build(quad_sets.QuadContext('MESH', 0, True, True), 'ANIMATION')
        self.assertEqual([quad.title for quad in q], ['transform','coordinates','pose','set'])
        self.assertEqual([r.label for r in q[1].entries],
                         ['World','Working','View','Screen','Parent','Local Aligned','Local'])
        self.assertEqual([r.label for r in q[3].entries if r.label],
                         ['Set Keyframe','Show Trajectories Toggle','Delete Selected Animation',
                          'Reaction Manager...','Dope Sheet...','Curve Editor...'])
        self.assertEqual(dict(q[1].entries[5].command.values), {'reference':'LOCAL_ALIGNED'})
        self.assertFalse(q[0].entries[0].enabled)
        cells=max_quad.arrange(q)
        self.assertEqual((min(c.rect[0] for c in cells), min(c.rect[1] for c in cells),
                          max(c.rect[0]+c.rect[2] for c in cells), max(c.rect[1]+c.rect[3] for c in cells)),
                         (-154,-122,155,109))

    def test_no_object_hides_context_quadrants(self):
        q=quad_sets.build(quad_sets.QuadContext('MESH',0,False,False))
        self.assertFalse(q[0].title)
        self.assertFalse(q[2].title)

    def test_single_light_context_uses_confirmed_captions(self):
        q=quad_sets.build(quad_sets.QuadContext('LIGHT',0,True,True,object_count=1))
        self.assertEqual([r.label for r in q[0].entries],
                         ['Ambient Only','Affect Specular','Affect Diffuse','Cast Shadows','Light On'])
        self.assertFalse(any(r.enabled for r in q[0].entries))

    def test_nathan_captions_and_held_tools(self):
        q = quad_sets.build(quad_sets.QuadContext('MESH', 2, True, True), 'NATHAN')
        self.assertEqual([quad.title for quad in q], ['Selection', 'Misc', 'Modeling', 'RappaTools3'])
        self.assertEqual([row.label for row in q[0].entries][:5],
                         ['Loop', 'Ring', '', 'Shrink Selection', 'Grow Selection'])
        for title in ('RappaTools3', 'ChamferOp', 'Quick Topo UI', 'Random Fly', 'Grow Loop', 'Flow Connect'):
            row = next(row for quad in q for row in quad.entries if row.label == title)
            self.assertFalse(row.enabled)
            self.assertIsNone(row.command)

    def test_settings_are_not_immediate_operations(self):
        ctx = quad_sets.QuadContext('MESH', 4, True, True)
        rows = [row for q in quad_sets.build(ctx) for row in q.entries]
        for token in ('EXTRUDE', 'BEVEL', 'INSET'):
            row = next(row for row in rows if row.key == token)
            self.assertEqual(row.command.operator, 'max.edit_poly')
            self.assertEqual(row.settings.operator, 'max.poly_settings')
            self.assertEqual(dict(row.settings.values), {'action': token})
        row = next(row for row in rows if row.key == 'ROTATE')
        self.assertEqual(row.settings.operator, 'max.quad_typein')
        self.assertEqual(dict(row.settings.values), {'kind': 'ROTATE'})

    def test_submenu_convert_routes_and_unhide(self):
        q = quad_sets.build(quad_sets.QuadContext('MESH', 0, True, True))
        row = next(row for row in q[3].entries if row.key == 'convert')
        self.assertEqual([r.label for r in row.children],
                         ['Editable Mesh','Editable Spline','Editable Patch','Editable Poly','NURBS Surface'])
        self.assertEqual([r.enabled for r in row.children], [False,True,False,True,False])
        row = next(row for row in q[1].entries if row.label == 'Unhide by Name')
        self.assertEqual(row.command.operator, 'max.scene_selection_dialog')
        self.assertEqual(dict(row.command.values), {'hide': False})

    def test_layout_shares_joint_and_clamps_as_one_unit(self):
        cells = max_quad.arrange(quad_sets.build(quad_sets.QuadContext('MESH', 4, True, True)))
        self.assertEqual((min(c.rect[0] for c in cells), min(c.rect[1] for c in cells),
                          max(c.rect[0]+c.rect[2] for c in cells), max(c.rect[1]+c.rect[3] for c in cells)),
                         (-178, -264, 179, 216))
        for scale in (1, 1.5):
            for point in ((0,0),(1200,0),(0,1000),(1200,1000),(600,500)):
                x, y = max_quad.place(cells, point, (1200,1000), scale)
                for cell in cells:
                    xx, yy, w, h = cell.rect
                    self.assertGreaterEqual(x+xx*scale, 0)
                    self.assertLessEqual(x+(xx+w)*scale, 1200)
                    self.assertGreaterEqual(y-(yy+h)*scale, 0)
                    self.assertLessEqual(y-yy*scale, 1000)
        titles = [c for c in cells if c.title]
        self.assertEqual([(c.rect[0], c.rect[1]) for c in titles],
                         [(-178,-14),(0,-14),(-178,0),(0,0)])

    def test_text_and_settings_hit_regions(self):
        cells = max_quad.arrange(quad_sets.build(quad_sets.QuadContext('MESH', 4, True, True)))
        menu = SimpleNamespace(cells=cells, subcells=[])
        for cell in cells:
            if cell.entry and cell.entry.settings:
                x,y,w,h = cell.rect
                part = max_quad.MAX_OT_quad_menu.target(menu, x+w/2, y+h/2)
                self.assertEqual(part, (cell, 'command'))
                sx = x+7 if cell.quadrant % 2 == 0 else x+w-7
                self.assertEqual(max_quad.MAX_OT_quad_menu.target(menu, sx, y+h/2), (cell, 'settings'))
        self.assertIsNone(max_quad.MAX_OT_quad_menu.target(menu, 800, 800))

    def test_small_viewport_preserves_every_item(self):
        cells = max_quad.arrange(quad_sets.build(quad_sets.QuadContext('MESH', 2, True, True), 'NATHAN'))
        scale = max_quad.fit_scale(cells, (400, 300), 1.5)
        self.assertLess(scale, 1.5)
        x,y = max_quad.place(cells, (200,150), (400,300), scale)
        for c in cells:
            xx,yy,w,h = c.rect
            self.assertGreaterEqual(x+xx*scale, 0)
            self.assertLessEqual(x+(xx+w)*scale, 400)
            self.assertGreaterEqual(y-(yy+h)*scale, 0)
            self.assertLessEqual(y-yy*scale, 300)

    def test_install_is_idempotent_and_teardown_restores(self):
        max_quad.install()
        max_quad.install()
        self.assertEqual(bpy.app.handlers.load_pre.count(max_quad._before_load), 1)
        max_quad.uninstall()
        self.assertNotIn(max_quad._before_load, bpy.app.handlers.load_pre)
        self.assertFalse(hasattr(bpy.types, 'MAX_OT_quad_menu'))
        max_quad.install()


if __name__ == '__main__':
    result = unittest.main(argv=[__file__], exit=False)
    if not result.result.wasSuccessful():
        raise SystemExit(1)
