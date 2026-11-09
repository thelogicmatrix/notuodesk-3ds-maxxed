"""Run in the isolated profile: blender -b --factory-startup --python tests/test_loft.py."""

import os
import sys
import tempfile
import unittest

import addon_utils
import bpy
from mathutils import Vector

addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
from notuodesk_3ds_maxxed import loft


def curve(name, coords, cyclic=False):
    data = bpy.data.curves.new(name, 'CURVE')
    data.dimensions = '3D'
    spline = data.splines.new('POLY')
    spline.points.add(len(coords) - 1)
    for point, co in zip(spline.points, coords):
        point.co = (*co, 1)
    spline.use_cyclic_u = cyclic
    ob = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(ob)
    return ob


def mesh_snapshot(ob, depsgraph):
    result = ob.evaluated_get(depsgraph)
    mesh = result.to_mesh()
    verts = [tuple(v.co) for v in mesh.vertices]
    faces = [(tuple(p.vertices), p.use_smooth, tuple(p.normal)) for p in mesh.polygons]
    result.to_mesh_clear()
    return verts, faces


def evaluated(ob):
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return mesh_snapshot(ob, depsgraph)


class LoftTestRenderEngine(bpy.types.RenderEngine):
    """Inspect Blender's real render depsgraph without a GPU or image sampling."""
    bl_idname = 'LOFT_TEST'
    bl_label = 'Loft test'
    snapshots = {}
    mode = None

    def render(self, depsgraph):
        type(self).mode = depsgraph.mode
        type(self).snapshots = {ob.name: mesh_snapshot(ob, depsgraph)
                                for ob in depsgraph.scene.objects if ob.type in {'CURVE', 'MESH'}}
        self.end_result(self.begin_result(0, 0, 1, 1))


def rendered():
    scene = bpy.context.scene
    previous = scene.render.engine
    bpy.utils.register_class(LoftTestRenderEngine)
    try:
        scene.render.engine = 'LOFT_TEST'
        LoftTestRenderEngine.snapshots = {}
        bpy.ops.render.render()
        assert LoftTestRenderEngine.mode == 'RENDER'
        return LoftTestRenderEngine.snapshots
    finally:
        scene.render.engine = previous
        bpy.utils.unregister_class(LoftTestRenderEngine)


def rendering_modifier(ob, viewport, renderer):
    """Line's Is Viewport switch and Curve to Mesh, independent of its branch."""
    group = bpy.data.node_groups.new('Spline Rendering fixture', 'GeometryNodeTree')
    group['max_spline_render'] = True
    group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    nodes, links = group.nodes, group.links
    source = nodes.new('NodeGroupInput')
    out = nodes.new('NodeGroupOutput')
    circle = nodes.new('GeometryNodeCurvePrimitiveCircle')
    circle.inputs['Radius'].default_value = .25
    skin = nodes.new('GeometryNodeCurveToMesh')
    links.new(source.outputs['Geometry'], skin.inputs['Curve'])
    links.new(circle.outputs['Curve'], skin.inputs['Profile Curve'])
    skin.inputs['Fill Caps'].default_value = True
    enabled = nodes.new('GeometryNodeSwitch')
    enabled.input_type = 'BOOLEAN'
    enabled.inputs['False'].default_value = renderer
    enabled.inputs['True'].default_value = viewport
    links.new(nodes.new('GeometryNodeIsViewport').outputs[0], enabled.inputs['Switch'])
    geometry = nodes.new('GeometryNodeSwitch')
    geometry.input_type = 'GEOMETRY'
    links.new(enabled.outputs[0], geometry.inputs['Switch'])
    links.new(source.outputs['Geometry'], geometry.inputs['False'])
    links.new(skin.outputs['Mesh'], geometry.inputs['True'])
    links.new(geometry.outputs[0], out.inputs['Geometry'])
    mod = ob.modifiers.new('Rendering', 'NODES')
    mod.node_group = group
    return mod


class LoftTests(unittest.TestCase):
    def setUp(self):
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        self.path = curve('Path', [(0, 0, 0), (0, 0, 5)])
        self.shape = curve('Shape', [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], True)

    def make(self, **kwargs):
        ob = loft.make_loft(bpy.context, self.path, self.shape, **kwargs)
        ob.max_loft.shape_steps = 0
        ob.max_loft.path_steps = 0
        ob.max_loft.adaptive = False
        return ob

    def test_steps_and_independent_caps(self):
        ob = self.make()
        verts, faces = evaluated(ob)
        self.assertEqual((len(verts), len(faces)), (8, 6))
        def cap_levels():
            verts, faces = evaluated(ob)
            return sorted({verts[f[0][0]][2] for f in faces
                           if len({verts[i][2] for i in f[0]}) == 1})
        self.assertEqual(cap_levels(), [0, 5])
        print('LOFT base: 8 vertices, 6 faces (4 sides, 2 caps)', flush=True)
        ob.max_loft.cap_start = False
        self.assertEqual(len(evaluated(ob)[1]), 5)
        self.assertEqual(cap_levels(), [5])
        ob.max_loft.cap_end = False
        self.assertEqual(len(evaluated(ob)[1]), 4)
        self.assertEqual(cap_levels(), [])
        ob.max_loft.cap_start = True
        self.assertEqual(len(evaluated(ob)[1]), 5)
        self.assertEqual(cap_levels(), [0])
        print('LOFT caps: start and end toggle independently, faces 6 -> 5 -> 4 -> 5', flush=True)
        ob.max_loft.cap_start = ob.max_loft.cap_end = False
        ob.max_loft.shape_steps = 1
        self.assertEqual(len(evaluated(ob)[0]), 16)
        ob.max_loft.path_steps = 2
        verts, faces = evaluated(ob)
        self.assertEqual((len(verts), len(faces)), (32, 24))
        print('LOFT steps: Shape Steps 1, Path Steps 2 = 32 vertices, 24 side faces', flush=True)

    def test_instance_edits_update_mesh(self):
        ob = self.make()
        self.path.data.splines[0].points[1].co.z = 9
        self.path.data.update_tag()
        self.assertAlmostEqual(max(v[2] for v in evaluated(ob)[0]), 9)
        self.shape.data.splines[0].points[1].co.x = 3
        self.shape.data.update_tag()
        self.assertAlmostEqual(max(v[0] for v in evaluated(ob)[0]), 3)
        print('LOFT live Instance: path endpoint z=9 and profile x=3 reach evaluated mesh', flush=True)

    def test_rendered_sources_keep_raw_spline_in_viewport_and_render(self):
        bpy.ops.object.camera_add(location=(10, -10, 10))
        bpy.context.scene.camera = bpy.context.object
        ob = self.make()
        baseline = evaluated(ob)
        self.assertEqual((len(baseline[0]), len(baseline[1])), (8, 6))
        for role in ('path', 'shape'):
            source = getattr(self, role)
            for kind in ('bevel', 'extrude', 'viewport', 'renderer', 'both'):
                with self.subTest(role=role, rendering=kind):
                    print(f'LOFT rendering check: {role} {kind}', flush=True)
                    mod = None
                    if kind == 'bevel':
                        source.data.bevel_depth = .25
                    elif kind == 'extrude':
                        source.data.extrude = .25
                    else:
                        mod = rendering_modifier(source, kind != 'renderer', kind != 'viewport')
                    try:
                        viewport_mesh = evaluated(ob)
                        viewport_source = evaluated(source)
                        render_meshes = rendered()
                        # Prove the fixture really converts the source in the intended evaluation.
                        self.assertEqual(bool(viewport_source[1]), kind != 'renderer')
                        self.assertEqual(bool(render_meshes[source.name][1]), kind != 'viewport')
                        self.assertEqual(viewport_mesh, baseline)
                        self.assertEqual(render_meshes[ob.name], baseline)
                    finally:
                        source.data.bevel_depth = source.data.extrude = 0
                        if mod:
                            source.modifiers.remove(mod)
        print('LOFT rendering: path and shape bevel, extrude and Line-style viewport/render switches preserve 8 vertices, 6 faces', flush=True)

    def test_rendered_sources_stay_live_in_edit_mode(self):
        self.shape.data.bevel_depth = .2
        rendering_modifier(self.path, True, True)
        ob = self.make()
        self.assertEqual((len(evaluated(ob)[0]), len(evaluated(ob)[1])), (8, 6))
        bpy.ops.object.select_all(action='DESELECT')
        self.path.select_set(True)
        bpy.context.view_layer.objects.active = self.path
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            bpy.ops.curve.select_all(action='SELECT')
            bpy.ops.transform.translate(value=(0, 0, 2))
            verts = evaluated(ob)[0]
            self.assertAlmostEqual(min(v[2] for v in verts), 2)
            self.assertAlmostEqual(max(v[2] for v in verts), 7)
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.curve.primitive_bezier_circle_add(radius=1)
        circle = bpy.context.object
        circle.data.bevel_depth = .3
        ob.max_loft.shape = circle
        ob.max_loft.shape_steps = 1
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            bpy.ops.curve.select_all(action='SELECT')
            bpy.ops.transform.resize(value=(2, 2, 2))
            bpy.ops.curve.subdivide(number_cuts=1)
            verts, faces = evaluated(ob)
            self.assertEqual((len(verts), len(faces)), (32, 18))
            self.assertAlmostEqual(max(v[0] for v in verts), 2, places=5)
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        self.assertAlmostEqual(self.shape.data.bevel_depth, .2)
        self.assertAlmostEqual(circle.data.bevel_depth, .3)
        self.assertEqual(len(self.path.modifiers), 1)
        print('LOFT rendered live edits: Edit Mode path movement, Bezier scaling/subdivision and Get Shape replacement update without changing source rendering', flush=True)

    def test_internal_curves_follow_loft_lifecycle(self):
        ob = self.make()
        original_curves = (ob.max_loft.path_curve.name, ob.max_loft.shape_curve.name)
        duplicate = ob.copy()
        bpy.context.collection.objects.link(duplicate)
        self.assertEqual(evaluated(duplicate), evaluated(ob))
        self.assertNotEqual(duplicate.max_loft.path_curve, ob.max_loft.path_curve)
        self.assertNotEqual(duplicate.max_loft.shape_curve, ob.max_loft.shape_curve)
        bpy.data.objects.remove(ob, do_unlink=True)
        self.assertEqual((len(evaluated(duplicate)[0]), len(evaluated(duplicate)[1])), (8, 6))
        self.assertTrue(all(name not in bpy.data.objects for name in original_curves))
        print('LOFT internal curves: duplicate owns independent helpers, deleting a Loft removes its helpers', flush=True)

    def test_copy_and_move(self):
        copied = self.make(mode='COPY')
        self.assertIsNot(copied.max_loft.path.data, self.path.data)
        self.assertIsNot(copied.max_loft.shape.data, self.shape.data)
        self.path.data.splines[0].points[1].co.z = 12
        self.path.data.update_tag()
        self.assertAlmostEqual(max(v[2] for v in evaluated(copied)[0]), 5)
        moved = self.make(mode='MOVE')
        self.assertTrue(self.path.hide_get())
        self.assertTrue(self.shape.hide_get())
        self.assertTrue(self.path.hide_render and self.shape.hide_render)
        self.assertGreater(len(evaluated(moved)[0]), 0)
        print('LOFT source modes: Copy isolates data, Move hides sources and keeps live geometry', flush=True)

    def test_smooth_flip_scale_twist(self):
        ob = self.make()
        self.assertTrue(all(p[1] for p in evaluated(ob)[1]))
        ob.max_loft.smooth_length = ob.max_loft.smooth_width = False
        self.assertFalse(any(p[1] for p in evaluated(ob)[1]))
        before = evaluated(ob)[1][0][2]
        ob.max_loft.flip_normals = True
        after = evaluated(ob)[1][0][2]
        self.assertLess(sum(a * b for a, b in zip(before, after)), -.99)
        ob.max_loft.scale_end = 200
        self.assertAlmostEqual(max(abs(v[0]) for v in evaluated(ob)[0]), 2)
        ob.max_loft.twist = 45
        self.assertGreater(max(abs(v[0]) for v in evaluated(ob)[0]), 2.8)
        print('LOFT surface: smooth toggles, flipped normals, 200% end scale and 45 degree twist verified', flush=True)

    def test_invalid_sources_leave_scene_unchanged(self):
        mesh = bpy.data.objects.new('Mesh', bpy.data.meshes.new('Mesh'))
        bpy.context.collection.objects.link(mesh)
        count = len(bpy.data.objects)
        for path, shape in ((mesh, self.shape), (self.path, self.path)):
            with self.assertRaises(ValueError):
                loft.make_loft(bpy.context, path, shape)
        self.assertEqual(len(bpy.data.objects), count)
        print('LOFT validation: non-spline and self-reference rejected without scene changes', flush=True)

    def test_adaptive_shape_level_and_contour(self):
        ob = self.make()
        p = ob.max_loft
        p.path_percent = 30
        bpy.context.view_layer.objects.active = ob
        self.shape.select_set(True)
        self.assertEqual(bpy.ops.max.loft_pick(source='SHAPE', object_name=self.shape.name), {'FINISHED'})
        self.assertEqual(p.shape_level, 30)
        p.adaptive = True
        verts, faces = evaluated(ob)
        self.assertEqual((len(verts), len(faces)), (12, 10))
        self.assertTrue(any(abs(v[2] - 1.5) < 1e-5 for v in verts))
        p.path_steps = 1
        p.path_percent = 50
        bpy.ops.max.loft_pick(source='SHAPE', object_name=self.shape.name)
        self.assertEqual(len(evaluated(ob)[0]), 12)
        print('LOFT adaptive: Get Shape at 30% adds ring z=1.5, 50% reuses an existing ring', flush=True)
        bend = curve('Bend', [(0, 0, 0), (0, 0, 3), (3, 0, 3)])
        bpy.ops.max.loft_pick(source='PATH', object_name=bend.name)
        p.adaptive = False
        p.path_steps = 0
        on = evaluated(ob)[0]
        p.contour = False
        off = evaluated(ob)[0]
        self.assertNotEqual(on, off)
        # Parallel end section remains in its original XY plane.
        self.assertAlmostEqual(max(v[2] for v in off), 3)
        self.assertGreater(max(v[2] for v in on), 3.5)
        print('LOFT contour: on follows bend, off keeps sections parallel to the start', flush=True)

    def test_bezier_closed_path_and_open_profile(self):
        bpy.ops.curve.primitive_bezier_circle_add(radius=1)
        circle = bpy.context.active_object
        ob = loft.make_loft(bpy.context, self.path, circle)
        ob.max_loft.path_steps = 0
        ob.max_loft.shape_steps = 1
        self.assertEqual((len(evaluated(ob)[0]), len(evaluated(ob)[1])), (16, 10))
        closed = curve('ClosedPath', [(0, 0, 0), (0, 0, 5), (5, 0, 5), (5, 0, 0)], True)
        loop = loft.make_loft(bpy.context, closed, self.shape)
        loop.max_loft.path_steps = loop.max_loft.shape_steps = 0
        loop.max_loft.shape_level = 30
        verts, faces = evaluated(loop)
        self.assertEqual((len(verts), len(faces)), (20, 20))
        loop.max_loft.cap_start = loop.max_loft.cap_end = False
        self.assertEqual(len(evaluated(loop)[1]), 20)
        open_shape = curve('OpenShape', [(-1, 0, 0), (0, 1, 0), (1, 0, 0)])
        sheet = loft.make_loft(bpy.context, self.path, open_shape)
        sheet.max_loft.path_steps = sheet.max_loft.shape_steps = 0
        self.assertEqual((len(evaluated(sheet)[0]), len(evaluated(sheet)[1])), (6, 2))
        print('LOFT spline types: Bezier profile, cyclic path, open profile verified', flush=True)

    def test_get_path_anchor_and_banking(self):
        self.shape.location = (8, 4, 2)
        self.path.location = (-10, 0, 0)
        ob = loft.make_loft(bpy.context, self.path, self.shape, anchor='SHAPE')
        ob.max_loft.path_steps = ob.max_loft.shape_steps = 0
        world = [ob.matrix_world @ Vector(v) for v in evaluated(ob)[0]]
        self.assertAlmostEqual(min(v.z for v in world), 2)
        self.assertAlmostEqual(max(v.z for v in world), 7)
        self.assertAlmostEqual(min(v.x for v in world), 7)
        self.assertAlmostEqual(max(v.x for v in world), 9)
        spatial = curve('SpatialPath', [(0, 0, 0), (1, 0, 1), (2, 2, 3), (3, 3, 2)])
        bank = loft.make_loft(bpy.context, spatial, self.shape)
        bank.max_loft.shape_steps = 0
        bank.max_loft.path_steps = 1
        on = evaluated(bank)[0]
        bank.max_loft.banking = False
        off = evaluated(bank)[0]
        self.assertNotEqual(on, off)
        print('LOFT Get Path: anchored at selected shape, Banking changes the 3D frame', flush=True)

    def test_source_scales_are_applied_once(self):
        self.path.scale = (2, 2, 2)
        self.shape.scale = (3, 3, 3)
        ob = self.make()
        world = [ob.matrix_world @ Vector(v) for v in evaluated(ob)[0]]
        self.assertAlmostEqual(max(v.z for v in world), 10)
        self.assertAlmostEqual(max(v.x for v in world), 3)
        other = loft.make_loft(bpy.context, self.path, self.shape, anchor='SHAPE')
        other.max_loft.path_steps = other.max_loft.shape_steps = 0
        world = [other.matrix_world @ Vector(v) for v in evaluated(other)[0]]
        self.assertAlmostEqual(max(v.x for v in world), 3, places=5)
        self.assertAlmostEqual(max(v.z for v in world), 10, places=5)
        self.path.scale.z = 3
        self.assertAlmostEqual(max(v[2] for v in evaluated(other)[0]), 15, places=5)
        print('LOFT transforms: source scales applied once, later path scaling remains live', flush=True)

    def test_existing_create_shapes(self):
        for kind in ('LINE', 'RECTANGLE', 'CIRCLE', 'ELLIPSE', 'ARC', 'NGON', 'STAR', 'HELIX'):
            bpy.ops.max.create_shape(kind=kind)
            ob = loft.make_loft(bpy.context, self.path, bpy.context.active_object)
            self.assertGreater(len(evaluated(ob)[0]), 0, kind)
        print('LOFT Create sources: Line, Rectangle, Circle, Ellipse, Arc, NGon, Star, Helix verified', flush=True)

    def test_save_reload_keeps_live_sources(self):
        self.path.data.extrude = .25
        rendering_modifier(self.shape, True, True)
        ob = self.make()
        ob.max_loft.scale_end = 150
        with tempfile.TemporaryDirectory(prefix='maxxed-loft-') as folder:
            filename = os.path.join(folder, 'loft.blend')
            bpy.ops.wm.save_as_mainfile(filepath=filename)
            bpy.ops.wm.open_mainfile(filepath=filename)
            loaded = bpy.data.objects['Loft001']
            self.assertTrue(loft.is_loft(loaded))
            self.assertEqual(loaded.max_loft.scale_end, 150)
            loaded.max_loft.path.data.splines[0].points[1].co.z = 8
            loaded.max_loft.path.data.update_tag()
            self.assertAlmostEqual(max(v[2] for v in evaluated(loaded)[0]), 8)
        print('LOFT persistence: save/reload preserves settings, sources and live mesh updates', flush=True)


suite = unittest.defaultTestLoader.loadTestsFromTestCase(LoftTests)
result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
