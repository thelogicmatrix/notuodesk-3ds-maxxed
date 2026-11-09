"""Repair unit scaling and recover smoothing from io_scene_max's parsed meshes."""

import importlib
import struct

import bpy
from mathutils import Matrix


def scale_roots(context, objects, factor):
    context.view_layer.update()
    imported = set(objects)
    scale = Matrix.Scale(factor, 4)
    for ob in objects:
        if ob.parent not in imported:
            ob.matrix_world = scale @ ob.matrix_world
    context.view_layer.update()


def apply_smoothing(mesh, masks):
    """Max faces are smooth across an edge if their masks share any bit."""
    if len(masks) != len(mesh.polygons):
        return False
    attr = mesh.attributes.get("max_smoothing_group")
    if attr is None:
        attr = mesh.attributes.new("max_smoothing_group", "INT", "FACE")
    attr.data.foreach_set("value", [m if m < 0x80000000 else m - 0x100000000 for m in masks])
    adjacent = [[] for _ in mesh.edges]
    for poly, mask in zip(mesh.polygons, masks):
        poly.use_smooth = bool(mask)
        for li in poly.loop_indices:
            adjacent[mesh.loops[li].edge_index].append(mask)
    for edge, faces in zip(mesh.edges, adjacent):
        edge.use_edge_sharp = len(faces) != 2 or not bool(faces[0] & faces[1])
    mesh.update()
    return True


def _mesh_smoothing(reader, msh, seen=None):
    """Read existing parsed data, never replace or patch the reader's functions."""
    seen = set() if seen is None else seen
    if msh is None or id(msh) in seen or len(seen) > 256:
        return
    seen.add(id(msh))
    chunk = msh.get_first(0x08FE)
    if chunk:
        points = chunk.get_first(0x011A)
        triangles = chunk.get_first(0x0912)
        if points:
            faces = reader.calc_point_3d(points)
            yield [list(p.points) for p in faces], [p.flag3 & 0xFFFFFFFF for p in faces]
            return
        if triangles:
            count = struct.unpack_from("<I", triangles.data)[0]
            if len(triangles.data) == 4 + count * 20:
                faces = list(struct.iter_unpack("<IIIIHH", triangles.data[4:]))
                yield [list(p[:3]) for p in faces], [p[3] for p in faces]
            return
    for ref in reader.get_references(msh):
        yield from _mesh_smoothing(reader, ref, seen)


def _reader_data():
    operator = bpy.types.Operator.bl_rna_get_subclass_py("IMPORT_SCENE_OT_max")
    if operator is None:
        return None
    package = importlib.import_module(operator.__module__)
    if getattr(package, "__version__", None) != "1.9.2":
        return None
    reader = importlib.import_module(package.__name__ + ".import_max")
    if not reader.SCENE_LIST:
        return None
    return reader


def restore_material_names(materials, source_names):
    """Remove the reader's bitmap suffix using exact source material names."""
    names = sorted(set(source_names), key=len, reverse=True)
    for mat in materials:
        for name in names:
            if mat.name == name:
                break
            if name and mat.name.startswith(name + "_"):
                mat["max_bitmap"] = mat.name[len(name) + 1:]
                mat.name = name
                break


def recover_materials(materials):
    reader = _reader_data()
    if reader is None:
        return
    names = []
    for chunk in reader.SCENE_LIST[0].children:
        if reader.get_super_id(chunk) != 0xC00:  # MATERIAL_CLASS_ID
            continue
        for ident in (0x4000, 0x5431, 0x0FA0):
            name_chunk = chunk.get_first(ident)
            if name_chunk and name_chunk.children and isinstance(name_chunk.children[0].data, str):
                names.append(name_chunk.children[0].data)
        header = chunk.get_first(0x100)
        physical_name = header.get_first(0x4001) if header else None
        if physical_name and isinstance(physical_name.data, str):
            names.append(physical_name.data)
    restore_material_names(materials, names)


def missing_nodes(objects):
    reader = _reader_data()
    if reader is None:
        return []
    names = {o.name for o in objects}
    missing = []
    for node in reader.SCENE_LIST[0].children:
        if reader.get_guid(node) != 1 or reader.get_super_id(node) != 1:
            continue
        name = reader.get_node_name(node)
        if not any(n == name or (n.startswith(name + ".") and n[len(name) + 1:].isdigit()) for n in names):
            missing.append(name)
    return missing


def recover_smoothing(objects):
    """Use the 1.9.2 reader's retained scene data only when face topology matches."""
    reader = _reader_data()
    if reader is None:
        return 0
    remaining = [o for o in objects if o.type == "MESH"]
    restored = 0
    for node in reader.SCENE_LIST[0].children:
        if reader.get_guid(node) != 1 or reader.get_super_id(node) != 1:
            continue
        name = reader.get_node_name(node)
        _prs, msh, _mat, _layer = reader.get_matrix_mesh_material(node)
        for faces, masks in _mesh_smoothing(reader, msh):
            if not faces:
                continue
            candidates = [o for o in remaining if o.name == name or
                          (o.name.startswith(name + ".") and o.name[len(name) + 1:].isdigit())]
            for ob in candidates:
                if len(ob.data.polygons) != len(faces):
                    continue
                if all(list(p.vertices) == face for p, face in zip(ob.data.polygons, faces)):
                    apply_smoothing(ob.data, masks)
                    remaining.remove(ob)
                    restored += 1
                    break
    return restored
