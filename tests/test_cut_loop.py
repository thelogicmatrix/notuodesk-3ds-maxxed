"""Run: blender -b --factory-startup --python tests/test_cut_loop.py"""
import sys
from pathlib import Path
from types import SimpleNamespace

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from notuodesk_3ds_maxxed import cut_loop as tools


def plane():
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in ((-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0))]
    bm.faces.new(vs)
    bm.normal_update()
    return bm, vs


def project(co):
    return co.xy


class Picker(tools._SurfaceTool):
    """Use deterministic orthographic rays with the real picking code and BVH."""
    def _project(self, co):
        return co.xy * 100 + Vector((200, 200))

    def _ray(self, mouse):
        co = (mouse - Vector((200, 200))) / 100
        return Vector((co.x, co.y, 10)), Vector((0, 0, -1))


bm = bmesh.new()
front = bm.faces.new([bm.verts.new((x, y, 1)) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
back = bm.faces.new([bm.verts.new((x, y, 0)) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
front.hide_set(True)
area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
picker = Picker()
picker.bm = bm
picker.region = region
for is_cut in (True, False):
    picker.is_cut = is_cut
    picker.bvh = None
    event = SimpleNamespace(mouse_x=region.x + 220, mouse_y=region.y + 210)
    hit = picker._pick(bpy.context, event)
    assert hit is not None, ('Cut' if is_cut else 'SwiftLoop', 'hidden front face blocked visible back face')
    assert hit[0] == ('FACE' if is_cut else 'EDGE'), hit
    assert hit[1] in ([back] if is_cut else back.edges)
    assert abs(hit[2].z) < 1e-5, hit
    back.hide_set(True)
    picker.bvh = None
    assert picker._pick(bpy.context, event) is None
    back.hide_set(False)
print('PASS Cut and SwiftLoop pick visible back face through hidden front face, all-hidden mesh misses')
bm.free()


for kind, co, face_count in (('EDGE', (1, 0, 0), 2), ('FACE', (.2, .3, 0), 4)):
    bm, vs = plane()
    loose = bm.verts.new(co)
    elem = bm.edges.get((vs[1], vs[2])) if kind == 'EDGE' else next(iter(bm.faces))
    end = tools.cut_segment(bm, vs[0], (kind, elem, Vector(co)), project)
    assert end != loose, (kind, 'cut reused unrelated loose vertex')
    assert len(loose.link_edges) == 0
    assert bm.edges.get((vs[0], end))
    assert (len(bm.verts), len(bm.faces)) == (6, face_count)
    assert all(f.calc_area() > 0 for f in bm.faces)
    print('PASS Cut ' + kind.lower() + ' endpoint ignores coincident loose vertex, creates connected segment')
    bm.free()


bm, vs = plane()
loose = bm.verts.new(vs[1].co)
for kind, elem in (('EDGE', bm.edges.get((vs[1], vs[2]))), ('FACE', next(iter(bm.faces)))):
    assert tools.resolve_hit(bm, (kind, elem, vs[1].co.copy())) == vs[1]
assert len(bm.verts) == 5 and len(loose.link_edges) == 0
print('PASS Cut reuses the picked edge or face vertex instead of a coincident loose vertex')
bm.free()


bm, vs = plane()
end = tools.cut_segment(bm, vs[0], ('EDGE', bm.edges.get((vs[1], vs[2])), Vector((1, 0, 0))), project)
assert (len(bm.verts), len(bm.faces)) == (5, 2)
assert bm.edges.get((vs[0], end))
print('PASS Cut vertex to edge: vertices=5 faces=2')
end = tools.cut_segment(bm, end, ('FACE', next(f for f in bm.faces if len(f.verts) == 4), Vector((0, .5, 0))), project)
assert len(bm.verts) == 6 and len(bm.faces) >= 3
assert end.co == Vector((0, .5, 0))
assert all(f.calc_area() > 0 for f in bm.faces)
print('PASS Cut edge to face: connected face endpoint, positive face areas')
bm.free()

bm, vs = plane()
edge = bm.edges.get((vs[0], vs[3]))
start = ('EDGE', edge, Vector((-1, 0, 0)))
end = tools.cut_segment(bm, start, ('EDGE', edge, Vector((-1, -.5, 0))), project)
assert (end.co - Vector((-1, -.5, 0))).length < 1e-5
assert len(bm.verts) == 6
print('PASS Cut two points on same edge')
bm.free()

bm, vs = plane()
uv = bm.loops.layers.uv.new('UVMap')
face = next(iter(bm.faces))
face.material_index = 3
for loop in face.loops:
    loop[uv].uv = loop.vert.co.xy
end = tools.cut_segment(bm, vs[0], ('FACE', face, Vector((.2,.3,0))), project)
assert all(f.material_index == 3 for f in bm.faces)
assert all((loop[uv].uv - loop.vert.co.xy).length < 1e-5 for f in bm.faces for loop in f.loops)
assert len(end.link_edges) >= 2
print('PASS Cut face endpoint preserves UVs and material')
bm.free()

bm = bmesh.new()
outline = [(0,0,0),(2,0,0),(2,1,0),(1,1,0),(1,2,0),(0,2,0)]
verts = [bm.verts.new(p) for p in outline]
face = bm.faces.new(verts)
bm.normal_update()
end = tools.cut_segment(bm, verts[0], ('FACE', face, Vector((.5,1.5,0))), project)
assert abs(sum(f.calc_area() for f in bm.faces) - 3) < 1e-5
assert all(f.calc_area() > 0 for f in bm.faces)
print('PASS Cut concave face keeps surface area')
bm.free()

bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=3, y_segments=1, size=1)
bm.normal_update()
v0 = min(bm.verts, key=lambda v: (v.co - Vector((-1, -1, 0))).length)
edge = next(e for e in bm.edges if all(abs(v.co.x - 1) < 1e-5 for v in e.verts))
end = tools.cut_segment(bm, v0, ('EDGE', edge, Vector((1, .5, 0))), project)
assert len(bm.faces) == 6
assert all(f.calc_area() > 0 for f in bm.faces)
print('PASS Cut crosses three faces')
bm.free()

bm = bmesh.new()
bmesh.ops.create_cube(bm, size=2)
bm.normal_update()
edge = next(e for e in bm.edges if all(abs(v.co.x + 1) < 1e-5 and abs(v.co.y + 1) < 1e-5 for v in e.verts))
loop = tools.insert_loop(bm, edge, .25)
assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (12, 20, 10)
assert len(loop) == 4
assert all(abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-5 for e in loop)
assert len(tools.edge_loop(loop[0])) == 4
print('PASS SwiftLoop closed cube ring: vertices=12 edges=20 faces=10')
tools.remove_loop(bm, loop[0])
assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (8, 12, 6)
print('PASS Ctrl+Shift removes loop and its vertices')
bm.free()

bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=1)
bm.normal_update()
edge = next(e for e in bm.edges if len(e.link_faces) == 2 and all(len(f.verts) == 4 for f in e.link_faces)
            and abs(e.verts[0].co.z - e.verts[1].co.z) > .1)
linear = tools.loop_position(edge, .5)
flow = tools.loop_position(edge, .5, True)
assert (flow - linear).length > .001
assert abs(flow.length - 1) < abs(linear.length - 1)
loop = tools.insert_loop(bm, edge, .5, True)
assert len(loop) == 12
assert all(f.calc_area() > 0 for f in bm.faces)
print('PASS Shift surface flow follows curved sphere, 12-edge loop')
bm.free()

bm, vs = plane()
edge = bm.edges.get((vs[0], vs[3]))
tools.insert_loop(bm, edge, .25)
assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (6, 7, 2)
edge = next(e for e in bm.edges if all(abs(v.co.x + 1) < 1e-5 for v in e.verts) and max(v.co.y for v in e.verts) > .9)
tools.insert_loop(bm, edge, .5)
assert (len(bm.verts), len(bm.edges), len(bm.faces)) == (8, 10, 3)
print('PASS SwiftLoop two open loops: edges=7 then 10')
bm.free()
print('PASS all Cut and SwiftLoop geometry checks')

import addon_utils
addon_utils.enable('notuodesk_3ds_maxxed', default_set=True)
assert bpy.ops.max.cut.get_rna_type().identifier == 'MAX_OT_cut'
assert bpy.ops.max.swift_loop.get_rna_type().identifier == 'MAX_OT_swift_loop'
addon_utils.disable('notuodesk_3ds_maxxed', default_set=True)
print('PASS add-on registration and unregister')
