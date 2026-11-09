"""Run with isolated Blender: blender -b --factory-startup --python tests/test_editable_poly_panel.py."""
import bpy
import addon_utils
import bmesh

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
from notuodesk_3ds_maxxed import editable_poly as ep


def mesh(verts, edges=(), faces=(), level=4):
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    me = bpy.data.meshes.new("Fixture")
    me.from_pydata(verts, edges, faces)
    ob = bpy.data.objects.new("Fixture", me)
    bpy.context.collection.objects.link(ob)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.max.subobject(level=level)
    bpy.ops.mesh.select_all(action="SELECT")
    return ob, bmesh.from_edit_mesh(me)


QUAD = [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)]
CUBE = [(-1, -1, -1), (-1, -1, 1), (-1, 1, -1), (-1, 1, 1), (1, -1, -1), (1, -1, 1), (1, 1, -1), (1, 1, 1)]
CUBE_FACES = [(0, 4, 6, 2), (1, 3, 7, 5), (0, 1, 5, 4), (2, 6, 7, 3), (0, 2, 3, 1), (4, 5, 7, 6)]


def run():
    assert hasattr(bpy.types, "MAX_OT_poly_settings")
    ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
    s = ep.settings(bpy.context, "EXTRUDE")
    s.amount = 0.7
    assert bpy.ops.max.edit_poly(op="EXTRUDE") == {"FINISHED"}
    assert len(bm.faces) == 5 and max(v.co.z for v in bm.verts) > 0.69
    assert ep.settings(bpy.context, "EXTRUDE").amount == s.amount
    print("PASS Extrude last settings: 5 faces, height 0.7", flush=True)
    ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)], level=2)
    assert bpy.ops.max.edit_poly(op="INSERT_VERTEX") == {"FINISHED"}
    assert len(bm.verts) == 8
    print("PASS Insert Vertex: 4 to 8 vertices", flush=True)
    ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
    assert bpy.ops.max.edit_poly(op="RETRIANGULATE") == {"FINISHED"}
    assert len(bm.faces) == 2
    print("PASS Retriangulate: quad to 2 triangles", flush=True)
    ob, bm = mesh(QUAD + [(0, 0, 3)], faces=[(0, 1, 2, 3)], level=1)
    assert bpy.ops.max.edit_poly(op="DELETE_ISOLATED") == {"FINISHED"}
    assert len(bm.verts) == 4
    print("PASS Delete Isolated Vertices: 5 to 4 vertices", flush=True)
    ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
    assert bpy.ops.max.poly_smoothing(action="TOGGLE", group=32) == {"FINISHED"}
    layer = bm.faces.layers.int.get(ep.SG_ATTRIBUTE)
    assert all((f[layer] & 0xffffffff) == 0x80000000 for f in bm.faces)
    bpy.ops.mesh.subdivide(number_cuts=1)
    assert all((f[layer] & 0xffffffff) == 0x80000000 for f in bm.faces)
    bpy.ops.object.mode_set(mode="OBJECT")
    assert ob.data.attributes[ep.SG_ATTRIBUTE].domain == "FACE"
    print("PASS Smoothing group 32 survives subdivide and Object mode", flush=True)
    more_actions()
    addon_utils.disable("notuodesk_3ds_maxxed")
    addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
    print("PASS unregister/register", flush=True)


def act(action):
    result = bpy.ops.max.edit_poly(op=action)
    assert result == {"FINISHED"}, (action, result)


def more_actions():
    for level in (1, 2):
        ob, bm = mesh(QUAD, edges=[(0, 1), (1, 2), (2, 3)], level=level)
        old = len(bm.verts)
        act("EXTRUDE")
        assert len(bm.verts) > old
    print("PASS Extrude at Vertex and Edge levels: vertex counts increase", flush=True)
    for kind in ("LOCAL", "POLYGON"):
        ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
        ep.settings(bpy.context, "EXTRUDE").extrusion_type = kind
        act("EXTRUDE")
        assert max(v.co.z for v in bm.verts) > 0.09
    print("PASS Extrude Local Normal and By Polygon move new faces", flush=True)
    ob, bm = mesh(CUBE, faces=CUBE_FACES, level=2)
    s = ep.settings(bpy.context, "CHAMFER")
    s.amount, s.segments = 0.2, 2
    act("CHAMFER")
    assert len(bm.verts) > 8
    print("PASS Chamfer: 2 segments add geometry", flush=True)
    verts = QUAD + [(x, y, 2) for x, y, z in QUAD]
    edges = [(i, (i + 1) % 4) for i in range(4)] + [(i + 4, (i + 1) % 4 + 4) for i in range(4)]
    ob, bm = mesh(verts, edges=edges, level=3)
    ep.settings(bpy.context, "BRIDGE").segments = 3
    act("BRIDGE")
    assert len(bm.faces) == 12
    print("PASS Bridge: 3 segments create 12 faces between 4-edge borders", flush=True)
    ob, bm = mesh(verts, edges=edges, level=3)
    s = ep.settings(bpy.context, "BRIDGE")
    s.segments, s.taper, s.bias = 4, 50, 25
    act("BRIDGE")
    assert len(bm.faces) == 16 and min(v.co.x for v in bm.verts) < -0.1
    print("PASS Bridge Taper and Bias widen intermediate bridge rings", flush=True)
    ob, bm = mesh(QUAD + [(0.00001, 0, 0)], faces=[(0, 1, 2, 3)], level=1)
    act("WELD")
    assert len(bm.verts) == 4
    print("PASS Weld: threshold merges coincident vertices", flush=True)
    for action in ("CONNECT", "TESSELLATE", "MSMOOTH"):
        ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)], level=2)
        act(action)
        assert len(bm.verts) == 9 and len(bm.faces) == 4, action
        print(f"PASS {action}: quad to 9 vertices and 4 faces", flush=True)
    for action in ("INSET", "BEVEL"):
        ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
        act(action)
        assert len(bm.faces) == 5, action
        print(f"PASS {action}: quad to 5 faces", flush=True)
    ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
    ep.settings(bpy.context, "OUTLINE").amount = 0.1
    act("OUTLINE")
    assert len(bm.faces) == 1 and min(v.co.x for v in bm.verts) < -0.09
    print("PASS Outline expands boundary without adding faces", flush=True)
    ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)], level=5)
    act("INSERT_VERTEX")
    assert len(bm.faces) == 4 and len(bm.verts) == 5
    print("PASS Insert Vertex at Element level pokes selected faces", flush=True)
    ob, bm = mesh(QUAD, faces=[(0, 1, 2), (0, 2, 3)], level=2)
    bpy.ops.mesh.select_all(action="DESELECT")
    diagonal = next(e for e in bm.edges if len(e.link_faces) == 2)
    old = {tuple(v.co) for v in diagonal.verts}
    diagonal.select_set(True)
    act("TURN")
    new = next(e for e in bm.edges if len(e.link_faces) == 2)
    assert {tuple(v.co) for v in new.verts} != old
    print("PASS Turn rotates a selected diagonal", flush=True)
    ob, bm = mesh(QUAD, faces=[(0, 1, 2), (0, 2, 3)], level=2)
    act("SPLIT")
    assert len(bm.verts) > 4
    print("PASS Split separates shared edge vertices", flush=True)
    ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)], level=3)
    act("CREATE_SHAPE")
    curve = next(o for o in bpy.data.objects if o.type == "CURVE")
    assert len(curve.data.splines) == 4 and len(bm.faces) == 1
    print("PASS Create Shape copies selected edges to 4 curve splines", flush=True)
    for action in ("PLANAR_X", "PLANAR_Y", "PLANAR_Z", "MAKE_PLANAR", "VIEW_ALIGN", "GRID_ALIGN"):
        ob, bm = mesh([(0, 0, 0), (2, 0, 1), (2, 2, 0), (0, 2, 2)], faces=[(0, 1, 2, 3)])
        before = [v.co.copy() for v in bm.verts]
        act(action)
        assert any((a - v.co).length > 0.001 for a, v in zip(before, bm.verts)), action
        if action.startswith("PLANAR_"):
            axis = "XYZ".index(action[-1])
            assert max(v.co[axis] for v in bm.verts) - min(v.co[axis] for v in bm.verts) < 0.0001
        print(f"PASS {action}: flattens selected vertices", flush=True)
    ob, bm = mesh(QUAD, edges=[(0, 1), (1, 2), (2, 3)], level=2)
    act("CREATE")
    assert len(bm.faces) == 1
    print("PASS Create forms a polygon from selected vertices", flush=True)
    ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
    act("COPY_SELECTION")
    bpy.ops.mesh.select_all(action="DESELECT")
    act("PASTE_SELECTION")
    assert sum(f.select for f in bm.faces) == 1
    print("PASS Named Selections Copy/Paste restores selection", flush=True)
    ob, bm = mesh(QUAD, faces=[(0, 1, 2), (0, 2, 3)])
    bpy.ops.mesh.select_all(action="DESELECT")
    bm.faces.ensure_lookup_table()
    bm.faces[0].select_set(True)
    act("SELECT_ANGLE")
    assert sum(f.select for f in bm.faces) == 2
    print("PASS By Angle expands across coplanar adjacent faces", flush=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    bpy.ops.max.subobject(level=4)
    bm = bmesh.from_edit_mesh(ob.data)
    bpy.ops.mesh.select_all(action="SELECT")
    act("SLICE_PLANE")
    assert ob.max_poly.slice_plane and len(bm.verts) == 8
    plane = ep.settings(bpy.context, "SLICE_PLANE")
    plane.plane_z = 0.25
    act("SLICE")
    assert len(bm.verts) == 12
    act("RESET_PLANE")
    assert plane.plane_z == 0 and plane.normal_z == 1
    print("PASS Slice Plane toggles, Slice cuts cube to 12 vertices, Reset Plane restores Z", flush=True)
    ob, bm = mesh(CUBE, faces=CUBE_FACES)
    act("QUICK_SLICE")
    assert len(bm.verts) == 12
    print("PASS QuickSlice EXEC uses stored plane and adds 4 intersection vertices", flush=True)
    ob, bm = mesh(CUBE, faces=CUBE_FACES, level=1)
    before = [v.co.copy() for v in bm.verts]
    act("RELAX")
    assert any((co - v.co).length > 0.1 for co, v in zip(before, bm.verts))
    print("PASS Relax moves selected vertices", flush=True)
    ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
    ob.max_poly.material_id = 3
    bpy.ops.max.poly_material(action="SET")
    assert all(f.material_index == 2 for f in bm.faces) and len(ob.data.materials) == 3
    bpy.ops.mesh.select_all(action="DESELECT")
    ob.max_poly.select_id = 3
    bpy.ops.max.poly_material(action="SELECT")
    assert all(f.select for f in bm.faces)
    ob.max_poly.material_name = "2"
    bpy.ops.max.poly_material(action="NAME")
    assert all(f.select for f in bm.faces)
    print("PASS Material IDs Set/Select/Select by Name use one-based slots", flush=True)
    bpy.ops.max.poly_smoothing(action="AUTO")
    layer = bm.faces.layers.int.get(ep.SG_ATTRIBUTE)
    assert all(f[layer] == 1 for f in bm.faces)
    bpy.ops.max.poly_smoothing(action="CLEAR")
    assert all(f[layer] == 0 and not f.smooth for f in bm.faces)
    bpy.ops.max.poly_smoothing(action="TOGGLE", group=1)
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.max.poly_smoothing(action="SELECT")
    assert all(f.select for f in bm.faces)
    print("PASS Smoothing Groups Auto Smooth/Clear All/Select By SG", flush=True)
    ob.max_poly.soft = True
    ob.max_poly.edge_distance = True
    ob.max_poly.falloff = 2.5
    ob.max_poly.falloff_curve = "SHARP"
    ts = bpy.context.tool_settings
    assert ts.use_proportional_edit and ts.use_proportional_connected and ts.proportional_size == 2.5
    assert ts.proportional_edit_falloff == "SHARP"
    print("PASS Soft Selection drives proportional radius, connectivity and curve", flush=True)
    for face in bm.faces:
        face.smooth = False
    ob.max_poly.smooth_result = True
    assert all(f.smooth for f in bm.faces)
    ob.max_poly.smooth_result = False
    assert all(not f.smooth for f in bm.faces)
    print("PASS Smooth Result restores original face shading", flush=True)
    ob.max_poly.nurms = True
    ob.max_poly.iterations = 2
    ob.max_poly.isoline = True
    mod = ob.modifiers.get("NURMS Subdivision")
    assert mod and mod.type == "SUBSURF" and mod.levels == 2 and mod.show_only_control_edges
    ob.max_poly.nurms = False
    assert not mod.show_viewport and not mod.show_render
    print("PASS NURMS uses native Subdivision Surface, iterations, isolines and visibility", flush=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    from notuodesk_3ds_maxxed.ui_panel import _is_poly
    assert _is_poly(bpy.context), "NURMS must leave Editable Poly selected at the stack base"
    print("PASS NURMS leaves the Editable Poly rollouts visible at Object level", flush=True)
    bpy.ops.max.subobject(level=2)
    bm = bmesh.from_edit_mesh(ob.data)
    ob.max_poly.crease = 0.6
    bpy.ops.max.poly_weight(crease=True)
    layer = bm.edges.layers.float.get("crease_edge")
    assert all(abs(e[layer] - 0.6) < 0.0001 for e in bm.edges if e.select)
    print("PASS Crease writes Blender crease_edge attribute", flush=True)
    smoothing_edges()
    shift_tests()
    attach_tests()
    for action in ep.UNSUPPORTED:
        assert bpy.ops.max.edit_poly(op=action) == {"CANCELLED"}, action
    print("PASS Unsupported actions cancel with explicit explanations", flush=True)


def shift_tests():
    verts = [(x, y, 0) for y in range(4) for x in range(4)]
    faces = [(y * 4 + x, y * 4 + x + 1, (y + 1) * 4 + x + 1, (y + 1) * 4 + x) for y in range(3) for x in range(3)]
    for action in ("RING", "LOOP", "RING_SHIFT_UP", "RING_SHIFT_DOWN", "LOOP_SHIFT_UP", "LOOP_SHIFT_DOWN"):
        ob, bm = mesh(verts, faces=faces, level=2)
        bpy.ops.mesh.select_all(action="DESELECT")
        edge = next(e for e in bm.edges if {tuple(v.co) for v in e.verts} == {(1, 1, 0), (2, 1, 0)})
        edge.select_set(True)
        act(action)
        selected = {e for e in bm.edges if e.select}
        assert selected and (selected != {edge}), action
        print(f"PASS {action}: changes the selected edge set", flush=True)


def attach_tests():
    ob, bm = mesh(QUAD, faces=[(0, 1, 2, 3)])
    me = bpy.data.meshes.new("Other")
    me.from_pydata(QUAD, [], [(0, 1, 2, 3)])
    other = bpy.data.objects.new("Other", me)
    bpy.context.collection.objects.link(other)
    assert bpy.ops.max.poly_attach_list(target=other.name) == {"FINISHED"}
    bm = bmesh.from_edit_mesh(ob.data)
    assert len(bm.faces) == 2
    print("PASS Attach List joins selected object and restores Edit mode", flush=True)
    act("DETACH")
    assert len([o for o in bpy.data.objects if o.type == "MESH"]) == 2
    print("PASS Detach creates another mesh object", flush=True)
    other = next(o for o in bpy.data.objects if o != ob)
    other.select_set(True)
    act("ATTACH")
    assert len([o for o in bpy.data.objects if o.type == "MESH"]) == 1
    print("PASS Attach joins the other selected mesh", flush=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    before = len(ob.data.polygons)
    act("TESSELLATE")
    assert bpy.context.mode == "OBJECT" and len(ob.data.polygons) > before
    print("PASS Object-level Tessellate affects whole mesh and restores Object mode", flush=True)
    bpy.ops.max.subobject(level=4)
    roundtrip()


def roundtrip():
    import os
    ob = bpy.context.active_object
    bpy.ops.max.poly_smoothing(action="TOGGLE", group=32)
    ep.settings(bpy.context, "EXTRUDE").amount = 0.37
    bpy.ops.object.mode_set(mode="OBJECT")
    path = os.path.join(os.environ["BLENDER_USER_CONFIG"], "panel-roundtrip.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    ob = bpy.context.active_object
    assert ep.SG_ATTRIBUTE in ob.data.attributes
    assert any(value.value & 0x80000000 for value in ob.data.attributes[ep.SG_ATTRIBUTE].data)
    bpy.ops.max.subobject(level=4)
    assert abs(ep.settings(bpy.context, "EXTRUDE").amount - 0.37) < 0.0001
    print("PASS Smoothing attribute and last settings survive saving and reopening blend", flush=True)


def smoothing_edges():
    ob, bm = mesh(QUAD, faces=[(0, 1, 2), (0, 2, 3)])
    bpy.ops.mesh.select_all(action="DESELECT")
    bm.faces.ensure_lookup_table()
    bm.faces[0].select_set(True)
    bpy.ops.max.poly_smoothing(action="TOGGLE", group=1)
    bpy.ops.mesh.select_all(action="DESELECT")
    bm.faces[1].select_set(True)
    bpy.ops.max.poly_smoothing(action="TOGGLE", group=2)
    edge = next(e for e in bm.edges if len(e.link_faces) == 2)
    assert not edge.smooth
    bpy.ops.max.poly_smoothing(action="TOGGLE", group=1)
    assert edge.smooth
    print("PASS Smoothing group overlap drives shared edge sharpness", flush=True)
    ob, bm = mesh([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], faces=[(0, 1, 2), (1, 0, 3)])
    bpy.ops.mesh.select_all(action="DESELECT")
    bm.faces.ensure_lookup_table()
    bm.faces[0].select_set(True)
    bpy.ops.max.poly_smoothing(action="TOGGLE", group=1)
    bpy.ops.mesh.select_all(action="DESELECT")
    bm.faces[1].select_set(True)
    bpy.ops.max.poly_smoothing(action="AUTO")
    edge = next(e for e in bm.edges if len(e.link_faces) == 2)
    assert not edge.smooth
    print("PASS Auto Smooth preserves hard boundaries with unselected faces", flush=True)


if __name__ == "__main__":
    run()
