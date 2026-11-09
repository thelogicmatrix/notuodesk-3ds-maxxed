"""Run in an isolated add-on profile:
blender -b --factory-startup --python-exit-code 1 --python tests/test_plane_plus.py

These checks catch wrong image proportions, unlocked size callbacks, misplaced
pivots, sideways UVs, lost materials and destructive freeze restoration.
"""
import os
import tempfile

import addon_utils
import bpy

addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
assert hasattr(bpy.types.Object, "max_plane_plus"), "PlanePlus parameters not registered"
from notuodesk_3ds_maxxed import plane_plus, freezing


def near(actual, expected):
    assert abs(actual - expected) < 0.0001, (actual, expected)


def image_file(folder, width, height):
    image = bpy.data.images.new("Reference", width=width, height=height)
    path = os.path.join(folder, f"{width}x{height}.png")
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    return path


with tempfile.TemporaryDirectory() as folder:
    for width, height, ratio in ((1920, 1080, 16 / 9), (1000, 2000, 0.5)):
        assert bpy.ops.max.plane_plus() == {"FINISHED"}
        ob = bpy.context.object
        p = ob.max_plane_plus
        path = image_file(folder, width, height)
        assert bpy.ops.max.plane_plus_image(filepath=path) == {"FINISHED"}
        near(p.width / p.length, ratio)
        p.width = 8
        near(p.length, 8 / ratio)
        p.length = 6
        near(p.width, 6 * ratio)
        p.uniform = False
        p.width = 10
        near(p.length, 6)
        p.uniform = True
        near(p.width / p.length, ratio)
        print(f"PASS image {width}x{height}: aspect, width lock, length lock, unlock", flush=True)

    p.uniform = False
    p.width, p.length = 8, 4
    for pivot, bounds in (
        ("CENTER", (-4, 4, -2, 2)),
        ("LEFT", (0, 8, 0, 4)), ("RIGHT", (-8, 0, 0, 4)),
        ("TOP_LEFT", (0, 8, -4, 0)), ("TOP", (-4, 4, -4, 0)),
        ("TOP_RIGHT", (-8, 0, -4, 0)), ("LEFT_EDGE", (0, 8, -2, 2)),
        ("RIGHT_EDGE", (-8, 0, -2, 2)), ("BOTTOM", (-4, 4, 0, 4)),
    ):
        p.pivot = pivot
        p.orientation = "HORIZONTAL"
        coords = [v.co for v in ob.data.vertices]
        for actual, expected in zip((min(v.x for v in coords), max(v.x for v in coords),
                                     min(v.y for v in coords), max(v.y for v in coords)), bounds):
            near(actual, expected)
        assert all(abs(v.z) < 0.0001 for v in coords)
        p.orientation = "VERTICAL"
        assert all(abs(v.co.y) < 0.0001 for v in ob.data.vertices)
        near(max(v.co.z for v in ob.data.vertices) - min(v.co.z for v in ob.data.vertices), 4)
    print("PASS nine pivots and horizontal/vertical geometry", flush=True)
    assert len(ob.data.uv_layers.active.data) == 4
    mat = ob.active_material
    assert mat and any(n.type == "TEX_IMAGE" and n.image == p.image for n in mat.node_tree.nodes)
    assert any(n.type == "EMISSION" for n in mat.node_tree.nodes)
    p.opacity = 35
    near(mat.node_tree.nodes["PlanePlus Opacity"].outputs[0].default_value, 0.35)
    p.enable_image = False
    assert not mat.node_tree.nodes["PlanePlus Surface"].inputs[0].is_linked
    p.enable_image = True
    assert mat.node_tree.nodes["PlanePlus Surface"].inputs[0].is_linked
    print("PASS UVs, image material, unlit shader, opacity and image toggle", flush=True)

    color = tuple(ob.color)
    mesh = ob.data
    assert not ob.max_show_frozen_gray
    bpy.ops.max.object_cmd(cmd="FREEZE")
    assert ob.hide_select and ob.max_frozen
    assert tuple(ob.color) == color
    assert ob.active_material == mat and ob.data == mesh
    assert bpy.context.scene.tool_settings.use_snap_selectable
    freezing.freeze(ob, bpy.context.scene)  # repeating freeze must not lose originals
    ob.max_show_frozen_gray = True
    assert tuple(round(c, 2) for c in ob.color) == (0.55, 0.55, 0.55, 1)
    assert ob.display_type == "SOLID"
    assert ob.active_material.node_tree.nodes["PlanePlus Image"].image == p.image
    p.width = 12
    near(max(v.co.x for v in ob.max_frozen_mesh.vertices) - min(v.co.x for v in ob.max_frozen_mesh.vertices), 12)
    p.opacity = 62
    near(ob.active_material.node_tree.nodes["PlanePlus Opacity"].outputs[0].default_value, .62)
    ob.max_show_frozen_gray = False
    assert tuple(ob.color) == color and ob.active_material == mat
    bpy.ops.max.object_cmd(cmd="UNFREEZE")
    assert not ob.hide_select and not ob.max_frozen
    assert tuple(ob.color) == color and ob.active_material == mat
    assert ob.data == mesh
    print("PASS freeze keeps image/color, gray toggle, repeated freeze, unfreeze restores", flush=True)

    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.object
    material = bpy.data.materials.new("Original object material")
    cube.data.materials.append(material)
    cube.material_slots[0].link = "OBJECT"
    cube.material_slots[0].material = material
    bpy.ops.object.duplicate(linked=True)
    linked = bpy.context.object
    linked.hide_select = True
    linked.select_set(False)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    original = tuple(cube.color)
    original_mesh = cube.data
    assert cube.max_show_frozen_gray
    bpy.ops.max.object_cmd(cmd="FREEZE")
    assert cube.hide_select
    near(cube.color[0], 0.55)
    assert cube.active_material != material and linked.active_material == material
    bpy.ops.max.unfreeze_by_name(obj=cube.name)
    assert not cube.hide_select and tuple(cube.color) == original and cube.data == original_mesh
    assert cube.material_slots[0].link == "OBJECT" and cube.active_material == material
    print("PASS ordinary object gray freeze and unfreeze by name", flush=True)

    # Preserve somebody else's unselectable object when unfreezing our objects.
    cube.hide_select = True
    freezing.freeze(cube, bpy.context.scene)
    bpy.ops.max.object_cmd(cmd="UNFREEZE")
    assert cube.hide_select
    cube.hide_select = False
    print("PASS shared mesh and object-linked materials remain intact", flush=True)
    cube["max_frozen_color"] = [0.2, 0.4, 0.6, 1]
    cube.color = (.55, .55, .55, 1)
    cube.hide_select = True
    bpy.ops.max.object_cmd(cmd="UNFREEZE")
    assert not cube.hide_select and "max_frozen_color" not in cube
    near(cube.color[0], .2)
    print("PASS legacy frozen objects remain recoverable", flush=True)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.max.object_cmd(cmd="CONVERT_POLY")
    assert not ob.max_prim.kind and ob.display_type == "TEXTURED"
    print("PASS unfreeze preserves unrelated locks and Editable Poly conversion restores surface", flush=True)

    # Native save/load must retain the original mesh behind a gray display copy.
    cube.hide_select = False
    for other in bpy.context.selected_objects:
        other.select_set(False)
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    bpy.ops.max.object_cmd(cmd="FREEZE")
    scene_path = os.path.join(folder, "frozen.blend")
    name, mesh_name = cube.name, original_mesh.name
    bpy.ops.wm.save_as_mainfile(filepath=scene_path)
    bpy.ops.wm.open_mainfile(filepath=scene_path)
    cube = bpy.data.objects[name]
    assert cube.max_frozen and cube.max_frozen_mesh.name == mesh_name
    bpy.ops.max.unfreeze_by_name(obj=name)
    assert not cube.hide_select and cube.data.name == mesh_name
    assert cube.active_material.name == "Original object material"
    print("PASS frozen state saves, reloads and restores original mesh/material", flush=True)
    bpy.ops.max.plane_plus()
    bpy.ops.max.plane_plus_image(filepath=path)
    plane_name = bpy.context.object.name

addon_utils.disable("notuodesk_3ds_maxxed", default_set=True)
assert not hasattr(bpy.types.Object, "max_plane_plus")
assert bpy.data.objects[plane_name].display_type == "TEXTURED", "Disabled add-on left an invisible wire plane"
addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
plane_plus._restore_draw_state()  # Background scripts do not advance GUI timers.
assert bpy.data.objects[plane_name].display_type == "WIRE"
print("PASS disable/re-enable lifecycle", flush=True)
print("PLANE_PLUS_TESTS_OK", flush=True)
