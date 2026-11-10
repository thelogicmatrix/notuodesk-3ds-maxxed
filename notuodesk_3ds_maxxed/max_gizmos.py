"""Shared Max Move, Rotate and Scale drawing and picking in viewport pixels."""

import math

import bpy
from bpy_extras import view3d_utils
from mathutils import Euler, Matrix, Vector

COLORS = ((1.0, .08, .045, 1), (.18, .95, .055, 1), (.12, .28, 1.0, 1))
YELLOW = (1.0, .92, .0, 1)
GREY = (.55, .55, .55, 1)
FILL = (1.0, .92, .0, .24)
# Autodesk 2026 Move/Scale state illustrations. Keep the approved Rotate
# palette separate from these sampled 8-bit colours.
TRANSFORM_COLORS = ((1, 0, 0, 1), (0, 200/255, 0, 1), (0, 0, 1, 1))
TRANSFORM_YELLOW = (242/255, 217/255, 0, 1)
SCREEN_RING_RATIO = 100/76
_active = {}
_hover = {}
_draw_handle = None


def tripod_color(axis, locked):
    return COLORS["XYZ".index(axis)] if axis in locked else GREY


def element_color(operation, element, handle, native, active, locked):
    """Highlight shafts/labels/regions, never Move cones or Scale point ends."""
    if operation == "ROTATE":
        return native
    highlighted = active if active != "OFF" else locked
    if operation == "MOVE" and highlighted == "XYZ":
        highlighted = "OFF"  # Unconstrained Move, not three selected handles.
    center = highlighted == "CENTER" or (operation == "SCALE" and highlighted == "XYZ")
    selected = (handle == highlighted or (handle == "CENTER" and center) or
                (len(handle) == 1 and (handle in highlighted or (operation == "SCALE" and center))))
    if element == "tip":
        return native
    if operation == "SCALE" and center and element == "shaft":
        return native  # Only the part inside the uniform volume turns yellow.
    if element == "fill":
        if not selected:
            return native
        if handle in {"XY", "YZ", "ZX"}:
            # A neutral overlay darkens the viewport into Max's grey plane.
            return (0, 0, 0, .32)
        return (*TRANSFORM_YELLOW[:3], .06)
    if operation == "MOVE" and handle == "CENTER":
        return TRANSFORM_YELLOW
    if operation == "SCALE" and element == "outline" and center:
        selected = True
    return TRANSFORM_YELLOW if selected else native


def plane_corners(operation, inner, outer):
    if operation == "MOVE":
        return ((0, 0), (outer, 0), (outer, outer), (0, outer))
    return ((inner, 0), (outer, 0), (0, outer), (0, inner))


def kind(context):
    from . import snaps
    return {"max.rotate": "ROTATE", "max.snap_move": "MOVE", "max.poly_move": "MOVE", "max.snap_scale": "SCALE"}.get(snaps._tool(context))


def _center(context, operation="ROTATE"):
    from . import max_rotate
    return max_rotate.transform_center(context, operation)


def centers(context, operation):
    from . import max_rotate
    s = max_rotate.settings(context)
    if s.multiple_gizmos and (max_rotate.center_mode(context,operation) == "PIVOT" or max_rotate.reference_name(context,operation) == "LOCAL") and context.mode == "OBJECT":
        return [ob.matrix_world.translation.copy() for ob in context.selected_objects]
    return [_center(context,operation)]


def geometries(context):
    operation = kind(context)
    if not operation:
        return []
    if context.region.as_pointer() in _active:
        return [geometry(context)]
    return [geometry(context,operation,center=center) for center in centers(context,operation)]


def pick_geometry(context, co):
    candidates = [data for data in geometries(context) if data is not None]
    hits = [data for data in candidates if hit_test(data,co) != "OFF"]
    return min(hits or candidates,key=lambda data:(data["xy"]-co).length_squared) if candidates else None


def geometry(context, operation=None, center=None, basis=None):
    """The same projected shapes drive drawing, hover and mouse-down picking."""
    from . import max_rotate, snaps
    operation = operation or kind(context)
    region, rv = context.region, context.region_data
    if not rv or not operation:
        return None
    state = _active.get(region.as_pointer())
    center = center if center is not None else (getattr(state,"display_center",state.gizmo_pivot) if state else _center(context, operation))
    basis = basis if basis is not None else (getattr(state,"display_basis",state.orientation) if state else
              max_rotate.reference_basis(context) if operation == "ROTATE" else snaps.orientation_basis(context))
    project = lambda p: view3d_utils.location_3d_to_region_2d(region, rv, p)
    xy = project(center)
    if xy is None:
        return None
    ui = context.preferences.system.ui_scale
    prefs = max_rotate.settings(context)
    radius = min(region.width, region.height) * .12 * prefs.size * getattr(prefs,operation.lower()+"_size") / 100
    radius *= context.preferences.view.ui_scale
    radius = max(36*ui, radius)
    world_radius = (view3d_utils.region_2d_to_location_3d(region, rv, xy+Vector((radius, 0)), center)-center).length
    view_basis = rv.view_rotation.to_matrix()
    data = dict(center=center, xy=xy, radius=radius, world_radius=world_radius, basis=basis,
                lines=[], faces=[], labels=[], rings={}, operation=operation, ui=ui, state=state,
                uniform_fraction=prefs.uniform_handle/100,
                label_height=radius*(6/76 if operation == "ROTATE" else 6/103))

    def line(handle, points, color, width=1.25, worlds=None):
        points = [project(p) for p in points]
        if all(p is not None for p in points):
            data["lines"].append((handle, points, color, width))
            if worlds is not None:
                data["rings"].setdefault(handle, []).extend(zip(points, worlds))

    if operation == "ROTATE":
        view_n = view_basis.col[2]
        for i, axis in enumerate(basis.col):
            u = axis.orthogonal().normalized()
            v = axis.cross(u).normalized()
            points = [center + world_radius * (u*math.cos(j*math.tau/128) + v*math.sin(j*math.tau/128)) for j in range(129)]
            handle = "XYZ"[i]
            for p, q in zip(points, points[1:]):
                if (p-center).dot(view_n) >= -world_radius*.025 or abs(axis.dot(view_n)) > .995:
                    line(handle, [p, q], COLORS[i], worlds=[p, q])
            end = project(center + axis*world_radius*.34)
            if end is not None and prefs.show_tripod:
                color = tripod_color(handle, max_rotate.constraint(context, operation))
                data["lines"].append(("TRIPOD_"+handle, [xy, end], color, 1))
                if prefs.show_labels:
                    data["labels"].append((handle, end+Vector((-radius*.025, radius*4/76)), color))
        for handle, size, color in (("FREE", 1, GREY), ("VIEW", SCREEN_RING_RATIO, GREY)):
            if (handle == "FREE" and not prefs.free_rotation) or (handle == "VIEW" and not prefs.screen_handle):
                continue
            points = [center + world_radius*size*(view_basis.col[0]*math.cos(j*math.tau/128) +
                          view_basis.col[1]*math.sin(j*math.tau/128)) for j in range(129)]
            line(handle, points, color, 1, worlds=points)
    else:
        endpoints = []
        for i, axis in enumerate(basis.col):
            key = "XYZ"[i]
            p = project(center + axis*world_radius)
            if p is None:
                continue
            endpoints.append(p)
            color = TRANSFORM_COLORS[i]
            shaft_end = project(center+axis*world_radius*.68) if operation == "MOVE" else p
            data["lines"].append((key, [xy, shaft_end], color, 1))
            direction = p-xy
            if direction.length > 1e-5:
                direction.normalize()
                side = Vector((-direction.y, direction.x))
                if operation == "MOVE":
                    # The long, narrow Max cone keeps its axis colour even when
                    # its shaft is yellow (Autodesk's selected-YZ illustration).
                    u = axis.orthogonal().normalized()*world_radius*.03
                    v = axis.cross(u).normalized()*world_radius*.03
                    base = center+axis*world_radius*.68
                    ring = [project(base+u*math.cos(j*math.tau/8)+v*math.sin(j*math.tau/8)) for j in range(8)]
                    for j in range(8):
                        if ring[j] is not None and ring[(j+1)%8] is not None:
                            data["faces"].append((key,[p,ring[j],ring[(j+1)%8]],color))
                else:
                    # Max Scale uses small point ends, not square box caps.
                    dot = [p+Vector((math.cos(j*math.tau/8),math.sin(j*math.tau/8)))*radius*.03 for j in range(8)]
                    data["faces"].append((key,dot,color))
                if prefs.show_labels:
                    data["labels"].append((key, p+direction*radius*.0883-Vector((data["label_height"]*.45, data["label_height"]*.4)), color))
        for i, j, key in ((0,1,"XY"), (1,2,"YZ"), (2,0,"ZX")):
            if operation == "MOVE" and not prefs.plane_handles:
                continue
            a, b = basis.col[i]*world_radius, basis.col[j]*world_radius
            inner = prefs.uniform_handle/100
            outer = prefs.plane_offset/100 if operation == "MOVE" else inner+prefs.two_axis_handle/100
            points = [center+a*x+b*y for x,y in plane_corners(operation,inner,outer)]
            poly = [project(p) for p in points]
            if all(p is not None for p in poly):
                data["faces"].append((key, poly, (0,0,0,0)))
                if operation == "MOVE":
                    # Only the connected outside corner is additional geometry.
                    data["lines"].append((key,poly[1:3],TRANSFORM_COLORS[i],1))
                    data["lines"].append((key,poly[2:4],TRANSFORM_COLORS[j],1))
                else:
                    # Each triangle edge carries its endpoint's axis colour
                    # to the midpoint. Shafts supply the two radial boundaries.
                    for a,b in ((poly[1],poly[2]),(poly[0],poly[3])):
                        middle = (a+b)*.5
                        data["lines"].append((key,[a,middle],TRANSFORM_COLORS[i],1))
                        data["lines"].append((key,[middle,b],TRANSFORM_COLORS[j],1))
        if operation == "MOVE":
            r = data["radius"]*.07
            poly = [xy+Vector(t) for t in ((-r,-r),(r,-r),(r,r),(-r,r))]
        else:
            poly = [project(center+axis*world_radius*prefs.uniform_handle/100) for axis in basis.col]
        if all(p is not None for p in poly) and (operation != "MOVE" or prefs.screen_move):
            data["faces"].append(("CENTER", poly, (0,0,0,0)))
            if operation == "MOVE":
                data["lines"].append(("CENTER", poly+[poly[0]], TRANSFORM_YELLOW, 1.25))
            # Scale's inner triangle shares the coloured plane edges above.
    return data


def segment_distance(co, a, b):
    delta = b-a
    t = min(1, max(0, (co-a).dot(delta)/delta.length_squared)) if delta.length_squared > 1e-10 else 0
    return (co-(a+delta*t)).length


def inside(co, poly):
    # Ray crossing also accepts a clockwise projected plane.
    result = False
    for a, b in zip(poly, poly[1:]+poly[:1]):
        if (a.y > co.y) != (b.y > co.y):
            if co.x < (b.x-a.x)*(co.y-a.y)/(b.y-a.y)+a.x:
                result = not result
    return result


def hit_test(data, co):
    if not data:
        return "OFF"
    if data["operation"] != "ROTATE":
        # Screen center wins over the overlapping projected planar regions.
        for handle, poly, color in reversed(data["faces"]):
            if inside(co, poly):
                return handle
    choices = []
    for handle, points, color, width in data["lines"]:
        if handle.startswith("TRIPOD_"):
            if data["operation"] == "ROTATE":
                continue
            handle = handle[-1]
        for a, b in zip(points, points[1:]):
            distance = segment_distance(co, a, b)
            if distance < 7*data["ui"]:
                # Inner tripod is a label, not a Rotate ring hit target.
                if data["operation"] == "ROTATE" and handle in "XYZ" and max((a-data["xy"]).length, (b-data["xy"]).length) < data["radius"]*.5:
                    continue
                choices.append((distance, handle))
    if choices:
        nearest = min(choices)
        if data['operation'] == 'ROTATE' and nearest[1] == 'FREE':
            # A principal-view axis circle can coincide with the Free outline.
            # Prefer the axis for subpixel ties, leaving the inner disk free.
            axes = [choice for choice in choices if choice[1] in {'X', 'Y', 'Z'}
                    and choice[0] <= nearest[0] + .5 * data['ui']]
            if axes:
                return min(axes)[1]
        return nearest[1]
    if data["operation"] == "ROTATE" and "FREE" in data["rings"] and (co-data["xy"]).length < data["radius"]:
        return "FREE"
    return "OFF"


def tangent(data, handle, co):
    """Positive rotation direction projected at the grabbed ring point."""
    from . import max_rotate
    if handle in {"X", "Y", "Z", "VIEW"} and data:
        samples = data["rings"].get(handle, [])
        if samples:
            xy, world = min(samples, key=lambda p: (p[0]-co).length_squared)
            radial = world-data["center"]
            rv = bpy.context.region_data
            axis = rv.view_rotation.to_matrix().col[2] if handle == "VIEW" else data["basis"].col["XYZ".index(handle)]
            moved = world+axis.cross(radial)*.05
            end = view3d_utils.location_3d_to_region_2d(bpy.context.region, rv, moved)
            if end is not None and (end-xy).length > 1e-5:
                return (end-xy).normalized(), radial
    return Vector((1, 0)), Vector((1, 0, 0))


def begin(context, operator, operation, pivot, orientation, handle):
    handle = "ZX" if handle == "XZ" else handle
    operator.operation = operation
    operator.gizmo_pivot = pivot.copy()
    operator.orientation = orientation.copy()
    operator.handle = handle
    operator._owner_context = (context.window, context.area, context.region)
    _active[context.region.as_pointer()] = operator


def finish(region):
    _active.pop(region.as_pointer(), None)
    _hover.pop(region.as_pointer(), None)


def pie_triangles(data, state):
    """Filled projected triangles, including complete turns before the remainder."""
    from . import max_rotate
    if not max_rotate.settings(bpy.context).show_pie or not hasattr(state, "angle_data"):
        return [], 0
    if state.handle == "FREE":
        rotation = Euler(state.angle_data,"XYZ").to_quaternion()
        angle = rotation.angle
        axis = state.orientation @ rotation.axis
        radial = axis.orthogonal().normalized()*data["world_radius"]
    elif state.handle in {"X","Y","Z","VIEW"}:
        index = 2 if state.handle == "VIEW" else "XYZ".index(state.handle)
        angle = state.angle_data[index]
        axis = state.view_basis.col[2] if state.handle == "VIEW" else state.orientation.col[index]
        radial = state.radial.normalized()*data["world_radius"]
    else:
        return [], 0
    if abs(angle) < 1e-7:
        return [], 0
    if state.handle == "VIEW":
        radial *= SCREEN_RING_RATIO
    turns = int(abs(angle)/math.tau)
    sweep = math.copysign(math.tau if turns else abs(angle), angle)
    count = max(2, int(abs(sweep)/math.tau*128)+1)
    rv, region = bpy.context.region_data, bpy.context.region
    arc = [view3d_utils.location_3d_to_region_2d(region, rv,
            state.pivot+Matrix.Rotation(sweep*j/count, 3, axis)@radial) for j in range(count+1)]
    tris = []
    for a, b in zip(arc, arc[1:]):
        if a is not None and b is not None:
            tris.extend((data["xy"], a, b))
    if turns > 1:
        # Repeated alpha blending makes each complete turn darker. Sixteen
        # layers already hide the background to within one 8-bit colour value.
        tris *= min(turns,16)
    # Full turns remain visible. The remainder overlays them, as in Autodesk's
    # -416.99 degree X example, rather than replacing the slice with a full disc.
    if turns and abs(angle) % math.tau > 1e-5:
        remainder = math.copysign(abs(angle) % math.tau, angle)
        arc = [view3d_utils.location_3d_to_region_2d(region, rv,
            state.pivot+Matrix.Rotation(remainder*j/count,3,axis)@radial) for j in range(count+1)]
        for a,b in zip(arc,arc[1:]):
            if a is not None and b is not None:
                tris.extend((data["xy"],a,b))
    return tris, .24


def _draw():
    context = bpy.context
    if not context.area or context.area.type != "VIEW_3D" or not context.region_data:
        return
    for data in geometries(context):
        if data:
            _draw_geometry(data)


def _draw_geometry(data):
    context = bpy.context
    if not context.area or context.area.type != "VIEW_3D" or not context.region_data:
        return
    if not context.space_data.show_gizmo or not context.selected_objects:
        return
    import blf
    import gpu
    from gpu_extras.batch import batch_for_shader
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    state = data["state"]
    active = state.handle if state else _hover.get(context.region.as_pointer(), "OFF")
    from . import max_rotate
    locked = max_rotate.constraint(context,data["operation"])
    highlighted = active if active != "OFF" else locked
    def selected(handle):
        return (handle == highlighted or (handle == "CENTER" and highlighted == "XYZ") or
                (data["operation"] != "ROTATE" and handle in {"X","Y","Z"} and handle in highlighted))
    def draw(mode, points, color):
        if not points:
            return
        shader.bind()
        shader.uniform_float("color", color)
        batch_for_shader(shader, mode, {"pos": [tuple(p) for p in points]}).draw(shader)
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")
    try:
        if state and data["operation"] == "ROTATE":
            tris, alpha = pie_triangles(data, state)
            index = "XYZ".find(state.handle)
            color = COLORS[index] if index >= 0 else GREY
            draw("TRIS", tris, (*color[:3], alpha))
            if tris:
                gpu.state.line_width_set(data["ui"])
                draw("LINES", [data["xy"],tris[1],data["xy"],tris[-1]],YELLOW)
        def draw_face(handle, poly, color):
            element = "tip" if len(handle) == 1 else "fill"
            rgba = element_color(data["operation"], element, handle, color, active, locked)
            tris = [p for i in range(1,len(poly)-1) for p in (poly[0],poly[i],poly[i+1])]
            draw("TRIS", tris, rgba)
        for handle, poly, color in data["faces"]:
            if len(handle) != 1:
                draw_face(handle, poly, color)
        # Shafts cover adjoining planar edges. Native-coloured ends cover shafts.
        for handle, points, color, width in sorted(data["lines"],key=lambda item:len(item[0]) == 1):
            gpu.state.line_width_set(width*data["ui"])
            if data["operation"] == "ROTATE":
                rgba = color if handle.startswith("TRIPOD_") else YELLOW if selected(handle) else color
            else:
                rgba = element_color(data["operation"], "shaft" if len(handle) == 1 else "outline",
                                     handle, color, active, locked)
            draw("LINE_STRIP", points, rgba)
            if data["operation"] == "SCALE" and len(handle) == 1 and highlighted in {"CENTER", "XYZ"}:
                inner = points[0].lerp(points[-1], data["uniform_fraction"])
                draw("LINE_STRIP", [points[0], inner], TRANSFORM_YELLOW)
        for handle, poly, color in data["faces"]:
            if len(handle) == 1:
                draw_face(handle, poly, color)
        for text, xy, color in data["labels"]:
            # Detailed Autodesk illustrations use 6-pixel axis labels at a
            # 76-pixel Rotate radius or roughly 103-pixel Move/Scale radius.
            height = data["label_height"]
            blf.size(0, height*2)
            blf.size(0, height*2*height/max(blf.dimensions(0, "z")[1], 1))
            blf.position(0, xy.x, xy.y, 0)
            blf.color(0, *element_color(data["operation"], "label", text, color, active, locked))
            blf.draw(0, text.lower())
        if state and hasattr(state, "angle_data") and max_rotate.settings(context).angle_data:
            # Autodesk's mid-drag reference shows the slice and angle data,
            # without the formerly invented 320-UI-pixel crossing guide.
            values = [math.degrees(v) for v in state.angle_data]
            text = "[%.2f, %.2f, %.2f]" % tuple(0 if abs(v)<.0001 else v for v in values)
            # CAE9185F: 95 x 11 px readout above a 76 px main ring.
            # Fit glyph dimensions, so UI scale does not change its proportions.
            # Rasterize at the reference radius, then scale both axes. Resizing
            # the font first changes hinted glyph bearings at each viewport size.
            size = 76*.2
            reference_text = "[-416.99, 0.00, 0.00]"
            blf.size(0, size)
            width, height = blf.dimensions(0, reference_text)
            blf.size(0, size*11/max(height, 1))
            width, height = blf.dimensions(0, reference_text)
            with gpu.matrix.push_pop():
                gpu.matrix.translate((data["xy"].x-data["radius"]*.375, data["xy"].y+data["radius"]*1.34, 0))
                gpu.matrix.scale((data["radius"]*95/76/max(width, 1),
                                  data["radius"]*11/76/max(height, 1), 1))
                blf.position(0, 0, 0, 0)
                blf.color(0, *YELLOW)
                blf.draw(0, text)
    finally:
        gpu.state.line_width_set(1)
        gpu.state.blend_set("NONE")


class MAX_GT_max_transform(bpy.types.Gizmo):
    bl_idname = "MAX_GT_max_transform"

    def draw(self, context):
        pass  # POST_PIXEL draws the shared Max set, without Blender's dial art.

    def test_select(self, context, location):
        if not context.space_data.show_gizmo:
            return -1
        handle = hit_test(pick_geometry(context,Vector(location)), Vector(location))
        key = context.region.as_pointer()
        if _hover.get(key) != handle:
            _hover[key] = handle
            context.area.tag_redraw()
        return 0 if handle != "OFF" else -1


class MAX_GGT_max_transform(bpy.types.GizmoGroup):
    bl_idname = "MAX_GGT_max_transform"
    bl_label = "Max Transform Gizmo"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT"}

    @classmethod
    def poll(cls, context):
        return bool(kind(context) and context.selected_objects and context.space_data.show_gizmo)

    def setup(self, context):
        handle = self.gizmos.new("MAX_GT_max_transform")
        handle.use_tooltip = False
        handle.target_set_operator("max.gizmo_drag")


class MAX_OT_gizmo_drag(bpy.types.Operator):
    bl_idname = "max.gizmo_drag"
    bl_label = "Max Transform Gizmo"
    bl_description = "Drag an axis or plane to transform the selection"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        operation = kind(context)
        hit = hit_test(pick_geometry(context,Vector((event.mouse_region_x,event.mouse_region_y))), Vector((event.mouse_region_x,event.mouse_region_y)))
        if operation == "ROTATE":
            return bpy.ops.max.rotate("INVOKE_DEFAULT", handle=hit)
        return bpy.ops.max.snap_transform("INVOKE_DEFAULT", kind=operation, from_gizmo=True,
                    constraint_axis=tuple(c in hit for c in "XYZ"), screen_plane=hit == "CENTER" and operation == "MOVE")


classes = (MAX_GT_max_transform, MAX_GGT_max_transform, MAX_OT_gizmo_drag)


def register():
    global _draw_handle
    if not bpy.app.background:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_PIXEL")
    if cancel_all not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(cancel_all)


@bpy.app.handlers.persistent
def cancel_all(*_):
    """Restore transactions while their operators and properties still exist."""
    for owner in list(_active.values()):
        context = getattr(owner, "_owner_context", None)
        if context:
            window, area, region = context
            with bpy.context.temp_override(window=window, area=area, region=region):
                owner._finish(bpy.context, True)
        else:
            owner.tx.cancel()
            if owner.clone:
                owner.clone.cancel()
            owner._closed = True
    _active.clear()
    _hover.clear()


def unregister():
    global _draw_handle
    cancel_all()
    if cancel_all in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(cancel_all)
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, "WINDOW")
        _draw_handle = None
    _active.clear()
    _hover.clear()
