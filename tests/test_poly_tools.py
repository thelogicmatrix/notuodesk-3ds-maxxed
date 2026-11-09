"""Run with isolated BLENDER_USER_* dirs:
blender -b --factory-startup --python-exit-code 1 --python tests/test_poly_tools.py
"""

import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import addon_utils
import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)


def mesh_object(points, edges=(), faces=()):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    mesh = bpy.data.meshes.new("Poly tool test")
    mesh.from_pydata(points, edges, faces)
    ob = bpy.data.objects.new("Poly tool test", mesh)
    bpy.context.collection.objects.link(ob)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    return ob


def open_prism(ring, single=False):
    n = len(ring)
    points = [(x, y, 0) for x, y in ring] + [(x, y, 1) for x, y in ring]
    faces = [tuple(reversed(range(n)))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    ob = mesh_object(points, faces=faces)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, True, False)
    bm = bmesh.from_edit_mesh(ob.data)
    for f in bm.faces:
        f.select_set(False)
    for e in bm.edges:
        e.select_set(False)
    border = [e for e in bm.edges if e.is_boundary]
    for e in border[:1] if single else border:
        e.select_set(True)
    bmesh.update_edit_mesh(ob.data)
    return ob


def rect_ring(nx, ny, irregular=False):
    corners = [(0, 0), (4, 0), (4.6, 1.8), (-.3, 2.2)] if irregular else [(0, 0), (4, 0), (4, 2), (0, 2)]
    points = []
    for a, b, n in zip(corners, corners[1:] + corners[:1], (nx, ny, nx, ny)):
        for i in range(n):
            t = i / n
            points.append((a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t))
    return points


def world_vertices(ob):
    return [ob.matrix_world @ v.co for v in ob.data.vertices]


def evaluated_world_vertices(ob):
    bpy.context.view_layer.update()
    evaluated = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return [evaluated.matrix_world @ v.co for v in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()


def text_with_pivot():
    from notuodesk_3ds_maxxed import get_prefs
    get_prefs().auto_pivot_on_create = "OFF"
    bpy.ops.max.create_shape(kind="TEXT")
    ob = bpy.context.object
    ob.data.size = 2.5
    ob.data.extrude = .15
    ob.matrix_world = Matrix.Translation((5, -3, 2)) @ Matrix.Rotation(.7, 4, "Y") @ Matrix.Diagonal((2, .5, 1, 1))
    before = evaluated_world_vertices(ob)
    bpy.ops.max.pivot_bounds(mode="BOTTOM")
    return ob, before


def visible_modifiers(ob):
    from notuodesk_3ds_maxxed.ui_panel import MAX_UL_stack
    flags, _ = MAX_UL_stack.filter_items(SimpleNamespace(bitflag_filter_item=1), bpy.context, ob, "modifiers")
    return [mod for mod, flag in zip(ob.modifiers, flags) if flag & 1]


class PolyToolsTests(unittest.TestCase):
    def assert_glyphs(self, ob, before, action, reordered=False):
        after = evaluated_world_vertices(ob)
        self.assertEqual(len(before), len(after), action)
        if reordered:
            # FONT-to-CURVE regenerates the same tessellation in a different
            # vertex order. Compare both point sets in world space.
            distances = []
            for source, target in ((before, after), (after, before)):
                tree = KDTree(len(source))
                for i, point in enumerate(source):
                    tree.insert(point, i)
                tree.balance()
                distances.append(max(tree.find(point)[2] for point in target))
            displacement = max(distances)
        else:
            displacement = max((a - b).length for a, b in zip(before, after))
        self.assertLess(displacement, 1e-5, f"{action}: glyphs moved {displacement:.6f} Blender units")

    def tearDown(self):
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

    def test_quad_cap(self):
        self.assertTrue(hasattr(bpy.types, "MAX_OT_quad_cap"), "Quad Cap operator is missing")
        for nx, ny in ((1, 1), (2, 2), (4, 2), (5, 1), (4, 4)):
            for irregular in (False, True):
                ob = open_prism(rect_ring(nx, ny, irregular), single=irregular)
                self.assertEqual(bpy.ops.max.quad_cap(), {"FINISHED"})
                bm = bmesh.from_edit_mesh(ob.data)
                cap = [f for f in bm.faces if all(v.co.z > .99 for v in f.verts)]
                self.assertEqual(len(cap), nx * ny)
                self.assertTrue(all(len(f.verts) == 4 for f in cap))
                self.assertTrue(all(e.is_manifold and e.is_contiguous for e in bm.edges))
                self.assertTrue(all(f.normal.z > .99 and f.calc_area() > 1e-7 for f in cap))
                print(f"PASS Quad Cap {2 * (nx + ny)} edges irregular={irregular}: all quads, manifold, normals +Z", flush=True)

    def test_quad_cap_odd(self):
        ring = [(math.cos(i * math.tau / 5), math.sin(i * math.tau / 5)) for i in range(5)]
        ob = open_prism(ring)
        bm = bmesh.from_edit_mesh(ob.data)
        for f in bm.faces:
            f.material_index = 2
            f.smooth = True
        self.assertTrue(hasattr(bpy.types, "MAX_OT_quad_cap"), "Quad Cap operator is missing")
        self.assertEqual(bpy.ops.max.quad_cap(), {"FINISHED"})
        bm = bmesh.from_edit_mesh(ob.data)
        cap = [f for f in bm.faces if all(v.co.z > .99 for v in f.verts)]
        self.assertTrue(all(e.is_manifold and e.is_contiguous for e in bm.edges))
        self.assertTrue(any(len(f.verts) == 3 for f in cap))
        self.assertTrue(all(len(f.verts) in (3, 4) and f.normal.z > .99 for f in cap))
        self.assertTrue(all(f.material_index == 2 and f.smooth for f in cap))
        print("PASS Quad Cap odd: warning path closes hole with triangles/quads, manifold, normals +Z", flush=True)

    def test_quad_cap_round_and_multiple(self):
        for n in (4, 8, 12, 16):
            ring = [(2 * math.cos(i * math.tau / n), math.sin(i * math.tau / n)) for i in range(n)]
            ob = open_prism(ring)
            self.assertEqual(bpy.ops.max.quad_cap(), {"FINISHED"})
            bm = bmesh.from_edit_mesh(ob.data)
            cap = [f for f in bm.faces if all(v.co.z > .99 for v in f.verts)]
            self.assertTrue(all(len(f.verts) == 4 and f.normal.z > .99 for f in cap))
            self.assertTrue(all(e.is_manifold and e.is_contiguous for e in bm.edges))
        ob = open_prism(rect_ring(2, 2))
        bm = bmesh.from_edit_mesh(ob.data)
        original = list(bm.verts) + list(bm.edges) + list(bm.faces)
        copied = bmesh.ops.duplicate(bm, geom=original)["geom"]
        bmesh.ops.translate(bm, verts=[v for v in copied if isinstance(v, bmesh.types.BMVert)], vec=(9, 0, 0))
        for e in bm.edges:
            e.select_set(e.is_boundary)
        bmesh.update_edit_mesh(ob.data)
        self.assertEqual(bpy.ops.max.quad_cap(), {"FINISHED"})
        self.assertTrue(all(e.is_manifold and e.is_contiguous for e in bm.edges))
        print("PASS Quad Cap: elliptical 4/8/12/16 borders and two holes in one mesh", flush=True)

    def test_regularizer(self):
        self.assertTrue(hasattr(bpy.types, "MAX_OT_loop_regularize"), "Loop Regularizer operator is missing")
        points, edges = [], []
        for cx in (0, 7):
            start = len(points)
            points += [(cx + (2 + .2 * math.sin(i)) * math.cos(a), (2 + .2 * math.sin(i)) * math.sin(a), 0)
                       for i, a in enumerate((0, .4, 1.1, 2, 2.8, 3.4, 4.5, 5.5))]
            edges += [(start + i, start + (i + 1) % 8) for i in range(8)]
        ob = mesh_object(points, edges)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        self.assertEqual(bpy.ops.max.loop_regularize(), {"FINISHED"})
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        for start in (0, 8):
            coords = [bm.verts[i].co for i in range(start, start + 8)]
            center = sum(coords, Vector()) / 8
            radii = [(p - center).length for p in coords]
            lengths = [(coords[i] - coords[(i + 1) % 8]).length for i in range(8)]
            self.assertLess(max(radii) - min(radii), 1e-5)
            self.assertLess(max(lengths) - min(lengths), 1e-5)
        print("PASS Loop Regularizer default Circle: two loops, equal chord spacing and radius within 1e-5", flush=True)
        ob = mesh_object([(0, 0, 0), (.1, 0, 0), (2, 0, 0), (4, 0, 0)], [(0, 1), (1, 2), (2, 3)])
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        self.assertEqual(bpy.ops.max.loop_regularize(mode="SPACE"), {"FINISHED"})
        bm = bmesh.from_edit_mesh(ob.data)
        lengths = [e.calc_length() for e in bm.edges]
        self.assertLess(max(lengths) - min(lengths), 1e-5)
        print("PASS Loop Regularizer open Even Spacing: equal edge lengths within 1e-5, endpoints fixed", flush=True)

    def test_regularizer_open_circle_and_branches(self):
        angles = (0, .2, .9, 1.7, 2.5)
        points = [(3 + 2 * math.cos(a), -1 + 2 * math.sin(a), 0) for a in angles]
        ob = mesh_object(points, [(i, i + 1) for i in range(4)])
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        self.assertEqual(bpy.ops.max.loop_regularize(), {"FINISHED"})
        bm = bmesh.from_edit_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        for v in bm.verts:
            self.assertAlmostEqual((v.co - Vector((3, -1, 0))).length, 2, places=5)
        lengths = [e.calc_length() for e in bm.edges]
        self.assertLess(max(lengths) - min(lengths), 1e-5)
        self.assertLess((bm.verts[0].co - Vector(points[0])).length, 1e-5)
        self.assertLess((bm.verts[4].co - Vector(points[4])).length, 1e-5)
        ob = mesh_object([(0, 0, 0), (1, 0, 0), (0, 1, 0), (-1, 0, 0)], [(0, 1), (0, 2), (0, 3)])
        before = [v.co.copy() for v in ob.data.vertices]
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        self.assertEqual(bpy.ops.max.loop_regularize(), {"CANCELLED"})
        self.assertTrue(all((a - v.co).length < 1e-8 for a, v in zip(before, bmesh.from_edit_mesh(ob.data).verts)))
        print("PASS Loop Regularizer: open circular arc, endpoints and radius preserved, branches cancel unchanged", flush=True)

    def test_regularizer_world_scale(self):
        ob = mesh_object([(math.cos(i), math.sin(i), 0) for i in range(6)], [(i, (i + 1) % 6) for i in range(6)])
        ob.matrix_world = Matrix.Rotation(.8, 4, "X") @ Matrix.Diagonal((3, 1, 2, 1))
        bpy.context.view_layer.update()
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        self.assertEqual(bpy.ops.max.loop_regularize(), {"FINISHED"})
        coords = [ob.matrix_world @ v.co for v in bmesh.from_edit_mesh(ob.data).verts]
        center = sum(coords, Vector()) / len(coords)
        radii = [(v - center).length for v in coords]
        lengths = [(coords[i] - coords[(i + 1) % 6]).length for i in range(6)]
        self.assertLess(max(radii) - min(radii), 1e-5)
        self.assertLess(max(lengths) - min(lengths), 1e-5)
        print("PASS Loop Regularizer: equal world-space radius and spacing on rotated non-uniformly scaled object", flush=True)

    def test_auto_pivot(self):
        from notuodesk_3ds_maxxed import get_prefs, prims
        prefs = get_prefs()
        self.assertTrue(hasattr(prefs, "auto_pivot_on_create"), "Auto Pivot preference is missing")
        from notuodesk_3ds_maxxed import poly_tools
        self.assertEqual(prefs.auto_pivot_on_create, "OFF")
        for mode in ("BOTTOM", "CENTER"):
            prefs.auto_pivot_on_create = mode
            ob = mesh_object([])
            ob.location = (5, -3, 2)
            prims.set_params(ob, "BOX", width=4, length=2, height=6)
            bpy.context.view_layer.update()
            before = world_vertices(ob)
            poly_tools.finalize_new_object(bpy.context, ob)
            bpy.context.view_layer.update()
            expected = Vector((5, -3, 2 if mode == "BOTTOM" else 5))
            self.assertLess((ob.matrix_world.translation - expected).length, 1e-5)
            self.assertTrue(all((a - b).length < 1e-5 for a, b in zip(before, world_vertices(ob))))
            prims.rebuild(ob)
            self.assertTrue(all((a - b).length < 1e-5 for a, b in zip(before, world_vertices(ob))))
            ob.max_prim.width = 8
            self.assertAlmostEqual(max(v.x for v in world_vertices(ob)) - min(v.x for v in world_vertices(ob)), 8)
            self.assertLess((ob.matrix_world.translation - expected).length, 1e-5)
            print(f"PASS AutoPivot {mode}: correct origin, geometry unchanged, rebuild and parameter edit preserve offset", flush=True)
        prefs.auto_pivot_on_create = "OFF"

    def test_manual_pivot_and_shapes(self):
        from notuodesk_3ds_maxxed import get_prefs, prims
        ob = mesh_object([])
        prims.set_params(ob, "BOX", width=4, length=2, height=-6)
        ob.matrix_world = Matrix.Translation((5, -3, 2)) @ Matrix.Rotation(.7, 4, "Y") @ Matrix.Diagonal((2, 1, .5, 1))
        sibling = bpy.data.objects.new("Shared mesh sibling", ob.data)
        bpy.context.collection.objects.link(sibling)
        child = bpy.data.objects.new("Pivot child", None)
        bpy.context.collection.objects.link(child)
        child.parent = ob
        child.location = (1, 2, 3)
        bpy.context.view_layer.update()
        child_matrix = child.matrix_world.copy()
        before = world_vertices(ob)
        original_mesh = sibling.data
        expected = Vector([(min(v[i] for v in before) + max(v[i] for v in before)) / 2 for i in range(3)])
        expected.z = min(v.z for v in before)
        self.assertEqual(bpy.ops.max.pivot_bounds(mode="BOTTOM"), {"FINISHED"})
        bpy.context.view_layer.update()
        self.assertLess((ob.matrix_world.translation - expected).length, 1e-5)
        self.assertTrue(all((a - b).length < 1e-5 for a, b in zip(before, world_vertices(ob))))
        self.assertIsNot(ob.data, original_mesh)
        self.assertIs(sibling.data, original_mesh)
        self.assertTrue(all(abs(child.matrix_world[i][j] - child_matrix[i][j]) < 1e-5 for i in range(4) for j in range(4)))
        prims.rebuild(ob)
        self.assertTrue(all((a - b).length < 1e-5 for a, b in zip(before, world_vertices(ob))))
        prefs = get_prefs()
        prefs.auto_pivot_on_create = "BOTTOM"
        bpy.context.scene.cursor.location = (8, 2, 3)
        self.assertEqual(bpy.ops.max.create_shape(kind="HELIX"), {"FINISHED"})
        shape = bpy.context.object
        evaluated = shape.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        coords = [shape.matrix_world @ v.co for v in mesh.vertices]
        evaluated.to_mesh_clear()
        self.assertAlmostEqual(shape.matrix_world.translation.z, min(p.z for p in coords), places=5)
        prefs.auto_pivot_on_create = "OFF"
        print("PASS Pivot controls: rotated/scaled negative-height box, child and shared mesh preserved, spline creation hook", flush=True)

    def test_text_pivot_preserves_evaluated_glyphs(self):
        from notuodesk_3ds_maxxed import get_prefs
        get_prefs().auto_pivot_on_create = "OFF"
        for mode in ("CENTER", "BOTTOM"):
            for size in (1, 2.5):
                with self.subTest(mode=mode, size=size):
                    self.assertEqual(bpy.ops.max.create_shape(kind="TEXT"), {"FINISHED"})
                    ob = bpy.context.object
                    self.assertEqual(ob.data.body, "MAX Text")
                    ob.data.size = size
                    ob.data.extrude = .15
                    ob.data.offset_x = .3
                    ob.data.offset_y = -.2
                    ob.matrix_world = Matrix.Translation((5, -3, 2)) @ Matrix.Rotation(.7, 4, "Y") @ Matrix.Diagonal((2, .5, 1, 1))
                    before = evaluated_world_vertices(ob)
                    expected = Vector([(min(p[i] for p in before) + max(p[i] for p in before)) / 2 for i in range(3)])
                    if mode == "BOTTOM":
                        expected.z = min(p.z for p in before)
                    for _ in range(2):
                        self.assertEqual(bpy.ops.max.pivot_bounds(mode=mode), {"FINISHED"})
                        after = evaluated_world_vertices(ob)
                        self.assertEqual(len(before), len(after))
                        displacement = max((a - b).length for a, b in zip(before, after))
                        self.assertLess(displacement, 1e-5, f"Text glyphs moved {displacement:.6f} Blender units")
                        self.assertLess((ob.matrix_world.translation - expected).length, 1e-5)
                    self.assertEqual(ob.type, "FONT")
                    self.assertEqual(ob.data.body, "MAX Text")
                    print(f"PASS Text pivot {mode} size={size}: evaluated glyphs unchanged, tilted/extruded/scaled, repeated calls", flush=True)

    def test_creation_finalizer_and_text_autopivot(self):
        from notuodesk_3ds_maxxed import get_prefs, poly_tools
        prefs = get_prefs()
        try:
            for mode in ("OFF", "CENTER", "BOTTOM"):
                prefs.auto_pivot_on_create = "OFF"
                self.assertEqual(bpy.ops.max.create_shape(kind="TEXT"), {"FINISHED"})
                baseline = bpy.context.object
                before = evaluated_world_vertices(baseline)
                original_origin = baseline.matrix_world.translation.copy()
                expected = Vector([(min(p[i] for p in before) + max(p[i] for p in before)) / 2 for i in range(3)])
                if mode == "BOTTOM":
                    expected.z = min(p.z for p in before)
                if mode == "OFF":
                    expected = original_origin
                prefs.auto_pivot_on_create = mode
                poly_tools.finalize_new_object(bpy.context, baseline)
                after = evaluated_world_vertices(baseline)
                self.assertLess((baseline.matrix_world.translation - expected).length, 1e-5)
                self.assertEqual(len(before), len(after))
                self.assertTrue(all((a - b).length < 1e-5 for a, b in zip(before, after)))
                self.assertEqual(bpy.ops.max.create_shape(kind="TEXT"), {"FINISHED"})
                created = bpy.context.object
                after = evaluated_world_vertices(created)
                self.assertLess((created.matrix_world.translation - expected).length, 1e-5)
                self.assertEqual(len(before), len(after))
                self.assertTrue(all((a - b).length < 1e-5 for a, b in zip(before, after)))
        finally:
            prefs.auto_pivot_on_create = "OFF"
        print("PASS creation finalizer and Shapes Text: Off/Center/Bottom preserve evaluated glyphs and set expected origins", flush=True)

    def test_text_pivot_stack_cannot_disable_or_remove_compensation(self):
        from notuodesk_3ds_maxxed import ui_panel
        ob, before = text_with_pivot()
        self.assert_glyphs(ob, before, "Pivot to Bottom")
        # Every exposed row offers a viewport bulb and Remove Modifier.
        for mod in visible_modifiers(ob):
            mod.show_viewport = False
            self.assert_glyphs(ob, before, "Modify stack disable " + mod.name)
            mod.show_viewport = True
            bpy.ops.object.modifier_remove(modifier=mod.name)
            self.assert_glyphs(ob, before, "Modify stack Remove Modifier")
        for mod in ob.modifiers:
            ob.modifiers.active = mod
            self.assertEqual(ui_panel._stack_get(ob), -1)
            ob.max_stack_index = ob.modifiers.find(mod.name)
            self.assertEqual(ui_panel._stack_get(ob), -1)
            self.assertEqual(bpy.ops.max.modifier_set_active(name=mod.name), {"CANCELLED"})
            self.assertEqual(bpy.ops.max.stack_move(modifier=mod.name, direction="DOWN"), {"CANCELLED"})
        self.assertEqual(visible_modifiers(ob), [])
        print("PASS Text pivot: no compensation row, bulb, selection or Remove Modifier in Max stack", flush=True)

    def test_text_pivot_other_stack_actions(self):
        from notuodesk_3ds_maxxed.gn_mods import G
        ob, before = text_with_pivot()
        for name in ("Other A", "Other B"):
            g = G(name)
            g.out(g.g("Geometry"))
            mod = ob.modifiers.new(name, "NODES")
            mod.node_group = g.ng
        self.assertEqual([m.name for m in visible_modifiers(ob)], ["Other A", "Other B"])
        for name in ("Other A", "Other B"):
            bpy.ops.max.modifier_set_active(name=name)
            mod = ob.modifiers[name]
            for prop in ("show_viewport", "show_in_editmode", "show_on_cage"):
                setattr(mod, prop, not getattr(mod, prop))
                self.assert_glyphs(ob, before, prop)
                setattr(mod, prop, not getattr(mod, prop))
            for direction in ("UP", "UP", "DOWN", "DOWN"):
                self.assertEqual(bpy.ops.max.stack_move(modifier=name, direction=direction), {"FINISHED"})
                self.assert_glyphs(ob, before, "Reorder " + direction)
                self.assertNotIn(ob.modifiers[0], visible_modifiers(ob))
        self.assertEqual(bpy.ops.object.make_single_user(object=True), {"FINISHED"})
        ob = bpy.context.object
        self.assert_glyphs(ob, before, "Make Unique")
        # Blender cannot apply individual modifiers to FONT objects. The offered
        # action must reject without disturbing the pivot or glyphs.
        with self.assertRaisesRegex(RuntimeError, "Cannot apply modifier for this object type"):
            bpy.ops.object.modifier_apply(modifier="Other A")
        self.assert_glyphs(ob, before, "Apply other modifier rejected")
        for name in ("Other A", "Other B"):
            self.assertEqual(bpy.ops.object.modifier_remove(modifier=name), {"FINISHED"})
            self.assert_glyphs(ob, before, "Remove Modifier " + name)
        self.assertEqual(visible_modifiers(ob), [])
        self.assertEqual(ob.type, "FONT")
        ob.data.body = "Still editable"
        self.assertGreater(len(evaluated_world_vertices(ob)), 0)
        # Creating the compensation after user modifiers must still put it first.
        bpy.ops.max.create_shape(kind="TEXT")
        ob = bpy.context.object
        g = G("Existing user modifier")
        g.out(g.g("Geometry"))
        mod = ob.modifiers.new("Existing user modifier", "NODES")
        mod.node_group = g.ng
        before = evaluated_world_vertices(ob)
        bpy.ops.max.pivot_bounds(mode="CENTER")
        self.assert_glyphs(ob, before, "Pivot with existing modifier")
        self.assertNotIn(ob.modifiers[0], visible_modifiers(ob))
        print("PASS Text pivot: other modifier bulbs, edit/cage, reorder boundaries, Make Unique, apply rejection and removal preserve glyphs", flush=True)

    def test_text_pivot_baked_on_conversion(self):
        from notuodesk_3ds_maxxed.gn_mods import G
        for cmd, expected_type in (("CONVERT_SPLINE", "CURVE"), ("CONVERT_POLY", "MESH")):
            ob, before = text_with_pivot()
            g = G("Conversion user modifier")
            g.out(g.g("Geometry"))
            mod = ob.modifiers.new("Conversion user modifier", "NODES")
            mod.node_group = g.ng
            origin = ob.matrix_world.translation.copy()
            self.assertEqual(bpy.ops.max.object_cmd(cmd=cmd), {"FINISHED"})
            self.assertEqual(ob.type, expected_type)
            self.assertLess((ob.matrix_world.translation - origin).length, 1e-5)
            self.assert_glyphs(ob, before, cmd, reordered=True)
            for mod in list(ob.modifiers):
                bpy.ops.object.modifier_remove(modifier=mod.name)
            self.assert_glyphs(ob, before, cmd + " after removing all modifiers", reordered=True)
        print("PASS Text pivot: Editable Spline and Editable Poly bake compensation, all modifiers removable", flush=True)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PolyToolsTests)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("Poly tools tests failed")
