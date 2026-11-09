"""Audit sandbox copies, never source scenes.

blender -b --factory-startup --python-exit-code 1 --python tests/report_max_scenes.py -- sandbox-inputs output.json
Use an isolated profile with io_scene_max 1.9.2 installed.
"""

import contextlib
import io
import json
import math
import pathlib
import sys

import addon_utils
import bpy


def inspect_scene(path):
    from io_scene_max import import_max as reader
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        result = bpy.ops.max.merge_max(filepath=str(path), units="INCHES")
    objects = list(bpy.context.scene.objects)
    meshes = [o for o in objects if o.type == "MESH"]
    nodes = []
    for node in reader.SCENE_LIST[0].children:
        if reader.get_guid(node) == 1 and reader.get_super_id(node) == 1:
            _prs, msh, _mat, _layer = reader.get_matrix_mesh_material(node)
            nodes.append(dict(name=reader.get_node_name(node), type=reader.get_cls_name(msh),
                              parent=reader.get_node_name(reader.get_node_parent(node))))
    names = {o.name for o in objects}
    missing = [n for n in nodes if n["name"] not in names]
    if missing:
        assert "source nodes were not imported" in log.getvalue(), "Partial import needs a visible warning"
    finite = all(math.isfinite(v) for o in objects for row in o.matrix_world for v in row)
    assert finite and result == {"FINISHED"} and meshes, path
    return dict(result=sorted(result), source_nodes=len(nodes), objects=len(objects), meshes=len(meshes),
                empty_meshes=[o.name for o in meshes if not o.data.vertices],
                vertices=sum(len(o.data.vertices) for o in meshes), faces=sum(len(o.data.polygons) for o in meshes),
                materials=[m.name for m in bpy.data.materials],
                images=[dict(name=im.name, path=im.filepath, exists=pathlib.Path(bpy.path.abspath(im.filepath)).is_file())
                        for im in bpy.data.images if im.source == "FILE"],
                uv_meshes=sum(bool(o.data.uv_layers) for o in meshes),
                parents={o.name: o.parent.name for o in objects if o.parent},
                helpers=[o.name for o in objects if o.type == "EMPTY"],
                recovered_smoothing=sum("max_smoothing_group" in o.data.attributes for o in meshes),
                sharp_edges=sum(sum(e.use_edge_sharp for e in o.data.edges) for o in meshes),
                units="INCHES (assumed, not read from the Max scene)", all_transforms_finite=finite,
                object_data=[dict(name=o.name, type=o.type, matrix=[list(row) for row in o.matrix_world]) for o in objects],
                missing_nodes=missing, reader_messages=log.getvalue().splitlines())


if __name__ == "__main__":
    source, output = map(pathlib.Path, sys.argv[sys.argv.index("--")+1:])
    paths = sorted(p for p in source.rglob("*.max") if "autoback" not in p.parts)
    rows = []
    for i, path in enumerate(paths, 1):
        print(f"[{i}/{len(paths)}] {path.relative_to(source)}", flush=True)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
        addon_utils.enable("io_scene_max", default_set=True)
        row = inspect_scene(path)
        row["file"] = path.relative_to(source).as_posix()
        inches = {o.name: o.matrix_world.copy() for o in bpy.context.scene.objects}
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        with contextlib.redirect_stdout(io.StringIO()):
            assert bpy.ops.max.merge_max(filepath=str(path), units="GENERIC") == {"FINISHED"}
        raw = {o.name: o.matrix_world.copy() for o in bpy.context.scene.objects}
        assert set(raw) == set(inches), path
        delta = max(abs(inches[name][i][j] - matrix[i][j] * 0.0254)
                    for name, matrix in raw.items() for i in range(3) for j in range(4))
        magnitude = max(abs(value) for matrix in inches.values() for line in matrix for value in line)
        assert delta < max(2e-5, magnitude * 2e-6), (path, delta, magnitude)
        row["uniform_unit_conversion_max_abs"] = delta
        rows.append(row)
        output.write_text(json.dumps(rows, indent=2))
        print(f'SCENE {row["file"]}: meshes={row["meshes"]} materials={len(row["materials"])} '
              f'parents={len(row["parents"])} smoothing={row["recovered_smoothing"]} missing={len(row["missing_nodes"])}', flush=True)
    print(f"VERIFIED {len(rows)}/{len(paths)} copied Max scenes imported, finite transforms, uniform hierarchy unit conversion", flush=True)
