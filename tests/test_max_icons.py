"""Run in the isolated profile: blender -b --factory-startup --python tests/test_max_icons.py.

Catches missing artwork, dead custom icon IDs, broken fallbacks, and preview leaks.
"""
import ast
from pathlib import Path
import struct
import sys
import tempfile

import addon_utils
import bpy
import bpy.utils.previews

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PACKAGE = ROOT / "notuodesk_3ds_maxxed"


def run():
    # Blender's diagnostic registry catches leaked collections, even empty ones.
    initial_collections = set(bpy.utils.previews._uuid_open)
    addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
    import notuodesk_3ds_maxxed as addon
    assert hasattr(addon, "max_icons"), "Custom preview loader is missing"
    icons = addon.max_icons
    names = {p.stem for p in (PACKAGE / "icons" / "src").glob("*.svg")}
    required = set("create modify hierarchy motion display utilities geometry shapes lights cameras helpers "
                   "vertex edge border polygon element editable_poly pin_stack show_end_result make_unique "
                   "remove_modifier configure_modifier_sets bulb_on bulb_off undo redo link unlink "
                   "bind_space_warp selection_filter select_object select_by_name region_rect region_circle "
                   "region_fence window_crossing move rotate scale reference_coords pivot snap_2d snap_25d "
                   "snap_3d angle_snap percent_snap spinner_snap named_selection_sets mirror align "
                   "scene_explorer layer_explorer ribbon curve_editor schematic_view material_editor "
                   "render_setup rendered_frame render_production".split())
    assert required <= names, f"Missing required icons: {sorted(required - names)}"
    referenced = set()
    for source in PACKAGE.glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "max_icons"
                    and node.func.attr in {"icon", "ui"} and node.args
                    and isinstance(node.args[0], ast.Constant)):
                referenced.add(node.args[0].value)
    referenced.update(key.lower() for key, *_ in addon.ui_panel.TABS + addon.ui_panel.CREATE_CATS)
    referenced.update(addon.ui_panel.SUBLEVEL_NAMES.values())
    referenced.update(key.lower() for key in addon.prims.PRIMITIVES)
    referenced.update(key.lower() for key, *_ in addon.create.SHAPES + addon.create.LIGHTS)
    referenced.update({"move", "rotate", "scale", "bulb_on", "bulb_off", "snap_3d", "snap_off"})
    assert referenced <= names, f"Referenced icons without SVG: {referenced - names}"
    # Check every UILayout call that receives the loader's keyword dictionary.
    for source in PACKAGE.glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if any(kw.arg is None and isinstance(kw.value, ast.Call)
                       and isinstance(kw.value.func, ast.Attribute)
                       and isinstance(kw.value.func.value, ast.Name)
                       and kw.value.func.value.id == "max_icons" for kw in node.keywords):
                    fn = bpy.types.UILayout.bl_rna.functions.get(node.func.attr)
                    assert fn is not None and "icon_value" in fn.parameters, (source.name, node.lineno)
    for name in names:
        for suffix, size in (("", 32), ("@2x", 64)):
            png = PACKAGE / "icons" / f"{name}{suffix}.png"
            assert png.is_file(), f"Missing PNG: {png.name}"
            header = png.read_bytes()[:24]
            assert header[:8] == b"\x89PNG\r\n\x1a\n"
            assert struct.unpack(">II", header[16:24]) == (size, size), png.name
        preview = icons._collection.get(name)
        assert preview is not None and tuple(preview.image_size) == (64, 64), f"Preview did not load: {name}"
        assert len(preview.image_pixels_float) == 64 * 64 * 4
        assert any(list(preview.icon_pixels_float)[3::4]), f"Transparent icon thumbnail: {name}"
        if not bpy.app.background:
            assert icons.icon(name) > 0, f"No GUI icon ID: {name}"
    print(f"ICONS artwork: {len(names)} original SVGs, 32/64px PNGs, all previews loaded", flush=True)
    print(f"ICONS references: {len(referenced)} literal and dynamic UI names resolved", flush=True)
    assert icons.ui("missing-test-icon", "ADD") == {"icon": "ADD"}
    expected = {"icon_value": icons.icon("create")} if icons.icon("create") else {"icon": "ADD"}
    assert icons.ui("create", "ADD") == expected
    tab_item = icons.enum_items(addon.ui_panel.TABS)[0]
    assert tab_item[:3] == ("CREATE", "Create", "Create") and tab_item[4] == 0
    assert tab_item[3] == (icons.icon("create") or "ADD")
    # Simulate one missing PNG without mutating the shipped assets.
    preview = icons._collection.pop("create")
    assert icons.icon("create") == 0
    assert icons.ui("create", "ADD") == {"icon": "ADD"}
    icons._collection["create"] = preview
    print("ICONS fallback: missing artwork uses the original Blender icon", flush=True)
    first = icons._collection
    assert len(set(bpy.utils.previews._uuid_open) - initial_collections) == 1
    for _ in range(3):
        icons.register()
        assert icons._collection is first, "Repeated register allocated another collection"
    for cycle in range(3):
        addon_utils.disable("notuodesk_3ds_maxxed", default_set=True)
        assert icons._collection is None
        assert len(first) == 0, "Previous preview collection was not freed"
        assert set(bpy.utils.previews._uuid_open) == initial_collections
        assert icons.icon("create") == 0
        addon_utils.enable("notuodesk_3ds_maxxed", default_set=True)
        first = icons._collection
        assert len(first) == len(names)
    addon_utils.disable("notuodesk_3ds_maxxed", default_set=True)
    assert icons._collection is None and len(first) == 0
    assert set(bpy.utils.previews._uuid_open) == initial_collections
    original_directory = icons.DIRECTORY
    with tempfile.TemporaryDirectory(prefix="maxxed-icons-") as folder:
        fixture = Path(folder)
        (fixture / "src").mkdir()
        (fixture / "src" / "create.svg").write_text("<svg/>")
        (fixture / "src" / "missing.svg").write_text("<svg/>")
        (fixture / "create.png").write_bytes((original_directory / "create.png").read_bytes())
        icons.DIRECTORY = fixture
        try:
            icons.register()
            assert set(icons._collection) == {"create"}
            assert tuple(icons._collection["create"].image_size) == (32, 32)
            assert icons.ui("missing", "ADD") == {"icon": "ADD"}
        finally:
            icons.unregister()
            icons.DIRECTORY = original_directory
    assert set(bpy.utils.previews._uuid_open) == initial_collections
    print("ICONS files: missing 64px uses 32px, missing PNG uses Blender fallback", flush=True)
    print("ICONS lifecycle: 3 idempotent loads, 3 add-on re-register cycles, final collection freed", flush=True)
    print("ICONS PASS", flush=True)


if __name__ == "__main__":
    run()
