"""3ds Max 2026 Editable Poly Command Panel layout."""

import bpy
import bmesh

from . import editable_poly as ep
from .operators import current_level

LEVEL_ACTIONS = {
    1: ("REMOVE", "BREAK", "EXTRUDE", "WELD", "CHAMFER", "TARGET_WELD", "CONNECT",
        "DELETE_ISOLATED", "REMOVE_UNUSED_MAP"),
    2: ("INSERT_VERTEX", "REMOVE", "SPLIT", "EXTRUDE", "WELD", "CHAMFER", "TARGET_WELD",
        "BRIDGE", "CONNECT", "CREATE_SHAPE"),
    3: ("EXTRUDE", "INSERT_VERTEX", "CHAMFER", "CAP", "TARGET_WELD", "BRIDGE", "CONNECT", "CREATE_SHAPE"),
    4: ("INSERT_VERTEX", "EXTRUDE", "OUTLINE", "BEVEL", "INSET", "BRIDGE", "FLIP",
        "HINGE", "SPLINE_EXTRUDE", "EDIT_TRIANGULATION", "RETRIANGULATE", "TURN"),
    5: ("INSERT_VERTEX", "FLIP", "EDIT_TRIANGULATION", "RETRIANGULATE", "TURN"),
}


def icon(name, fallback):
    try:
        from . import max_icons
    except ImportError:
        return {"icon": fallback}
    return max_icons.ui(name, fallback)


def unavailable(layout, text, reason):
    row = layout.row(align=True)
    row.enabled = False
    row.operator("max.poly_unavailable", text=text).reason = reason


def button(layout, action, text=None):
    from .ui_panel import EP_LABELS
    label = text or EP_LABELS[action]
    row = layout.row(align=True)
    if action in ep.UNSUPPORTED:
        row.enabled = False
        row.operator("max.poly_unavailable", text=label).reason = ep.UNSUPPORTED[action]
    else:
        row.operator_context = "INVOKE_DEFAULT" if action in ep.poly_caddies.SHIFT_ACTIONS else "EXEC_DEFAULT"
        if action == "TARGET_WELD":
            from .target_weld import is_active
            row.operator("max.edit_poly", text=label, depress=is_active(bpy.context)).op = action
        else:
            row.operator("max.edit_poly", text=label).op = action
    if action in ep.CADDIES:
        sub = row.row(align=True)
        sub.operator_context = "INVOKE_DEFAULT"
        sub.operator("max.poly_settings", text="", **icon("settings", "PREFERENCES")).action = action


def grid(layout, actions):
    flow = layout.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
    for action in actions:
        button(flow, action)


def radios(layout, data, key):
    row = layout.row(align=True)
    row.emboss = "NONE"
    for item in data.bl_rna.properties[key].enum_items:
        row.prop_enum(data, key, item.identifier, text=item.name,
                      icon="RADIOBUT_ON" if getattr(data, key) == item.identifier else "RADIOBUT_OFF")


def spinner(layout, data, key):
    row = layout.row(align=True)
    row.label(text=data.bl_rna.properties[key].name + ":")
    row.prop(data, key, text="")


def selection(layout, context):
    from .ui_panel import SUBLEVEL_ICONS, SUBLEVEL_NAMES
    level = current_level(context)
    p = context.active_object.max_poly
    row = layout.row(align=True)
    for i in range(1, 6):
        row.operator("max.subobject", text="", **icon(SUBLEVEL_NAMES[i], SUBLEVEL_ICONS[i]), depress=(level == i)).level = i
    col = layout.column(align=True)
    col.enabled = level > 0
    row = col.row(align=True)
    row.enabled = False
    row.prop(p, "by_vertex")
    row.prop(p, "ignore_backfacing")
    row = col.row(align=True)
    row.enabled = level in (4, 5)
    row.prop(p, "by_angle")
    row.prop(p, "angle", text="")
    if p.by_angle:
        button(col, "SELECT_ANGLE", "Select By Angle")
    row = col.row(align=True)
    button(row, "SHRINK")
    button(row, "GROW")
    row = col.row(align=True)
    row.enabled = level in (2, 3)
    for action in ("RING", "LOOP"):
        sub = row.row(align=True)
        button(sub, action)
        arrows = sub.column(align=True)
        for suffix, fallback in (("UP", "TRIA_UP"), ("DOWN", "TRIA_DOWN")):
            arrows.operator("max.edit_poly", text="", **icon(suffix.lower(), fallback)).op = action + "_SHIFT_" + suffix
    col.label(text="Preview Selection")
    row = col.row(align=True)
    row.enabled = False
    radios(row, p, "preview")
    if level == 3:
        button(col, "OPEN_EDGES")
    if level == 0:
        text = "Whole Object Selected"
    else:
        bm = bmesh.from_edit_mesh(context.active_object.data)
        seq = bm.verts if level == 1 else bm.edges if level in (2, 3) else bm.faces
        count = sum(1 for item in seq if item.select)
        if level == 5:
            # Count connected selected elements, not individual polygons.
            remaining = {f for f in bm.faces if f.select}
            count = 0
            while remaining:
                todo = [remaining.pop()]
                count += 1
                while todo:
                    for edge in todo.pop().edges:
                        for face in edge.link_faces:
                            if face in remaining:
                                remaining.remove(face)
                                todo.append(face)
        noun = {1: "Vertices", 2: "Edges", 3: "Edges", 4: "Polygons", 5: "Elements"}[level]
        text = f"{count} {noun} Selected"
    layout.label(text=text)


def soft_selection(layout, context):
    p = context.active_object.max_poly
    layout.enabled = current_level(context) > 0
    layout.prop(p, "soft")
    col = layout.column(align=True)
    col.enabled = p.soft
    row = col.row(align=True)
    row.prop(p, "edge_distance")
    sub = row.row(align=True)
    sub.enabled = False
    sub.prop(p, "edge_steps", text="")
    row = col.row(align=True)
    row.enabled = False
    row.prop(p, "affect_backfacing")
    spinner(col, p, "falloff")
    row = col.row(align=True)
    row.enabled = False
    row.prop(p, "pinch")
    row.prop(p, "bubble")
    col.prop(p, "falloff_curve")
    row = col.row(align=True)
    row.enabled = False
    row.prop(p, "shaded_faces")


def edit_level(layout, context):
    level = current_level(context)
    actions = LEVEL_ACTIONS[level]
    row = None
    column = 0
    for action in actions:
        label = "Remove Isolated Vertices" if level == 1 and action == "DELETE_ISOLATED" else None
        if action in {"DELETE_ISOLATED", "REMOVE_UNUSED_MAP", "CREATE_SHAPE", "SPLINE_EXTRUDE", "EDIT_TRIANGULATION"}:
            button(layout, action, label)
            row = None
            column = 0
            continue
        if action == "CAP" and hasattr(bpy.types, "MAX_OT_quad_cap"):
            row = layout.row(align=True)
            button(row, action)
            row.operator("max.quad_cap", text="Quad Cap")
            row = None
            column = 0
            continue
        if row is None:
            row = layout.row(align=True)
        button(row, action, label)
        column += 1
        if column == 2:
            row = None
            column = 0
    if level == 2 and hasattr(bpy.types, "MAX_OT_loop_regularize"):
        layout.operator("max.loop_regularize", text="Loop Regularizer")
    if level in (1, 2, 3):
        p = context.active_object.max_poly
        row = layout.row(align=True)
        row.enabled = False
        row.prop(p, "weight")
        row = layout.row(align=True)
        row.prop(p, "crease")
        row.operator("max.poly_weight", text="Set").crease = True
    if level in (2, 3):
        if level == 2:
            row = layout.row(align=True)
            row.enabled = False
            spinner(row, context.active_object.max_poly, "depth")
            row = layout.row(align=True)
            unavailable(row, "Hard", "Max's automatic smoothing-group reassignment for hard edges is not implemented")
            unavailable(row, "Smooth", "Max's automatic smoothing-group reassignment for smooth edges is not implemented")
            row = layout.row(align=True)
            row.enabled = False
            row.prop(context.active_object.max_poly, "display_hard_edges")
        grid(layout, ("EDIT_TRIANGULATION", "TURN"))


def geometry(layout, context):
    level = current_level(context)
    layout.operator("screen.repeat_last", text="Repeat Last")
    layout.label(text="Constraints")
    row = layout.row(align=True)
    radios(row, context.active_object.max_poly, "constraints")
    row = layout.row(align=True)
    row.prop(context.tool_settings, "use_transform_correct_face_attributes", text="Preserve UVs")
    unavailable(row, "...", "Blender cannot choose preserved map channels per transform")
    col = layout.column(align=True)
    col.enabled = level > 0
    grid(col, ("CREATE", "COLLAPSE"))
    row = layout.row(align=True)
    if level:
        button(row, "ATTACH")
    else:
        row.operator("max.object_cmd", text="Attach").cmd = "ATTACH"
    row.operator_context = "INVOKE_DEFAULT"
    row.operator("max.poly_attach_list", text="", **icon("select_by_name", "PRESET"))
    sub = row.row(align=True)
    sub.enabled = level > 0
    button(sub, "DETACH")
    row = layout.row(align=True)
    row.enabled = level > 0
    button(row, "SLICE_PLANE")
    row.prop(ep.settings(context, "SLICE_PLANE"), "split")
    row = layout.row(align=True)
    row.enabled = level > 0
    button(row, "SLICE")
    button(row, "RESET_PLANE")
    row = layout.row(align=True)
    for action in ("QUICK_SLICE", "CUT"):
        sub = row.row(align=True)
        sub.operator_context = "INVOKE_DEFAULT"
        sub.operator("max.edit_poly", text="QuickSlice" if action == "QUICK_SLICE" else "Cut").op = action
    col = layout.column(align=True)
    grid(col, ("MSMOOTH", "TESSELLATE"))
    button(col, "MAKE_PLANAR")
    row = col.row(align=True)
    for axis in "XYZ":
        button(row, "PLANAR_" + axis)
    grid(col, ("VIEW_ALIGN", "GRID_ALIGN"))
    button(col, "RELAX")
    hide = layout.column(align=True)
    hide.enabled = level in (1, 4, 5)
    grid(hide, ("HIDE_SEL", "UNHIDE", "HIDE_UNSEL"))
    col = layout.column(align=True)
    col.enabled = level > 0
    col.label(text="Named Selections")
    grid(col, ("COPY_SELECTION", "PASTE_SELECTION"))
    if level in (2, 3, 4, 5):
        layout.prop(context.active_object.max_poly, "delete_isolated")
    row = layout.row(align=True)
    row.enabled = False
    row.prop(context.active_object.max_poly, "full_interactivity")


def material_ids(layout, context):
    p = context.active_object.max_poly
    for prop, action, text in (("material_id", "SET", "Set ID"), ("select_id", "SELECT", "Select ID")):
        row = layout.row(align=True)
        row.operator("max.poly_material", text=text).action = action
        row.prop(p, prop, text="")
    layout.prop(p, "clear_selection")
    layout.prop(p, "material_name", text="")
    layout.operator("max.poly_material", text="Select by Name").action = "NAME"


def smoothing_groups(layout, context):
    bm = bmesh.from_edit_mesh(context.active_object.data)
    layer = bm.faces.layers.int.get(ep.SG_ATTRIBUTE)
    selected = [f for f in bm.faces if f.select]
    g = layout.grid_flow(row_major=True, columns=8, even_columns=True, align=True)
    for group in range(1, 33):
        on = bool(layer and selected and all(f[layer] & (1 << (group - 1)) for f in selected))
        op = g.operator("max.poly_smoothing", text=str(group), depress=on)
        op.action = "TOGGLE"
        op.group = group
    row = layout.row(align=True)
    row.operator("max.poly_smoothing", text="Select By SG").action = "SELECT"
    row.prop(context.active_object.max_poly, "sg_select", text="")
    layout.operator("max.poly_smoothing", text="Clear All").action = "CLEAR"
    row = layout.row(align=True)
    row.operator("max.poly_smoothing", text="Auto Smooth").action = "AUTO"
    row.prop(context.active_object.max_poly, "auto_angle", text="")
    layout.prop(context.active_object.max_poly, "sg_clear_selection")


def subdivision(layout, context):
    p = context.active_object.max_poly
    for key in ("smooth_result", "nurms", "isoline", "iterations"):
        layout.prop(p, key)
    row = layout.row(align=True)
    row.enabled = False
    row.prop(p, "smoothness")


def vertex_colors(layout, context):
    layout.enabled = False
    p = context.active_object.max_poly
    for key in ("vertex_color", "illumination", "alpha"):
        spinner(layout, p, key)


def displacement(layout, context):
    layout.enabled = False
    p = context.active_object.max_poly
    layout.prop(p, "use_displacement")
    layout.prop(p, "split_mesh")


def paint_deformation(layout, context):
    layout.enabled = False
    p = context.active_object.max_poly
    radios(layout, p, "paint_mode")
    for key in ("paint_value", "brush_size", "brush_strength"):
        spinner(layout, p, key)
    layout.prop(p, "paint_direction")


def install(rollout, when, is_poly):
    rollout("Soft Selection", {"MODIFY"}, 5, closed=True)(when(is_poly)(soft_selection))
    for level, label in ((1, "Edit Vertices"), (2, "Edit Edges"), (3, "Edit Borders"), (4, "Edit Polygons"), (5, "Edit Elements")):
        def draw(layout, context):
            edit_level(layout, context)
        draw.__name__ = "poly_level_" + str(level)
        rollout(label, {"MODIFY"}, 6)(when(lambda c, n=level: is_poly(c) and current_level(c) == n)(draw))
    for label, fn in (("Polygon: Material IDs", material_ids), ("Polygon: Smoothing Groups", smoothing_groups), ("Polygon: Vertex Colors", vertex_colors)):
        rollout(label, {"MODIFY"}, 8, closed=True)(when(lambda c: is_poly(c) and current_level(c) in (4, 5))(fn))
    rollout("Subdivision Surface", {"MODIFY"}, 8, closed=True)(when(is_poly)(subdivision))
    rollout("Subdivision Displacement", {"MODIFY"}, 9, closed=True)(when(is_poly)(displacement))
    rollout("Paint Deformation", {"MODIFY"}, 10, closed=True)(when(is_poly)(paint_deformation))
