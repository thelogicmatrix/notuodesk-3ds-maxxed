"""Editable Poly rollouts and persistent operation settings, using native mesh tools."""

import math

import bpy
import bmesh
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       IntProperty, PointerProperty, StringProperty)
from bpy.types import Operator, PropertyGroup
from mathutils import Vector
from . import poly_constraints

from . import poly_caddies

SG_ATTRIBUTE = "max_smoothing_group"
SMOOTH_BACKUP = "max_poly_original_smooth"
OBJECT_ACTIONS = {"MSMOOTH", "TESSELLATE", "MAKE_PLANAR", "PLANAR_X", "PLANAR_Y", "PLANAR_Z", "VIEW_ALIGN", "GRID_ALIGN", "RELAX", "ATTACH", "CUT", "QUICK_SLICE"}


def is_nurms(mod):
    return mod is not None and mod.type == "SUBSURF" and mod.name.startswith("NURMS Subdivision")

EXTRA_OPS = [
    ("INSERT_VERTEX", "Insert Vertex", "Subdivide selected edges or poke selected faces"),
    ("SPLIT", "Split", "Split selected edges from adjacent faces"),
    ("DELETE_ISOLATED", "Delete Isolated Vertices", "Delete vertices not used by polygons"),
    ("REMOVE_UNUSED_MAP", "Remove Unused Map Verts", "Blender stores UVs per face corner and has no unused map vertices"),
    ("CREATE_SHAPE", "Create Shape From Selection", "Copy selected edges into a curve"),
    ("RETRIANGULATE", "Retriangulate", "Triangulate selected polygons"),
    ("TURN", "Turn", "Rotate the selected diagonal between two faces"),
    ("EDIT_TRIANGULATION", "Edit Triangulation", "Blender cannot edit hidden triangulation without changing polygon topology"),
    ("HINGE", "Hinge From Edge", "Blender has no picked-edge hinge extrusion tool"),
    ("SPLINE_EXTRUDE", "Extrude Along Spline", "Blender has no polygon extrusion along a picked spline"),
    ("PLANAR_X", "X", "Flatten selected vertices on local X"),
    ("PLANAR_Y", "Y", "Flatten selected vertices on local Y"),
    ("PLANAR_Z", "Z", "Flatten selected vertices on local Z"),
    ("VIEW_ALIGN", "View Align", "Flatten selection on the active view plane"),
    ("GRID_ALIGN", "Grid Align", "Flatten selection on the nearest principal view plane"),
    ("CREATE", "Create", "Create an edge or face from selected vertices"),
    ("QUICK_SLICE", "QuickSlice", "Click two points to slice. Right-click to finish"),
    ("SLICE", "Slice", "Slice using the stored plane"),
    ("RESET_PLANE", "Reset Plane", "Reset the slice plane to local Z at the origin"),
    ("ATTACH", "Attach", "Attach other selected meshes"),
    ("COPY_SELECTION", "Copy", "Copy this sub-object selection to a named mesh attribute"),
    ("PASTE_SELECTION", "Paste", "Restore the copied selection at this sub-object level"),
    ("RING_SHIFT_UP", "Ring Shift Up", "Shift selected edges across adjacent quads"),
    ("RING_SHIFT_DOWN", "Ring Shift Down", "Shift selected edges across adjacent quads"),
    ("LOOP_SHIFT_UP", "Loop Shift Up", "Shift selected edges along their quad loops"),
    ("LOOP_SHIFT_DOWN", "Loop Shift Down", "Shift selected edges along their quad loops"),
    ("SELECT_ANGLE", "By Angle", "Expand selected faces across angles below the threshold"),
]

UNSUPPORTED = {
    key: reason for key, label, reason in EXTRA_OPS
    if key in {"REMOVE_UNUSED_MAP", "EDIT_TRIANGULATION", "HINGE", "SPLINE_EXTRUDE"}
}

CADDIES = {
    "EXTRUDE": ("extrusion_type", "amount", "local_bias", "base_width"), "WELD": ("threshold",),
    "CHAMFER": ("chamfer_miter", "amount", "segments", "tension", "chamfer_depth",
                "end_bias", "radial_bias", "open", "invert_open", "chamfer_smooth",
                "smooth_type", "smooth_threshold", "chamfer_clamp"),
    "BRIDGE": ("segments", "taper", "bias", "smooth", "twist1", "twist2", "bridge_selection",
               "bridge_adjacent", "reverse_triangulation"),
    "CONNECT": ("segments", "pinch", "slide"),
    "OUTLINE": ("amount",), "BEVEL": ("bevel_type", "height", "amount", "local_bias"),
    "INSET": ("amount", "individual"), "HINGE": (), "SPLINE_EXTRUDE": (),
    "MSMOOTH": ("smoothness",), "TESSELLATE": ("tessellate_type", "tess_tension"),
    "RELAX": ("relax", "iterations", "hold_boundary", "hold_outer"), "DETACH": ("object_name", "as_clone", "as_element"),
    "CREATE_SHAPE": ("object_name",), "SLICE_PLANE": ("plane_x", "plane_y", "plane_z", "normal_x", "normal_y", "normal_z", "split"),
}


def option_properties():
    return {
        "amount": FloatProperty(name="Amount", default=0.1),
        "height": FloatProperty(name="Height", default=0.1),
        "extrusion_type": EnumProperty(name="Extrusion Type", items=[("GROUP", "Group", ""), ("LOCAL", "Local Normal", ""), ("POLYGON", "By Polygon", "")]),
        "bevel_type": EnumProperty(name="Bevel Type", items=[("GROUP", "Group", ""), ("LOCAL", "Local Normal", ""), ("POLYGON", "By Polygon", "")]),
        "local_bias": FloatProperty(name="Bias", default=0, description="Blender has no Max Local Normal Bias solver"),
        "base_width": FloatProperty(name="Extrusion Base Width", default=0, description="Blender extrusion has no base-width parameter"),
        "tessellate_type": EnumProperty(name="Type", items=[("EDGE", "Edge", ""), ("FACE", "Face", "")]),
        "threshold": FloatProperty(name="Weld Threshold", min=0, default=0.0001),
        "segments": IntProperty(name="Segments", min=1, max=100, default=1),
        "open": BoolProperty(name="Open", default=False),
        "invert_open": BoolProperty(name="Invert Open", default=False),
        "chamfer_miter": EnumProperty(name="Mitering", default="UNIFORM", items=[
            ("QUAD", "Quad", "Blender offset bevel with grid-filled intersections"),
            ("TRI", "Tri", "Legacy Standard chamfer, Blender cutoff intersections"),
            ("UNIFORM", "Uniform", "Blender width bevel with grid-filled intersections"),
            ("RADIAL", "Radial", "Blender arc outer and inner miters"),
            ("PATCH", "Patch", "Blender patch outer miter and sharp inner miter")]),
        "chamfer_depth": FloatProperty(name="Depth", min=-.5, max=1, default=.5),
        "end_bias": FloatProperty(name="End Bias", min=0, max=1, default=.5,
            description="BMesh bevel has no Max end-point bias parameter"),
        "radial_bias": FloatProperty(name="Radial Bias", min=0, max=1, default=0,
            description="BMesh bevel has no Max spherical radial bias parameter"),
        "chamfer_smooth": BoolProperty(name="Smooth", default=True),
        "smooth_type": EnumProperty(name="Smooth Type", items=[
            ("OBJECT", "Smooth Entire Object", ""), ("CHAMFERS", "Smooth Chamfers Only", "")]),
        "smooth_threshold": FloatProperty(name="Smooth Threshold", min=0, max=180, default=30),
        "chamfer_clamp": BoolProperty(name="Clamp Overlap", default=True),
        "tension": FloatProperty(name="Tension", min=0, max=1, default=1),
        "tess_tension": FloatProperty(name="Tension", default=0),
        "taper": FloatProperty(name="Taper", default=0, min=-100, max=1000),
        "bias": FloatProperty(name="Bias", default=0, min=-99, max=99),
        "smooth": FloatProperty(name="Smooth", default=45, min=0, max=180),
        "bridge_adjacent": FloatProperty(name="Bridge Adjacent", default=45, min=0, max=180,
            description="Blender bridge_edge_loops has no adjacent-edge angle filter"),
        "reverse_triangulation": BoolProperty(name="Reverse Triangulation", default=False,
            description="Blender bridge_edge_loops cannot reverse Max's unequal-loop triangulation"),
        "twist": IntProperty(name="Twist", default=0),
        "twist1": IntProperty(name="Twist 1", default=0),
        "twist2": IntProperty(name="Twist 2", default=0),
        "bridge_selection": EnumProperty(name="Selection", description="Blender bridges the current selection. Max's caddy selection mode and pick controls are not implemented", items=[("SELECTION", "Use Polygon/Border Selection", "Blender uses the current selection and has no Max caddy selection mode"), ("PICK", "Use Specific Polygons/Borders", "Blender has no Max bridge caddy border picker")]),
        "pinch": FloatProperty(name="Pinch", default=0, min=-100, max=100, description="Blender subdivision has no Max Connect Pinch spacing solver"),
        "slide": FloatProperty(name="Slide", default=0, min=-100, max=100, description="Blender subdivision has no Max Connect Slide spacing solver"),
        "smoothness": FloatProperty(name="Smoothness", default=1, min=0, max=1),
        "relax": FloatProperty(name="Relax Amount", default=0.5, min=-1, max=1),
        "iterations": IntProperty(name="Iterations", default=3, min=1, max=100),
        "hold_boundary": BoolProperty(name="Hold Boundary Points", default=True),
        "hold_outer": BoolProperty(name="Hold Outer Points", default=False),
        "individual": BoolProperty(name="By Polygon", default=False),
        "object_name": StringProperty(name="Name", default="Detached"),
        "as_clone": BoolProperty(name="Detach As Clone", default=False),
        "as_element": BoolProperty(name="Detach To Element", default=False),
        "plane_x": FloatProperty(name="Plane X"),
        "plane_y": FloatProperty(name="Plane Y"),
        "plane_z": FloatProperty(name="Plane Z"),
        "normal_x": FloatProperty(name="Normal X"),
        "normal_y": FloatProperty(name="Normal Y"),
        "normal_z": FloatProperty(name="Normal Z", default=1),
        "split": BoolProperty(name="Split", default=False),
    }


class MaxPolyOperation(PropertyGroup):
    __annotations__ = option_properties()


def operation_defaults(action):
    # Caddy distances use one Max world unit per Blender unit, without physical-unit inference.
    return {
        "EXTRUDE": {"amount": 10, "base_width": 3},
        "CHAMFER": {"amount": 1},
        "BEVEL": {"height": 10, "amount": -1},
        "INSET": {"amount": 1}, "OUTLINE": {"amount": -1},
        "WELD": {"threshold": .1}, "RELAX": {"iterations": 1},
        "TESSELLATE": {"tess_tension": 0},
    }.get(action, {})


def settings(context, action):
    from .operators import current_level
    if action == "SLICE_PLANE":
        return context.scene.max_poly_slice
    key = f"{action}:{current_level(context)}"
    coll = context.scene.max_poly_operations
    item = coll.get(key)
    if item is None:
        item = coll.add()
        item.name = key
        for prop, value in operation_defaults(action).items():
            setattr(item, prop, value)
    elif action == "TESSELLATE" and not item.is_property_set("tess_tension") and item.is_property_set("tension"):
        # Preserve the number entered in files saved before Tension was separated.
        item.tess_tension = item.tension
    return item


def soft_update(self, context):
    ts = context.tool_settings
    ts.use_proportional_edit = self.soft
    ts.use_proportional_connected = self.edge_distance
    ts.proportional_size = self.falloff
    ts.proportional_edit_falloff = self.falloff_curve


def subdiv_update(self, context):
    ob = self.id_data
    mod = next((m for m in ob.modifiers if is_nurms(m)), None)
    if mod is None and self.nurms:
        active = ob.modifiers.active
        active = active if active is not None and active.is_active else None
        mod = ob.modifiers.new("NURMS Subdivision", "SUBSURF")
        if active is not None:
            ob.modifiers.active = active
    if mod:
        mod.show_viewport = mod.show_render = self.nurms
        mod.levels = mod.render_levels = self.iterations
        mod.show_only_control_edges = self.isoline
        mod.show_in_editmode = True
        mod.show_on_cage = True
    me = ob.data
    if ob.mode == "EDIT":
        bm = bmesh.from_edit_mesh(me)
        layer = bm.faces.layers.int.get(SMOOTH_BACKUP)
        if self.smooth_result:
            if layer is None:
                layer = bm.faces.layers.int.new(SMOOTH_BACKUP)
                for face in bm.faces:
                    face[layer] = int(face.smooth)
            for face in bm.faces:
                face.smooth = True
        elif layer:
            for face in bm.faces:
                face.smooth = bool(face[layer])
            bm.faces.layers.int.remove(layer)
        bmesh.update_edit_mesh(me)
    else:
        backup = me.attributes.get(SMOOTH_BACKUP)
        if self.smooth_result:
            if backup is None:
                backup = me.attributes.new(SMOOTH_BACKUP, "INT", "FACE")
                for face, value in zip(me.polygons, backup.data):
                    value.value = int(face.use_smooth)
            for face in me.polygons:
                face.use_smooth = True
        elif backup:
            for face, value in zip(me.polygons, backup.data):
                face.use_smooth = bool(value.value)
            me.attributes.remove(backup)
        me.update()


class MaxPolyState(PropertyGroup):
    by_vertex: BoolProperty(name="By Vertex", description="Use Blender's Vertex selection level. Per-click By Vertex is unavailable")
    ignore_backfacing: BoolProperty(name="Ignore Backfacing", description="Blender does not expose Max's backface selection filter")
    preview: EnumProperty(name="Preview Selection", items=[(v, n, "Blender has no Max-style hover preview and multi-level selection") for v, n in (("OFF", "Off"), ("SUBOBJ", "SubObj"), ("MULTI", "Multi"))])
    constraints: EnumProperty(name="Constraints", default="NONE", update=poly_constraints.constraint_update,
                              items=[("NONE", "None", "Ordinary Move"), ("EDGE", "Edge", "Slide along the original connected edges"),
                                     ("FACE", "Face", "Project each vertex onto this object's original surface"),
                                     ("NORMAL", "Normal", "Move along the original averaged vertex normals")])
    soft: BoolProperty(name="Use Soft Selection", update=soft_update)
    edge_distance: BoolProperty(name="Edge Distance", description="Connected-only proportional editing. Blender has no edge-count cutoff", update=soft_update)
    edge_steps: IntProperty(name="Edge Distance", default=1, min=1, description="Blender proportional editing has no edge-count cutoff")
    affect_backfacing: BoolProperty(name="Affect Backfacing", default=True, description="Blender proportional editing has no backface influence filter")
    pinch: FloatProperty(name="Pinch", description="Blender uses preset curves rather than Max's Pinch parameter")
    bubble: FloatProperty(name="Bubble", description="Blender uses preset curves rather than Max's Bubble parameter")
    falloff: FloatProperty(name="Falloff", default=20, min=0.00001, update=soft_update)
    shaded_faces: BoolProperty(name="Shaded Faces", description="Blender proportional editing does not draw Max's soft-selection face gradient")
    delete_isolated: BoolProperty(name="Delete Isolated Vertices", default=True, description="Remove vertices not used by polygons after Delete or Remove")
    full_interactivity: BoolProperty(name="Full Interactivity", default=True, description="Blender does not expose Max's deferred mesh evaluation mode")
    depth: FloatProperty(name="Depth", description="Blender crease attributes have no Max crease depth control")
    display_hard_edges: BoolProperty(name="Display Hard Edges", description="Blender has no separate Max hard-edge display mode")
    falloff_curve: EnumProperty(name="Falloff Curve", items=[(v, n, "") for v, n in (
        ("SMOOTH", "Smooth"), ("SPHERE", "Sphere"), ("ROOT", "Root"),
        ("INVERSE_SQUARE", "Inverse Square"), ("SHARP", "Sharp"), ("LINEAR", "Linear"), ("CONSTANT", "Constant"))], update=soft_update)
    by_angle: BoolProperty(name="By Angle", description="Use Select By Angle to expand the current polygon selection")
    slice_plane: BoolProperty(name="Slice Plane", description="Enable the numeric slice plane. Use its settings to position it, then click Slice")
    angle: FloatProperty(name="Angle", default=45, min=0, max=180)
    material_id: IntProperty(name="Set ID", min=1, max=32767, default=1)
    select_id: IntProperty(name="Select ID", min=1, max=32767, default=1)
    clear_selection: BoolProperty(name="Clear Selection", default=True)
    sg_clear_selection: BoolProperty(name="Clear Selection", default=True)
    material_name: EnumProperty(name="Select by Name", items=lambda self, c: material_items(self, c))
    sg_select: IntProperty(name="Smoothing Group", min=1, max=32, default=1)
    auto_angle: FloatProperty(name="Threshold", default=45, min=0, max=180)
    weight: FloatProperty(name="Weight", default=1, description="Blender subdivision has no Max vertex/edge weight parameter")
    smoothness: FloatProperty(name="Smoothness", default=1, description="Blender Catmull-Clark subdivision has no Max adaptive Smoothness threshold")
    crease: FloatProperty(name="Crease", default=0, min=0, max=1)
    nurms: BoolProperty(name="Use NURMS Subdivision", update=subdiv_update)
    smooth_result: BoolProperty(name="Smooth Result", default=True, update=subdiv_update)
    isoline: BoolProperty(name="Isoline Display", update=subdiv_update)
    iterations: IntProperty(name="Iterations", default=1, min=0, max=6, update=subdiv_update)
    vertex_color: bpy.props.FloatVectorProperty(name="Color", subtype="COLOR", size=3, default=(1, 1, 1), min=0, max=1, description="Max vertex color editing is not mapped to a Blender color attribute")
    illumination: bpy.props.FloatVectorProperty(name="Illumination", subtype="COLOR", size=3, default=(1, 1, 1), min=0, max=1, description="Blender has no Max vertex illumination channel")
    alpha: FloatProperty(name="Alpha", default=100, min=0, max=100, description="Max vertex alpha editing is not mapped to a Blender attribute")
    use_displacement: BoolProperty(name="Use Displacement", description="Blender has no Max subdivision displacement approximation")
    split_mesh: BoolProperty(name="Split Mesh", default=True, description="Blender has no Max subdivision displacement Split Mesh option")
    paint_mode: EnumProperty(name="Paint Deformation", items=[(v, n, "Max Paint Deformation is not mapped to Blender sculpt mode") for v,n in (("PUSH", "Push/Pull"), ("RELAX", "Relax"), ("REVERT", "Revert"))])
    paint_value: FloatProperty(name="Push/Pull Value", description="Max Paint Deformation is unavailable in mesh Edit mode")
    brush_size: FloatProperty(name="Brush Size", min=0, description="Max Paint Deformation is unavailable in mesh Edit mode")
    brush_strength: FloatProperty(name="Brush Strength", min=0, description="Max Paint Deformation is unavailable in mesh Edit mode")
    paint_direction: EnumProperty(name="Push/Pull Direction", items=[("ORIGINAL", "Original Normals", "Max Paint Deformation is not mapped to Blender sculpt mode")])


def material_items(self, context):
    ob = self.id_data
    return [(str(i), m.name if m else f"ID {i + 1}", "") for i, m in enumerate(ob.data.materials)] or [("0", "No materials", "")]


class MAX_OT_poly_settings(Operator):
    """Open operation settings and apply them. Main buttons reuse the accepted values"""
    bl_idname = "max.poly_settings"
    bl_label = "Editable Poly Settings"
    bl_options = {"REGISTER", "UNDO"}

    action: StringProperty()
    __annotations__ = {**option_properties(), "action": StringProperty()}

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH" or (context.mode == "OBJECT" and context.active_object is not None)

    def invoke(self, context, event):
        if self.action in poly_caddies.ACTIONS:
            return poly_caddies.invoke(self, context, event)
        s = settings(context, self.action)
        for key in CADDIES[self.action]:
            setattr(self, key, getattr(s, key))
        return context.window_manager.invoke_props_dialog(self, width=300)

    def modal(self, context, event):
        return poly_caddies.modal(self, context, event)

    def cancel(self, context):
        poly_caddies.cancel(self, context)

    def draw(self, context):
        from .operators import EDIT_POLY_OPS, current_level
        self.layout.label(text=dict((k, n) for k, n, _ in EDIT_POLY_OPS)[self.action])
        for key in CADDIES[self.action]:
            if key == "local_bias" and not ((self.action == "BEVEL" and self.bevel_type == "LOCAL") or (self.action == "EXTRUDE" and current_level(context) >= 4 and self.extrusion_type == "LOCAL")):
                continue
            if self.action == "EXTRUDE" and ((key == "extrusion_type" and current_level(context) < 4) or (key == "base_width" and current_level(context) >= 4)):
                continue
            if self.action == "BRIDGE" and current_level(context) == 2 and key not in {"segments", "smooth", "bridge_selection"}:
                continue
            row = self.layout.row()
            # Connect has no native Max pinch/slide spacing control.
            if (self.action == "CONNECT" and key in {"pinch", "slide"}) or key in {"base_width", "bridge_selection", "local_bias"}:
                row.enabled = False
            label = "Extrusion Height" if self.action == "EXTRUDE" and key == "amount" else "Outline Amount" if self.action == "BEVEL" and key == "amount" else "Amount" if key == "relax" else None
            prop = self.properties.bl_rna.properties[key]
            if prop.type in {"INT", "FLOAT"}:
                row.label(text=(label or prop.name) + ":")
                row.prop(self, key, text="")
            else:
                row.prop(self, key)
        if self.action == "BRIDGE":
            from .editable_poly_ui import unavailable
            name = "Edge" if current_level(context) == 2 else "Border" if current_level(context) == 3 else "Polygon"
            row = self.layout.row(align=True)
            for i in (1, 2):
                unavailable(row, f"Pick {name} {i}", "Blender bridge uses the current selection and has no Max caddy picker")
        if self.action == "CONNECT":
            self.layout.label(text="Pinch and Slide require Max's edge spacing solver", icon="INFO")
        if self.action == "EXTRUDE" and current_level(context) < 4:
            self.layout.label(text="Blender extrusion has no base-width parameter", icon="INFO")

    def execute(self, context):
        s = settings(context, self.action)
        old = {key: getattr(s, key) for key in CADDIES[self.action]}
        for key in old:
            setattr(s, key, getattr(self, key))
        result = bpy.ops.max.edit_poly(op=self.action)
        if result != {"FINISHED"}:
            for key, value in old.items():
                setattr(s, key, value)
        return result


class MAX_OT_poly_hsx_settings(Operator):
    """Imported settings shortcuts share the panel's persistent operation values"""
    bl_idname = "max.hsx_settings"
    bl_label = "Editable Poly Settings"
    op: EnumProperty(items=[(key, key.title(), "") for key in ("CHAMFER", "EXTRUDE", "CONNECT", "BRIDGE", "TESSELLATE")])

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def invoke(self, context, event):
        return bpy.ops.max.poly_settings("INVOKE_DEFAULT", action=self.op)

    def execute(self, context):
        return bpy.ops.max.edit_poly(op=self.op)


def hsx_adapter_classes():
    # Main owns hsx import/storage. Replace only its settings class, before
    # __init__ assembles registrations, so the operator ID registers once.
    try:
        from . import hsx_import
    except ImportError:
        return (MAX_OT_poly_hsx_settings,)
    original = hsx_import.MAX_OT_hsx_settings
    hsx_import.classes = tuple(MAX_OT_poly_hsx_settings if cls is original else cls for cls in hsx_import.classes)
    hsx_import.MAX_OT_hsx_settings = MAX_OT_poly_hsx_settings
    hsx_import.DESCRIPTIONS["target weld"] = ("Mesh", "max.edit_poly", {"op": "TARGET_WELD"})
    hsx_import.DESCRIPTIONS["target weld mode"] = ("Mesh", "max.edit_poly", {"op": "TARGET_WELD"})
    return ()


class MAX_OT_poly_unavailable(Operator):
    """This Max tool has no Blender equivalent"""
    bl_idname = "max.poly_unavailable"
    bl_label = "Unavailable in Blender"
    reason: StringProperty()

    @classmethod
    def description(cls, context, props):
        return props.reason

    def execute(self, context):
        self.report({"WARNING"}, self.reason)
        return {"CANCELLED"}


def update_mesh(context):
    bm = bmesh.from_edit_mesh(context.active_object.data)
    layer = bm.faces.layers.int.get(SG_ATTRIBUTE)
    if layer:
        sync_smoothing(bm, layer)
    bmesh.update_edit_mesh(context.active_object.data, loop_triangles=True, destructive=True)


def selected_vertices(bm):
    return [v for v in bm.verts if v.select and not v.hide]


def cleanup_isolated(context):
    if context.active_object.max_poly.delete_isolated:
        bm = bmesh.from_edit_mesh(context.active_object.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces and not v.hide], context="VERTS")
        update_mesh(context)


def flatten(context, normal):
    bm = bmesh.from_edit_mesh(context.active_object.data)
    verts = selected_vertices(bm)
    if not verts:
        return {"CANCELLED"}
    center = sum((v.co for v in verts), Vector()) / len(verts)
    normal.normalize()
    for v in verts:
        v.co -= normal * (v.co - center).dot(normal)
    update_mesh(context)
    return {"FINISHED"}


def create_shape(context, name):
    ob = context.active_object
    bm = bmesh.from_edit_mesh(ob.data)
    edges = [e for e in bm.edges if e.select and not e.hide]
    if not edges:
        return {"CANCELLED"}
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    # Keep each edge as a poly spline so branches and disconnected sets are preserved.
    for edge in edges:
        spline = cu.splines.new("POLY")
        spline.points.add(1)
        for point, vert in zip(spline.points, edge.verts):
            point.co = (*vert.co, 1)
    shape = bpy.data.objects.new(name, cu)
    context.collection.objects.link(shape)
    shape.matrix_world = ob.matrix_world.copy()
    return {"FINISHED"}


def shift_edges(bm, ring, direction):
    """Move a selection one quad step. Stable face/vertex order defines +/- direction."""
    bm.faces.index_update()
    bm.verts.index_update()
    source = {e for e in bm.edges if e.select and not e.hide}
    target = set()
    for edge in source:
        if ring:
            candidates = []
            for face in edge.link_faces:
                if len(face.verts) == 4:
                    other = next(e for e in face.edges if not set(e.verts) & set(edge.verts))
                    candidates.append((face.index, other))
        else:
            candidates = []
            for vert in edge.verts:
                # Interior quad loops continue through the edge that shares no face.
                others = [e for e in vert.link_edges if e != edge and not set(e.link_faces) & set(edge.link_faces)]
                if len(others) == 1:
                    candidates.append((vert.index, others[0]))
        candidates.sort(key=lambda pair: pair[0])
        if candidates:
            target.add(candidates[-1 if direction > 0 else 0][1])
    if not target:
        return {"CANCELLED"}
    for face in bm.faces:
        face.select_set(False)
    for edge in bm.edges:
        edge.select_set(False)
    for vert in bm.verts:
        vert.select_set(False)
    for edge in target:
        edge.select_set(True)
    bm.select_flush_mode()
    return {"FINISHED"}


def chamfer_options(s, mode):
    """Map the 2026 miter choices to BMesh's bevel parameters."""
    outer = {'QUAD': 'SHARP', 'TRI': 'SHARP', 'UNIFORM': 'SHARP',
             'RADIAL': 'ARC', 'PATCH': 'PATCH'}[s.chamfer_miter]
    profile = (1 - .5*s.tension if s.chamfer_miter in {'QUAD', 'UNIFORM'} else
               .5 + .5*s.chamfer_depth if s.chamfer_miter in {'RADIAL', 'PATCH'} else .5)
    return dict(offset=max(0, s.amount), offset_type='WIDTH' if mode != 'VERT' and s.chamfer_miter == 'UNIFORM' else 'OFFSET',
                segments=1 if mode == 'VERT' else s.segments, profile=.5 if mode == 'VERT' else profile,
                affect='VERTICES' if mode == 'VERT' else 'EDGES',
                miter_outer=outer, miter_inner='ARC' if outer == 'ARC' else 'SHARP',
                vmesh_method='CUTOFF' if s.chamfer_miter == 'TRI' else 'ADJ',
                harden_normals=mode != 'VERT' and s.chamfer_smooth, clamp_overlap=s.chamfer_clamp,
                material=-1, loop_slide=True)


def run(operator, context, how, operation_settings=None):
    """Return None for the legacy commands that need no new handling."""
    from .operators import mesh_select_mode
    action = operator.op
    if action in {"CUT", "QUICK_SLICE", "TARGET_WELD"}:
        if action == "TARGET_WELD":
            from .operators import current_level
            if context.mode != "EDIT_MESH" or current_level(context) not in (1, 2, 3):
                operator.report({"WARNING"}, "Target Weld is available at Vertex, Edge and Border levels")
                return {"CANCELLED"}
        if action != "QUICK_SLICE" or how == "INVOKE_DEFAULT":
            from .operators import viewport_override
            override = viewport_override(context)
            if override is None or override["region"] is None:
                operator.report({"WARNING"}, "This tool requires a 3D viewport")
                return {"CANCELLED"}
            with context.temp_override(**override):
                if action == "TARGET_WELD":
                    return bpy.ops.max.target_weld("INVOKE_DEFAULT")
                if action == "QUICK_SLICE":
                    return bpy.ops.max.poly_quick_slice("INVOKE_DEFAULT")
                return bpy.ops.max.cut("INVOKE_DEFAULT")
    if context.mode == "OBJECT":
        if action not in OBJECT_ACTIONS:
            return {"CANCELLED"}
        if action == "ATTACH":
            return bpy.ops.max.object_cmd(cmd="ATTACH")
        operation_settings = settings(context, action)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        try:
            return run(operator, context, how, operation_settings)
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")
    if action in UNSUPPORTED:
        operator.report({"WARNING"}, UNSUPPORTED[action])
        return {"CANCELLED"}
    handled = set(CADDIES) | {k for k, _, _ in EXTRA_OPS} | {"MAKE_PLANAR", "BEVEL"}
    if action not in handled:
        return None
    ob = context.active_object
    bm = bmesh.from_edit_mesh(ob.data)
    mode = mesh_select_mode(context)
    s = operation_settings if operation_settings is not None else settings(context, action)
    ops = poly_caddies.MeshOps() if how == "CADDY_PREVIEW" else bpy.ops.mesh
    try:
        if action == "EXTRUDE":
            faces = [f for f in bm.faces if f.select and not f.hide]
            if mode != "FACE":
                faces = list({f for v in selected_vertices(bm) for f in v.link_faces})
            normal = sum((f.normal for f in faces), Vector())
            if normal.length == 0:
                normal = Vector((0, 0, 1))
            normal.normalize()
            if mode == "FACE" and s.extrusion_type == "POLYGON":
                result = bmesh.ops.extrude_discrete_faces(bm, faces=faces)
                for face in result["faces"]:
                    bmesh.ops.translate(bm, verts=list(face.verts), vec=face.normal * s.amount)
                for seq in (bm.faces, bm.edges, bm.verts):
                    for item in seq:
                        item.select_set(False)
                for face in result["faces"]:
                    face.select_set(True)
                bm.select_flush_mode()
                update_mesh(context)
                return {"FINISHED"}
            if mode == "FACE":
                result = bmesh.ops.extrude_face_region(bm, geom=faces)
                bmesh.ops.delete(bm, geom=faces, context="FACES_ONLY")
            elif mode == "EDGE":
                result = bmesh.ops.extrude_edge_only(bm, edges=[e for e in bm.edges if e.select])
            else:
                result = bmesh.ops.extrude_vert_indiv(bm, verts=selected_vertices(bm))
            geom = result.get("geom", result.get("verts", []) + result.get("edges", []))
            verts = [v for v in geom if isinstance(v, bmesh.types.BMVert)]
            if not verts:
                return {"CANCELLED"}
            if mode == "FACE" and s.extrusion_type == "LOCAL":
                top_faces = {f for f in geom if isinstance(f, bmesh.types.BMFace)}
                for vert in verts:
                    direction = sum((f.normal for f in vert.link_faces if f in top_faces), Vector())
                    vert.co += (direction.normalized() if direction.length else normal) * s.amount
            else:
                bmesh.ops.translate(bm, verts=verts, vec=normal * s.amount)
            for seq in (bm.faces, bm.edges, bm.verts):
                for item in seq:
                    item.select_set(False)
            if mode == "VERT":
                for vert in verts:
                    vert.select_set(True)
            elif mode == "EDGE":
                top = set(verts)
                for edge in geom:
                    if isinstance(edge, bmesh.types.BMEdge) and all(v in top for v in edge.verts):
                        edge.select_set(True)
            else:
                for item in geom:
                    if item.is_valid:
                        item.select_set(True)
            bm.select_flush_mode()
        elif action == "CHAMFER":
            geom = selected_vertices(bm) if mode == "VERT" else [e for e in bm.edges if e.select and not e.hide]
            result = bmesh.ops.bevel(bm, geom=geom, **chamfer_options(s, mode))
            created = set(result["faces"])
            bm.normal_update()
            if mode != "VERT" and s.chamfer_smooth:
                smooth_faces = set(bm.faces) if s.smooth_type == "OBJECT" else created
                for face in smooth_faces:
                    face.smooth = True
                for edge in bm.edges:
                    if len(edge.link_faces) == 2 and all(f in smooth_faces for f in edge.link_faces):
                        edge.smooth = edge.calc_face_angle() < math.radians(s.smooth_threshold)
            for seq in (bm.faces, bm.edges, bm.verts):
                for item in seq:
                    item.select_set(False)
            for face in created:
                face.select_set(True)
            if s.open:
                remove = [f for f in bm.faces if f not in created] if mode != "VERT" and s.invert_open else list(created)
                bmesh.ops.delete(bm, geom=remove, context="FACES_ONLY")
            bm.select_flush_mode()
        elif action == "WELD":
            ops.remove_doubles(threshold=s.threshold)
        elif action == "BRIDGE":
            old_verts = set(bm.verts)
            old_faces = set(bm.faces)
            # Find the two selected border loops for the taper axis.
            remaining = {e for e in bm.edges if e.select}
            centers = []
            while remaining:
                loop = {remaining.pop()}
                todo = list(loop)
                while todo:
                    for vert in todo.pop().verts:
                        for edge in vert.link_edges:
                            if edge in remaining:
                                remaining.remove(edge)
                                loop.add(edge)
                                todo.append(edge)
                verts = {v for e in loop for v in e.verts}
                centers.append(sum((v.co for v in verts), Vector()) / len(verts))
            ops.bridge_edge_loops(number_cuts=s.segments - 1, twist_offset=s.twist + s.twist2 - s.twist1,
                                  interpolation="LINEAR")
            if len(centers) == 2 and s.taper:
                start, end = centers
                axis = end - start
                if axis.length_squared > 1e-12:
                    peak = 0.5 + s.bias / 200
                    for vert in set(bm.verts) - old_verts:
                        t = max(0, min(1, (vert.co - start).dot(axis) / axis.length_squared))
                        strength = t / peak if t <= peak else (1 - t) / (1 - peak)
                        center = start.lerp(end, t)
                        vert.co = center + (vert.co - center) * (1 + s.taper * strength / 100)
            bm.normal_update()
            new_faces = set(bm.faces) - old_faces
            for face in new_faces:
                face.smooth = True
            for edge in bm.edges:
                if len(edge.link_faces) == 2 and any(f in new_faces for f in edge.link_faces):
                    edge.smooth = edge.calc_face_angle() <= math.radians(s.smooth)
        elif action == "CONNECT":
            if mode == "VERT":
                ops.vert_connect_path()
            else:
                ops.subdivide(number_cuts=s.segments, smoothness=0)
        elif action == "INSET":
            if s.individual:
                ops.inset(thickness=max(0, s.amount), use_individual=True)
            else:
                ops.inset(thickness=max(0, s.amount), use_individual=False)
        elif action == "OUTLINE":
            # Move the selected region boundary in its plane without adding faces.
            faces = {f for f in bm.faces if f.select}
            offsets = {}
            for edge in bm.edges:
                linked = [f for f in edge.link_faces if f in faces]
                if len(linked) == 1 and (len(edge.link_faces) == 1 or len(linked) != len(edge.link_faces)):
                    face = linked[0]
                    loop = next(l for l in face.loops if l.edge == edge)
                    tangent = (loop.link_loop_next.vert.co - loop.vert.co).normalized()
                    outward = tangent.cross(face.normal).normalized()
                    for v in edge.verts:
                        offsets.setdefault(v, []).append(outward)
            for v, normals in offsets.items():
                offset = sum(normals, Vector())
                if offset.length:
                    offset.normalize()
                    v.co += offset * s.amount / max(abs(offset.dot(normals[0])), 0.01)
        elif action == "BEVEL":
            faces = [f for f in bm.faces if f.select and not f.hide]
            if not faces:
                return {"CANCELLED"}
            if s.bevel_type == "POLYGON":
                bmesh.ops.inset_individual(bm, faces=faces, thickness=-s.amount, depth=s.height, use_even_offset=True)
            else:
                normal = sum((f.normal for f in faces), Vector()).normalized()
                bmesh.ops.inset_region(bm, faces=faces, thickness=-s.amount, depth=0, use_even_offset=True, use_boundary=True)
                tops = set(faces)
                for vert in {v for f in faces for v in f.verts}:
                    direction = normal if s.bevel_type == "GROUP" else sum((f.normal for f in vert.link_faces if f in tops), Vector()).normalized()
                    vert.co += direction * s.height
            for seq in (bm.faces, bm.edges, bm.verts):
                for item in seq:
                    item.select_set(False)
            for face in faces:
                face.select_set(True)
            bm.select_flush_mode()
        elif action == "MSMOOTH":
            ops.subdivide(number_cuts=s.segments, smoothness=s.smoothness)
        elif action == "TESSELLATE":
            if s.tessellate_type == "FACE":
                ops.poke()
            else:
                # The mesh operator clamps smoothness to nonnegative values.
                # BMesh supports the signed displacement required by Max Tension.
                result = bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if e.select and not e.hide],
                                                   cuts=1, smooth=s.tess_tension, use_grid_fill=True)
                for elem in result["geom_inner"] + result["geom_split"]:
                    elem.select_set(True)
                bm.select_flush_mode()
        elif action == "RELAX":
            verts = selected_vertices(bm)
            held = {v: v.co.copy() for v in verts if (s.hold_boundary and v.is_boundary) or (s.hold_outer and any(not e.select for e in v.link_edges))}
            for i in range(s.iterations):
                bmesh.ops.smooth_vert(bm, verts=verts, factor=s.relax, use_axis_x=True, use_axis_y=True, use_axis_z=True)
                for vert, co in held.items():
                    vert.co = co
        elif action == "DETACH":
            if s.as_clone:
                ops.duplicate()
            if s.as_element:
                ops.split()
                return {"FINISHED"}
            before = set(bpy.data.objects)
            ops.separate(type="SELECTED")
            for new in set(bpy.data.objects) - before:
                new.name = s.object_name
        elif action == "INSERT_VERTEX":
            if mode == "FACE":
                ops.poke()
            else:
                for edge in list(bm.edges):
                    if edge.select and not edge.hide:
                        new_edge, vertex = bmesh.utils.edge_split(edge, edge.verts[0], 0.5)
                        vertex.select_set(True)
        elif action == "SPLIT":
            ops.edge_split(type="EDGE")
        elif action == "DELETE_ISOLATED":
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces and not v.hide], context="VERTS")
        elif action == "CREATE_SHAPE":
            return create_shape(context, s.object_name)
        elif action == "RETRIANGULATE":
            ops.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
        elif action == "TURN":
            ops.edge_rotate(use_ccw=False)
        elif action in {"MAKE_PLANAR", "PLANAR_X", "PLANAR_Y", "PLANAR_Z", "VIEW_ALIGN", "GRID_ALIGN"}:
            if action == "MAKE_PLANAR":
                normal = sum((f.normal for f in bm.faces if f.select), Vector())
                if not normal.length:
                    normal = Vector((0, 0, 1))
            elif action in {"VIEW_ALIGN", "GRID_ALIGN"}:
                from .operators import find_view3d
                area, region = find_view3d(context)
                rv3d = region.data if region is not None else None
                if rv3d is None and area is not None:
                    rv3d = area.spaces.active.region_3d
                if rv3d is None:
                    return {"CANCELLED"}
                normal = ob.matrix_world.to_3x3().transposed() @ (rv3d.view_rotation @ Vector((0, 0, 1)))
                if action == "GRID_ALIGN":
                    axis = max(range(3), key=lambda i: abs(normal[i]))
                    normal = Vector(tuple(1 if i == axis else 0 for i in range(3)))
            else:
                normal = Vector(tuple(1 if c == action[-1] else 0 for c in "XYZ"))
            return flatten(context, normal)
        elif action == "CREATE":
            ops.edge_face_add()
        elif action in {"SLICE", "SLICE_PLANE", "QUICK_SLICE"}:
            if action == "SLICE_PLANE":
                ob.max_poly.slice_plane = not ob.max_poly.slice_plane
                return {"FINISHED"}
            plane = settings(context, "SLICE_PLANE")
            normal = Vector((plane.normal_x, plane.normal_y, plane.normal_z))
            if not normal.length:
                operator.report({"WARNING"}, "Slice plane normal must not be zero")
                return {"CANCELLED"}
            from .operators import current_level
            faces = [f for f in bm.faces if not f.hide and (current_level(context) < 4 or f.select)]
            edges = {e for f in faces for e in f.edges if not e.hide}
            verts = {v for e in edges for v in e.verts if not v.hide}
            result = bmesh.ops.bisect_plane(bm, geom=list(verts) + list(edges) + faces,
                dist=0.00001, plane_co=(plane.plane_x, plane.plane_y, plane.plane_z), plane_no=normal)
            if plane.split:
                edges = [e for e in result["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
                bmesh.ops.split_edges(bm, edges=edges)
        elif action == "RESET_PLANE":
            plane = settings(context, "SLICE_PLANE")
            plane.plane_x = plane.plane_y = plane.plane_z = 0
            plane.normal_x = plane.normal_y = 0
            plane.normal_z = 1
        elif action == "ATTACH":
            others = [o for o in context.selected_objects if o != ob and o.type == "MESH"]
            if not others:
                operator.report({"WARNING"}, "Select another mesh before Attach, or use Attach List")
                return {"CANCELLED"}
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.join()
            bpy.ops.object.mode_set(mode="EDIT")
            return {"FINISHED"}
        elif action in {"COPY_SELECTION", "PASTE_SELECTION"}:
            seq = bm.verts if mode == "VERT" else bm.edges if mode == "EDGE" else bm.faces
            name = "max_named_selection_" + str(context.window_manager.max_sublevel)
            layer = seq.layers.int.get(name)
            if action == "COPY_SELECTION":
                layer = layer or seq.layers.int.new(name)
                for item in seq:
                    item[layer] = int(item.select)
            elif layer:
                ops.select_all(action="DESELECT")
                for item in seq:
                    item.select_set(bool(item[layer]) and not item.hide)
                bm.select_flush_mode()
            else:
                return {"CANCELLED"}
        elif action.startswith(("RING_SHIFT", "LOOP_SHIFT")):
            result = shift_edges(bm, action.startswith("RING"), 1 if action.endswith("UP") else -1)
            update_mesh(context)
            return result
        elif action == "SELECT_ANGLE":
            selected = {f for f in bm.faces if f.select}
            todo = list(selected)
            angle = math.radians(ob.max_poly.angle)
            while todo:
                f = todo.pop()
                for e in f.edges:
                    for other in e.link_faces:
                        if other not in selected and not other.hide and f.normal.angle(other.normal, math.pi) <= angle:
                            selected.add(other)
                            todo.append(other)
            for face in selected:
                face.select_set(True)
            bm.select_flush_mode()
        update_mesh(context)
    except (RuntimeError, ValueError, TypeError) as exc:
        operator.report({"WARNING"}, str(exc))
        return {"CANCELLED"}
    return {"FINISHED"}


class MAX_OT_poly_attach_list(Operator):
    """Choose a mesh and attach it to the active Editable Poly"""
    bl_idname = "max.poly_attach_list"
    bl_label = "Attach List"
    bl_options = {"REGISTER", "UNDO"}
    target: EnumProperty(name="Object", items=lambda s, c: [(o.name, o.name, "") for o in c.scene.objects if o.type == "MESH" and o != c.active_object])

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        ob = context.scene.objects.get(self.target)
        if ob is None:
            return {"CANCELLED"}
        active = context.active_object
        editing = context.mode == "EDIT_MESH"
        if editing:
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        active.select_set(True)
        ob.select_set(True)
        bpy.ops.object.join()
        if editing:
            bpy.ops.object.mode_set(mode="EDIT")
        return {"FINISHED"}


def sync_smoothing(bm, layer):
    for face in bm.faces:
        face.smooth = bool(face[layer])
    for edge in bm.edges:
        edge.smooth = len(edge.link_faces) == 2 and bool(edge.link_faces[0][layer] & edge.link_faces[1][layer])


class MAX_OT_poly_smoothing(Operator):
    """Assign or select persistent Max smoothing groups and update sharp edges"""
    bl_idname = "max.poly_smoothing"
    bl_label = "Smoothing Groups"
    bl_options = {"REGISTER", "UNDO"}
    action: EnumProperty(items=[(v, n, "") for v, n in (("TOGGLE", "Assign Group"), ("SELECT", "Select By SG"), ("CLEAR", "Clear All"), ("AUTO", "Auto Smooth"))])
    group: IntProperty(min=1, max=32, default=1)

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def execute(self, context):
        bm = bmesh.from_edit_mesh(context.active_object.data)
        layer = bm.faces.layers.int.get(SG_ATTRIBUTE) or bm.faces.layers.int.new(SG_ATTRIBUTE)
        faces = [f for f in bm.faces if f.select and not f.hide]
        p = context.active_object.max_poly
        if self.action == "TOGGLE":
            bit = 1 << (self.group - 1)
            remove = bool(faces) and all(f[layer] & bit for f in faces)
            for face in faces:
                value = (face[layer] & 0xffffffff) & ~bit if remove else (face[layer] & 0xffffffff) | bit
                face[layer] = value if value < 0x80000000 else value - 0x100000000
        elif self.action == "CLEAR":
            for face in faces:
                face[layer] = 0
        elif self.action == "SELECT":
            bit = 1 << (p.sg_select - 1)
            if p.sg_clear_selection:
                bpy.ops.mesh.select_all(action="DESELECT")
            for face in bm.faces:
                if not face.hide and face[layer] & bit:
                    face.select_set(True)
            bm.select_flush_mode()
        else:
            # Each smooth patch gets a group. Do not silently reuse a group after 32.
            remaining = set(faces)
            patches = []
            while remaining:
                patch = {remaining.pop()}
                todo = list(patch)
                while todo:
                    face = todo.pop()
                    for edge in face.edges:
                        for other in edge.link_faces:
                            if other in remaining and face.normal.angle(other.normal, math.pi) <= math.radians(p.auto_angle):
                                remaining.remove(other)
                                patch.add(other)
                                todo.append(other)
                patches.append(patch)
            if len(patches) > 32:
                self.report({"WARNING"}, "Auto Smooth needs more than 32 groups. Select a smaller region")
                return {"CANCELLED"}
            assigned = []
            used = 0
            selected = set(faces)
            for patch in patches:
                forbidden = used
                for face in patch:
                    for edge in face.edges:
                        for other in edge.link_faces:
                            if other not in selected and face.normal.angle(other.normal, math.pi) > math.radians(p.auto_angle):
                                forbidden |= other[layer] & 0xffffffff
                value = next((1 << i for i in range(32) if not forbidden & (1 << i)), None)
                if value is None:
                    self.report({"WARNING"}, "Auto Smooth has no free group that preserves the unselected hard boundaries")
                    return {"CANCELLED"}
                used |= value
                assigned.append((patch, value))
            for patch, value in assigned:
                for face in patch:
                    face[layer] = value if value < 0x80000000 else value - 0x100000000
        sync_smoothing(bm, layer)
        update_mesh(context)
        return {"FINISHED"}


class MAX_OT_poly_material(Operator):
    """Set or select a one-based Max material ID"""
    bl_idname = "max.poly_material"
    bl_label = "Material ID"
    bl_options = {"REGISTER", "UNDO"}
    action: EnumProperty(items=[("SET", "Set ID", ""), ("SELECT", "Select ID", ""), ("NAME", "Select by Name", "")])

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def execute(self, context):
        ob = context.active_object
        p = ob.max_poly
        bm = bmesh.from_edit_mesh(ob.data)
        idx = p.material_id - 1 if self.action == "SET" else int(p.material_name) if self.action == "NAME" else p.select_id - 1
        if self.action == "SET":
            # Empty slots preserve Max's IDs even without assigned materials.
            while len(ob.data.materials) <= idx:
                ob.data.materials.append(None)
            for face in bm.faces:
                if face.select:
                    face.material_index = idx
        else:
            if p.clear_selection:
                bpy.ops.mesh.select_all(action="DESELECT")
            for face in bm.faces:
                if face.material_index == idx and not face.hide:
                    face.select_set(True)
            bm.select_flush_mode()
        update_mesh(context)
        return {"FINISHED"}


class MAX_OT_poly_weight(Operator):
    """Set selected vertex/edge subdivision weight or crease"""
    bl_idname = "max.poly_weight"
    bl_label = "Set Weight / Crease"
    bl_options = {"REGISTER", "UNDO"}
    crease: BoolProperty(default=True)

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def execute(self, context):
        from .operators import current_level
        if not self.crease:
            self.report({"WARNING"}, "Blender subdivision has no Max vertex/edge weight parameter")
            return {"CANCELLED"}
        ob = context.active_object
        bm = bmesh.from_edit_mesh(ob.data)
        vertex = current_level(context) == 1
        seq = bm.verts if vertex else bm.edges
        name = "crease_vert" if vertex else "crease_edge"
        layer = seq.layers.float.get(name) or seq.layers.float.new(name)
        for item in seq:
            if item.select:
                item[layer] = ob.max_poly.crease
        update_mesh(context)
        return {"FINISHED"}


from . import target_weld, poly_modal

classes = poly_constraints.classes + target_weld.classes + poly_modal.classes + hsx_adapter_classes() + (MaxPolyOperation, MaxPolyState, MAX_OT_poly_settings, MAX_OT_poly_unavailable,
           MAX_OT_poly_attach_list, MAX_OT_poly_smoothing, MAX_OT_poly_material, MAX_OT_poly_weight)


def register_props():
    poly_caddies.register_handlers()
    bpy.types.Scene.max_poly_operations = CollectionProperty(type=MaxPolyOperation)
    bpy.types.Scene.max_poly_slice = PointerProperty(type=MaxPolyOperation)
    bpy.types.Object.max_poly = PointerProperty(type=MaxPolyState)
    poly_constraints.register_tools()


def unregister_props():
    poly_constraints.unregister_tools()
    poly_caddies.unregister_handlers()
    del bpy.types.Object.max_poly
    del bpy.types.Scene.max_poly_operations
    del bpy.types.Scene.max_poly_slice
