"""Compare a copied Max FBX through the add-on's import/export/import operators.

blender -b --factory-startup --python-exit-code 1 --python tests/roundtrip_max_fbx.py -- copy.fbx output-directory
Use an isolated BLENDER_USER_SCRIPTS/CONFIG/EXTENSIONS profile.
"""

import json
import pathlib
import sys

import addon_utils
import bpy


def snapshot():
    result = {}
    for ob in bpy.context.scene.objects:
        data = dict(type=ob.type, parent=ob.parent.name if ob.parent else None,
                    matrix=[list(row) for row in ob.matrix_world])
        if ob.type == "MESH":
            mesh = ob.data
            data.update(vertices=[list(v.co) for v in mesh.vertices], faces=[list(p.vertices) for p in mesh.polygons],
                        normals=[list(n.vector) for n in mesh.corner_normals],
                        smooth=[p.use_smooth for p in mesh.polygons], sharp=[e.use_edge_sharp for e in mesh.edges],
                        edges=[list(e.vertices) for e in mesh.edges],
                        materials=[m.name if m else None for m in mesh.materials],
                        material_indices=[p.material_index for p in mesh.polygons])
        result[ob.name] = data
    return result


def max_delta(a, b):
    assert len(a) == len(b), (len(a), len(b))
    return max((abs(x-y) for va, vb in zip(a, b) for x, y in zip(va, vb)), default=0)


if __name__ == "__main__":
    source, directory = map(pathlib.Path, sys.argv[sys.argv.index("--")+1:])
    directory.mkdir(parents=True, exist_ok=True)
    addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    assert bpy.ops.max.import_max_fbx(filepath=str(source), animation=False) == {"FINISHED"}
    before = snapshot()
    assert before, "Reference import is empty"
    (directory / "fbx-before.json").write_text(json.dumps(before, indent=2))
    path = directory / "3World-roundtrip.fbx"
    units = bpy.context.scene.max_system_units
    assert bpy.ops.max.export_max_fbx(filepath=str(path), animation=False) == {"FINISHED"}
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)
    assert bpy.ops.max.import_max_fbx(filepath=str(path), animation=False) == {"FINISHED"}
    after = snapshot()
    (directory / "fbx-after.json").write_text(json.dumps(after, indent=2))
    assert set(before) == set(after), (set(before)-set(after), set(after)-set(before))
    matrix_error = vertex_error = normal_error = 0
    smoothing_changes = []
    for name, a in before.items():
        b = after[name]
        assert a["parent"] == b["parent"] and a["type"] == b["type"], name
        matrix_error = max(matrix_error, max_delta(a["matrix"], b["matrix"]))
        if a["type"] != "MESH":
            continue
        assert a["faces"] == b["faces"], name
        assert a["materials"] == b["materials"], (name, a["materials"], b["materials"])
        assert a["material_indices"] == b["material_indices"], name
        vertex_error = max(vertex_error, max_delta(a["vertices"], b["vertices"]))
        normal_error = max(normal_error, max_delta(a["normals"], b["normals"]))
        sharp_a = {tuple(sorted(edge)): sharp for edge, sharp in zip(a["edges"], a["sharp"])}
        sharp_b = {tuple(sorted(edge)): sharp for edge, sharp in zip(b["edges"], b["sharp"])}
        if a["smooth"] != b["smooth"] or sharp_a != sharp_b:
            smoothing_changes.append(name)
    report = dict(objects=len(before), meshes=sum(v["type"]=="MESH" for v in before.values()),
                  units=units, matrix_max_abs=matrix_error, vertex_max_abs=vertex_error,
                  corner_normal_max_abs=normal_error, smoothing_flag_changes=smoothing_changes)
    (directory / "fbx-comparison.json").write_text(json.dumps(report, indent=2))
    print("FBX_COMPARISON " + json.dumps(report), flush=True)
    assert matrix_error < 2e-5 and vertex_error < 2e-5 and normal_error < 2e-5, report
    assert not smoothing_changes, report
    print("VERIFIED reference FBX: names, transforms, scale, pivots, hierarchy, topology, normals, smoothing and material names", flush=True)
