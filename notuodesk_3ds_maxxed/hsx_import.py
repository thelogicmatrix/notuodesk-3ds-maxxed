"""Import 3ds Max hotkey transformations into the add-on keyconfig."""

import json
import re
import xml.etree.ElementTree as ET

import bpy
import bmesh
from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector


def poly(op, settings=False):
    return ("Mesh", "max.hsx_settings" if settings else "max.edit_poly", {"op": op})


# Editable Polygon and Edit Poly expose the same actions in separate tables.
POLY_IDS = {
    "40013": poly("BEVEL"), "40017": poly("EXTRUDE"),
    "40041": poly("RING"), "40050": poly("TESSELLATE"),
    "40051": poly("TESSELLATE", True), "40054": poly("EXTRUDE", True),
    "40055": poly("CHAMFER"), "40056": poly("CHAMFER", True),
    "40060": poly("CAP"), "40062": poly("CONNECT", True),
    "40090": poly("BRIDGE"), "40091": poly("BRIDGE", True),
    "40117": poly("RELAX"), "41014": poly("RELAX"),
}
CONVERT = ("3D View", "max.object_cmd", {"cmd": "CONVERT_POLY"})
ACTION_IDS = {
    "0-40264": ("3D View", "max.expert_mode", {}),
    "0-40373": ("Window", "export_scene.fbx", {"use_selection": True}),
    "0-278": ("3D View", "wm.tool_set_by_id", {"name": "builtin.scale"}),
    "951718758-40040": poly("CHAMFER"),
    "951718758-40017": poly("EXTRUDE"),
}
MACROS = {
    "epoly_connect2": poly("CONNECT", True), "relaxselection": poly("RELAX"),
    "epoly_select_ring": poly("RING"), "convert_to_poly": CONVERT,
    "editpolymod": ("3D View", "max.add_modifier", {"kind": "EDIT_POLY|Edit Poly"}),
    "relaxctrlshift": poly("RELAX"), "inset": poly("INSET"), "mepoly": CONVERT,
    "fastbridge": poly("BRIDGE"), "epoly_fextrude": poly("EXTRUDE"),
    "physicalcamera_createfromview": ("Object Mode", "max.camera_from_view", {}),
    "rapidqcap": ("Mesh", "max.quad_cap", {}),
    "fastedgeloopregularizer": ("Mesh", "max.loop_regularize", {}),
}
DESCRIPTIONS = {
    "convert to editable polygon": CONVERT, "convert to editable poly": CONVERT,
    "expert mode toggle": ACTION_IDS["0-40264"], "export selected": ACTION_IDS["0-40373"],
    "select edge ring": poly("RING"), "select sub-object ring": poly("RING"),
    "relax selection": poly("RELAX"), "paint deform relax": poly("RELAX"),
    "relax: hard (ctrlshift)": poly("RELAX"), "edit poly modifier": MACROS["editpolymod"],
    "connect edge settings": poly("CONNECT", True),
    "connect (with dialog) (poly)": poly("CONNECT", True),
}
for _name, _op in (("Bridge", "BRIDGE"), ("Cap", "CAP"), ("Inset", "INSET"),
                   ("Relax", "RELAX"), ("Chamfer", "CHAMFER"), ("Extrude", "EXTRUDE"),
                   ("Bevel", "BEVEL"), ("Connect", "CONNECT"), ("Tessellate", "TESSELLATE")):
    DESCRIPTIONS[_name.lower()] = poly(_op)
    DESCRIPTIONS[_name.lower() + " mode"] = poly(_op)
    if _op in {"BRIDGE", "CHAMFER", "EXTRUDE", "CONNECT", "TESSELLATE"}:
        DESCRIPTIONS[_name.lower() + " settings"] = poly(_op, True)
for _name in ("fastbridge", "rapidqcap", "fastedgeloopregularizer", "mepoly"):
    DESCRIPTIONS[_name] = MACROS[_name]


def operator_exists(idname):
    try:
        namespace, name = idname.split(".")
        getattr(getattr(bpy.ops, namespace), name).get_rna_type()
        return True
    except (AttributeError, KeyError, RuntimeError):
        return False


def resolve_action(entry):
    action_id = entry["id"]
    target = ACTION_IDS.get(action_id)
    table, _, action = action_id.partition("-")
    if table in {"1250838234", "369982487"}:
        target = POLY_IDS.get(action)
    elif table == "647394":
        target = MACROS.get(action.split("`", 1)[0].lower())
    target = target or DESCRIPTIONS.get(entry["description"].strip().lower())
    if target and operator_exists(target[1]):
        return target
    return None


def parse_shortcut(shortcut):
    # Keep the plus sign when it is the numpad key itself.
    text = shortcut.strip()
    modifiers = set()
    while "+" in text:
        first, rest = text.split("+", 1)
        if first.strip().lower() not in {"ctrl", "control", "alt", "shift"}:
            break
        modifiers.add(first.strip().lower())
        text = rest.strip()
    key = re.sub(r"[\s_]", "", text).upper()
    digits = ("ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE")
    aliases = {"DELETE": "DEL", "DEL": "DEL", "BACKSPACE": "BACK_SPACE", "PAGEUP": "PAGE_UP",
               "PGUP": "PAGE_UP", "PAGEDOWN": "PAGE_DOWN", "PGDN": "PAGE_DOWN",
               "PGDOWN": "PAGE_DOWN", "ESC": "ESC", "ESCAPE": "ESC",
               "RETURN": "RET", "ENTER": "RET", "SPACE": "SPACE", "SPACEBAR": "SPACE",
               "HOME": "HOME", "END": "END", "INSERT": "INSERT", "TAB": "TAB"}
    for direction in ("LEFT", "RIGHT", "UP", "DOWN"):
        aliases[direction] = aliases[direction + "ARROW"] = direction + "_ARROW"
    if key.startswith(("NUMPAD", "NUM")):
        suffix = key[6:] if key.startswith("NUMPAD") else key[3:]
        num = {"+": "PLUS", "PLUS": "PLUS", "ADD": "PLUS", "-": "MINUS",
               "MINUS": "MINUS", "SUBTRACT": "MINUS", "*": "ASTERIX", "MULTIPLY": "ASTERIX",
               "/": "SLASH", "DIVIDE": "SLASH", ".": "PERIOD", "DECIMAL": "PERIOD",
               "PERIOD": "PERIOD", "ENTER": "ENTER", "RETURN": "ENTER"}
        if suffix in "0123456789" and len(suffix) == 1:
            key = "NUMPAD_" + suffix
        elif suffix in num:
            key = "NUMPAD_" + num[suffix]
        else:
            raise ValueError(f"Unsupported shortcut: {shortcut}")
    elif len(key) == 1 and key in "0123456789":
        key = digits[int(key)]
    elif key in aliases:
        key = aliases[key]
    elif not (len(key) == 1 and "A" <= key <= "Z" or re.fullmatch(r"F([1-9]|1[0-9]|2[0-4])", key)):
        raise ValueError(f"Unsupported shortcut: {shortcut}")
    return key, bool(modifiers & {"ctrl", "control"}), "shift" in modifiers, "alt" in modifiers


def parse_hsx(source):
    root = ET.fromstring(source)
    if root.tag != "MaxHotkeyTransformations":
        raise ValueError("Expected MaxHotkeyTransformations XML")
    entries = []
    for node in root.iter():
        if node.tag not in {"Assign_Hotkey", "Unassign_Hotkey"}:
            continue
        if not all(name in node.attrib for name in ("Shortcut", "Description", "Id")):
            raise ValueError(f"{node.tag} needs Shortcut, Description and Id")
        entries.append({"kind": node.tag, "shortcut": node.attrib["Shortcut"],
                        "description": node.attrib["Description"], "id": node.attrib["Id"]})
    return entries


def build_bindings(entries):
    bindings = {}
    unmapped = []
    for entry in entries:
        target = resolve_action(entry)
        try:
            shortcut = parse_shortcut(entry["shortcut"])
        except ValueError:
            shortcut = None
        if entry["kind"] == "Unassign_Hotkey":
            if target and shortcut:
                slot = (target[0], shortcut)
                if slot in bindings and bindings[slot][1:] == target[1:]:
                    del bindings[slot]
            continue
        if target is None or shortcut is None:
            unmapped.append(entry)
            continue
        bindings[(target[0], shortcut)] = target
    return [(name, shortcut, target[1], target[2]) for (name, shortcut), target in bindings.items()], unmapped


def load_entries(prefs=None):
    if prefs is None:
        from . import get_prefs
        prefs = get_prefs()
    try:
        return json.loads(prefs.imported_hsx) if prefs and prefs.imported_hsx else []
    except (ValueError, AttributeError):
        return []


def store_entries(prefs, entries):
    prefs.imported_hsx = json.dumps(entries)
    bpy.context.preferences.is_dirty = True


def skip_default(name, item, entries):
    shortcut = (item[1], item[3], item[4], item[5])
    # A transformation frees its key before assigning it, including across modes.
    for entry in entries:
        try:
            if parse_shortcut(entry["shortcut"]) != shortcut:
                continue
        except ValueError:
            continue
        if entry["kind"] == "Unassign_Hotkey" or resolve_action(entry):
            return True
    return False


def register_keymaps(kc, registered, entries):
    bindings, _ = build_bindings(entries)
    for name, shortcut, idname, props in bindings:
        names = ("3D View", "Object Mode", "Mesh", "Curve") if name == "3D View" else (name,)
        for km_name in names:
            km = kc.keymaps.new(name=km_name, space_type="VIEW_3D" if km_name == "3D View" else "EMPTY", region_type="WINDOW")
            key, ctrl, shift, alt = shortcut
            kmi = km.keymap_items.new(idname, key, "PRESS", ctrl=ctrl, shift=shift, alt=alt, head=True)
            for prop, value in props.items():
                setattr(kmi.properties, prop, value)
            registered.append((km, kmi))


def refresh_keymaps():
    from . import get_prefs, keymap
    keymap.unregister_keymaps()
    prefs = get_prefs()
    if prefs and prefs.use_keymap:
        keymap.register_keymaps()


def draw_preferences(layout, prefs):
    box = layout.box()
    row = box.row()
    row.operator("max.import_hsx", text="Import 3ds Max Hotkeys (.hsx)...", icon="IMPORT")
    row.operator("max.clear_hsx_hotkeys", text="Clear Imported Hotkeys")
    entries = load_entries(prefs)
    _, unmapped = build_bindings(entries)
    box.label(text=f"Imported entries: {len(entries)}. Unmapped assignments: {len(unmapped)}")
    for entry in entries:
        row = box.row()
        prefix = "Unassign" if entry["kind"] == "Unassign_Hotkey" else "Assign"
        row.label(text=f"{prefix} {entry['shortcut']}")
        row.label(text=entry["description"], icon="ERROR" if entry in unmapped else "NONE")


class MAX_OT_import_hsx(bpy.types.Operator, ImportHelper):
    """Import a 3ds Max hotkey file"""
    bl_idname = "max.import_hsx"
    bl_label = "Import 3ds Max Hotkeys (.hsx)"
    filename_ext = ".hsx"
    filter_glob: StringProperty(default="*.hsx", options={"HIDDEN"})

    def execute(self, context):
        from . import get_prefs
        try:
            with open(self.filepath, "rb") as handle:
                entries = parse_hsx(handle.read())
        except (OSError, ET.ParseError, ValueError) as exc:
            self.report({"ERROR"}, f"Could not import hotkeys: {exc}")
            return {"CANCELLED"}
        prefs = get_prefs()
        if prefs is None:
            self.report({"ERROR"}, "Add-on preferences are unavailable")
            return {"CANCELLED"}
        store_entries(prefs, entries)
        refresh_keymaps()
        _, unmapped = build_bindings(entries)
        count = sum(e["kind"] == "Assign_Hotkey" for e in entries) - len(unmapped)
        summary = f"Mapped {count} assignments. Unmapped: {len(unmapped)}"
        self.report({"INFO"}, summary)
        for entry in unmapped:
            self.report({"INFO"}, f"Unmapped: {entry['description']} ({entry['id']}, {entry['shortcut']})")
        if not bpy.app.background:
            def draw(menu, context):
                menu.layout.label(text=summary)
                for entry in unmapped:
                    menu.layout.label(text=f"Unmapped: {entry['description']} ({entry['shortcut']})")
            context.window_manager.popup_menu(draw, title="3ds Max Hotkeys", icon="INFO")
        return {"FINISHED"}


class MAX_OT_clear_hsx_hotkeys(bpy.types.Operator):
    """Remove imported hotkeys and restore the add-on defaults"""
    bl_idname = "max.clear_hsx_hotkeys"
    bl_label = "Clear Imported Hotkeys"

    def execute(self, context):
        from . import get_prefs
        store_entries(get_prefs(), [])
        refresh_keymaps()
        return {"FINISHED"}


def extrude_surface_normals(context, amount):
    """Extrude along the adjacent surface normals, captured before topology changes."""
    meshes = []
    vertex_mode = context.tool_settings.mesh_select_mode[0]
    for obj in context.objects_in_mode_unique_data:
        bm = bmesh.from_edit_mesh(obj.data)
        bm.normal_update()
        selected = [item for item in (bm.verts if vertex_mode else bm.edges) if item.select and not item.hide]
        if not selected:
            continue
        vertices = set(selected) if vertex_mode else {v for e in selected for v in e.verts}
        directions = {}
        for vert in vertices:
            faces = set(vert.link_faces) if vertex_mode else {f for e in vert.link_edges if e.select and not e.hide for f in e.link_faces}
            normal = sum((f.normal for f in faces), Vector())
            if normal.length_squared < 1e-12:
                return False
            directions[vert] = normal.normalized()
        meshes.append((obj, bm, selected, directions))
    for obj, bm, selected, directions in meshes:
        if vertex_mode:
            result = bmesh.ops.extrude_vert_indiv(bm, verts=selected)
            new_vertices = result["verts"]
        else:
            result = bmesh.ops.extrude_edge_only(bm, edges=selected)
            new_vertices = [v for v in result["geom"] if isinstance(v, bmesh.types.BMVert)]
        for vert in new_vertices:
            source = next(e.other_vert(vert) for e in vert.link_edges if e.other_vert(vert) in directions)
            vert.co += directions[source] * amount
        for seq in (bm.faces, bm.edges, bm.verts):
            for item in seq:
                item.select_set(False)
        if vertex_mode:
            for vert in new_vertices:
                vert.select_set(True)
        else:
            top = set(new_vertices)
            for edge in result["geom"]:
                if isinstance(edge, bmesh.types.BMEdge) and all(v in top for v in edge.verts):
                    edge.select_set(True)
        bm.select_flush_mode()
        bm.normal_update()
        bmesh.update_edit_mesh(obj.data)
    return bool(meshes)


class MAX_OT_hsx_settings(bpy.types.Operator):
    """Open settings before applying an imported Editable Poly operation"""
    bl_idname = "max.hsx_settings"
    bl_label = "Editable Poly Settings"
    bl_options = {"REGISTER", "UNDO"}

    op: EnumProperty(items=[(key, key.title(), "") for key in ("CHAMFER", "EXTRUDE", "CONNECT", "BRIDGE", "TESSELLATE")])
    amount: FloatProperty(name="Amount", default=0.1)
    segments: IntProperty(name="Segments", default=1, min=1, max=1000)
    tessellate_type: EnumProperty(name="Type", items=[("EDGE", "Edge", ""), ("FACE", "Face", "")], default="EDGE")
    tension: FloatProperty(name="Edge Tension", default=1, min=0, max=1)

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def invoke(self, context, event):
        self.set_defaults()
        return context.window_manager.invoke_props_dialog(self)

    def set_defaults(self):
        if self.op == "CHAMFER" and not self.properties.is_property_set("amount"):
            self.amount = 1.0

    def draw(self, context):
        self.layout.label(text=self.op.title() + " Settings")
        if self.op in {"CHAMFER", "EXTRUDE"}:
            self.layout.prop(self, "amount", text="Extrusion Height" if self.op == "EXTRUDE" else "Amount")
        if self.op in {"CHAMFER", "CONNECT", "BRIDGE"}:
            self.layout.prop(self, "segments")
        if self.op == "TESSELLATE":
            self.layout.prop(self, "tessellate_type")
            if self.tessellate_type == "EDGE":
                self.layout.prop(self, "tension")

    def execute(self, context):
        self.set_defaults()
        try:
            if self.op == "CHAMFER":
                return bpy.ops.mesh.bevel(offset=self.amount, segments=self.segments,
                                          affect="VERTICES" if context.tool_settings.mesh_select_mode[0] else "EDGES")
            if self.op == "EXTRUDE":
                mode = context.tool_settings.mesh_select_mode
                if mode[2]:
                    return bpy.ops.mesh.extrude_region_shrink_fatten(TRANSFORM_OT_shrink_fatten={"value": self.amount})
                if extrude_surface_normals(context, self.amount):
                    return {"FINISHED"}
                self.report({"WARNING"}, "Select edges or vertices with a nonzero adjacent surface normal")
                return {"CANCELLED"}
            if self.op == "BRIDGE":
                return bpy.ops.mesh.bridge_edge_loops(number_cuts=self.segments - 1)
            if self.op == "CONNECT" and context.tool_settings.mesh_select_mode[0]:
                return bpy.ops.mesh.vert_connect_path()
            if self.op == "CONNECT":
                return bpy.ops.mesh.subdivide(number_cuts=self.segments)
            if self.tessellate_type == "FACE":
                return bpy.ops.mesh.poke()
            return bpy.ops.mesh.subdivide(number_cuts=1, smoothness=1 - self.tension)
        except RuntimeError as exc:
            self.report({"WARNING"}, str(exc))
            return {"CANCELLED"}


classes = (MAX_OT_import_hsx, MAX_OT_clear_hsx_hotkeys, MAX_OT_hsx_settings)
