"""Construction-plane creation sessions and supported object catalogues."""

import math
import random

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector

from . import extended_primitives, prims

PRIMITIVES = prims.PRIMITIVES

SHAPES = tuple((key, label, icon) for key, label, icon in (
    ('LINE', 'Line', 'CURVE_PATH'), ('RECTANGLE', 'Rectangle', 'MESH_PLANE'),
    ('CIRCLE', 'Circle', 'CURVE_BEZCIRCLE'), ('ELLIPSE', 'Ellipse', 'CURVE_BEZCIRCLE'),
    ('ARC', 'Arc', 'CURVE_BEZCURVE'), ('NGON', 'NGon', 'MESH_CIRCLE'),
    ('STAR', 'Star', 'SOLO_ON'), ('TEXT', 'Text', 'FONT_DATA'), ('HELIX', 'Helix', 'CURVE_SPIRAL')))
LIGHTS = (('TARGET_SPOT', 'Target Spot', 'LIGHT_SPOT'), ('FREE_SPOT', 'Free Spot', 'LIGHT_SPOT'),
          ('TARGET_DIRECT', 'Target Direct', 'LIGHT_SUN'), ('FREE_DIRECT', 'Free Direct', 'LIGHT_SUN'),
          ('OMNI', 'Omni', 'LIGHT_POINT'), ('AREA', 'Area', 'LIGHT_AREA'), ('SKYLIGHT', 'Skylight', 'WORLD'))
HELPERS = (('DUMMY', 'Dummy', 'EMPTY_DATA'), ('POINT', 'Point', 'EMPTY_AXIS'),
           ('SPHERE', 'Sphere Gizmo', 'SPHERE'), ('CIRCLE', 'Circle Gizmo', 'MESH_CIRCLE'),
           ('CONE', 'Cone Gizmo', 'CONE'))
STANDARD_ORDER = ('BOX', 'CONE', 'SPHERE', 'GEOSPHERE', 'CYLINDER', 'TUBE', 'TORUS',
                  'PYRAMID', 'TEAPOT', 'PLANE', 'TEXTPLUS')
EXTENDED_ORDER = ('HEDRA', 'TORUS_KNOT', 'CHAMFERBOX', 'CHAMFERCYL', 'OILTANK',
                  'CAPSULE', 'SPINDLE', 'L_EXT', 'GENGON', 'C_EXT', 'RINGWAVE', 'PRISM', 'HOSE', 'SPRING', 'DAMPER')
_running = []
_ui_hosts = {}
CATEGORIES = (('GEOMETRY', 'Geometry'), ('SHAPES', 'Shapes'), ('LIGHTS', 'Lights'),
              ('CAMERAS', 'Cameras'), ('HELPERS', 'Helpers'), ('SPACE_WARPS', 'Space Warps'),
              ('SYSTEMS', 'Systems'))


def construction_frame(rv3d):
    if rv3d is None or rv3d.is_perspective:
        return Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
    facing = rv3d.view_rotation @ Vector((0, 0, 1))
    horizontal = rv3d.view_rotation @ Vector((1, 0, 0))
    axis = max(range(3), key=lambda i: abs(facing[i]))
    n = Vector(tuple((1 if facing[i] >= 0 else -1) if i == axis else 0 for i in range(3)))
    side = max((i for i in range(3) if i != axis), key=lambda i: abs(horizontal[i]))
    u = Vector(tuple((1 if horizontal[i] >= 0 else -1) if i == side else 0 for i in range(3)))
    return u, n.cross(u), n


def region_under_mouse(context, x, y):
    screen = context.window.screen if context.window else context.screen
    if screen:
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            # Reject sidebars which can overlap the drawable region.
            if any(r.type in {'UI', 'TOOLS', 'HEADER', 'TOOL_HEADER'} and
                   r.width > 1 and r.height > 1 and r.x <= x < r.x+r.width and r.y <= y < r.y+r.height
                   for r in area.regions):
                continue
            for region in area.regions:
                if region.type == 'WINDOW' and region.x <= x < region.x+region.width and region.y <= y < region.y+region.height:
                    return area, region
    return None, None


def mouse_ray(region, rv3d, co):
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, co)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, co)
    return origin, direction


def ray_plane(region, rv3d, co, point, normal):
    origin, direction = mouse_ray(region, rv3d, co)
    divisor = direction.dot(normal)
    if abs(divisor) < 1e-9:
        return None
    hit = origin + direction * ((Vector(point) - origin).dot(normal) / divisor)
    return hit if all(math.isfinite(c) for c in hit) else None


def ray_line_height(region, rv3d, co, base, axis):
    origin, direction = mouse_ray(region, rv3d, co)
    axis = Vector(axis).normalized()
    cross = direction.dot(axis)
    denominator = 1 - cross * cross
    if abs(denominator) > 1e-8:
        delta = origin - base
        return (delta.dot(axis) - cross * delta.dot(direction)) / denominator
    screen = view3d_utils.location_3d_to_region_2d(region, rv3d, base)
    if screen is None:
        return 0.0
    a = view3d_utils.region_2d_to_location_3d(region, rv3d, screen, base)
    b = view3d_utils.region_2d_to_location_3d(region, rv3d, screen + Vector((0, 1)), base)
    return (co[1] - screen.y) * (b - a).length


def new_object(context, name, data):
    if context.mode != 'OBJECT' and context.object:
        bpy.ops.object.mode_set(mode='OBJECT')
    for selected in context.selected_objects:
        selected.select_set(False)
    ob = bpy.data.objects.new(name, data)
    collection = context.collection or context.scene.collection
    collection.objects.link(ob)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    ob.color = random_color()
    return ob


def random_color():
    return (*[random.uniform(.25, .85) for _ in range(3)], 1)


def _name(label):
    from .operators import max_name
    return max_name(label)


def _finish(context, ob):
    from .poly_tools import finalize_new_object
    finalize_new_object(context, ob)


def _session_end(context=None):
    MAX_OT_create._session += 1
    MAX_OT_create.active_kind = ''
    for tool in list(_running):
        tool._discard()
        if context and tool.timer is not None:
            context.window_manager.event_timer_remove(tool.timer)
            tool.timer = None
        _running.remove(tool)
    if context and context.window:
        context.window.cursor_modal_restore()
    from . import snaps
    snaps.clear_preview()


@persistent
def _load_reset(_):
    _session_end(bpy.context)


class MAX_OT_create(bpy.types.Operator):
    """Drag the base, then click to set each remaining dimension. Right-click ends creation"""
    bl_idname = 'max.create'
    bl_label = 'Create Primitive'
    bl_options = {'REGISTER', 'BLOCKING'}

    kind: EnumProperty(items=[(key, value[0], '') for key, value in prims.PRIMITIVES.items() if key != 'PLANEPLUS'])
    segments: IntProperty(default=24, min=3, max=256)
    active_kind = ''
    _session = 0

    def invoke(self, context, event):
        from . import keyboard_entry
        _session_end(context)
        self.session = MAX_OT_create._session
        MAX_OT_create.active_kind = self.kind
        keyboard_entry.remember_kind(context, self.kind)
        self.obj = None
        self.state = 'WAIT'
        self.stage_index = -1
        self.window = context.window
        self.screen = context.window.screen
        context.window.cursor_modal_set('CROSSHAIR')
        self.timer = context.window_manager.event_timer_add(.2, window=context.window)
        _running.append(self)
        register()
        context.window_manager.modal_handler_add(self)
        self._status(context)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        label = prims.PRIMITIVES[self.kind][0]
        ob = new_object(context, _name(label), bpy.data.meshes.new(label))
        prims.set_params(ob, self.kind)
        _finish(context, ob)
        if context.window:
            bpy.ops.ed.undo_push(message='Create ' + label)
        return {'FINISHED'}

    def _redraw(self, context):
        for area in context.screen.areas:
            area.tag_redraw()

    def _status(self, context):
        from . import snaps
        message = ('Click and drag the base. Right-click to leave creation' if self.state == 'WAIT' else
                   'Release to accept the base' if self.state == 'BASE' else
                   'Move to set ' + self.stage_prop.replace('_', ' ') + ', click to accept. Right-click cancels')
        if self.state != 'WAIT':
            message = snaps._prompts.get(self.region.as_pointer(), message)
        context.workspace.status_text_set(message)

    def _co(self, event):
        return Vector((event.mouse_x - self.region.x, event.mouse_y - self.region.y))

    def _base_point(self, context, event):
        from . import snaps
        co = self._co(event)
        point = ray_plane(self.region, self.rv3d, co, Vector(), self.n)
        if point is None:
            return None
        return snaps.snap_point(context, self.region, self.rv3d, co, point, (Vector(), self.n),
                                exclude=(self.obj,) if self.obj else (), base=self.p0,
                                commit=event.type == 'LEFTMOUSE')

    def _footprint(self, context, event):
        from . import keyboard_entry
        point = self._base_point(context, event)
        if point is None:
            return
        center, size = keyboard_entry.base_size(self.kind, self.creation_method, self.p0, point, self.u, self.v, .0001)
        values = dict(width=size.x, length=size.y, height=size.z, radius1=size.x)
        if self.kind == 'TORUS':
            values['radius2'] = size.x * .25
        if self.kind == 'TUBE':
            values['radius2'] = size.x * .75
        if self.kind == 'CONE':
            values['radius2'] = 0
        if self.kind == 'PRISM':
            values.update(side1=size.x, side2=math.hypot(size.x*.5, size.y), side3=math.hypot(size.x*.5, size.y))
        if self.kind in {'L_EXT', 'C_EXT'}:
            values.update(front_length=size.x, back_length=size.x, side_length=size.y,
                          side_width=min(size.x, size.y)*.2, front_width=min(size.x, size.y)*.2,
                          back_width=min(size.x, size.y)*.2)
            center -= self.u * size.x / 2 + self.v * size.y / 2
        prims.set_params(self.obj, self.kind, **values)
        self.obj.matrix_world = Matrix.Translation(center) @ Matrix((self.u, self.v, self.n)).transposed().to_4x4()
        self.footprint_valid = (point - self.p0).length > 1e-5
        self._redraw(context)

    def _next_creation_stage(self, context, event):
        if getattr(self, 'stage_prop', '') == 'height' and self.obj.max_prim.height == 0:
            context.workspace.status_text_set('Set a non-zero height, or right-click to cancel')
            return
        from . import snaps
        snaps.consume_override(context)
        stages = extended_primitives.STAGES.get(self.kind)
        if stages is None:
            stages = {'CONE': ('height', 'radius2'), 'TUBE': ('radius2', 'height'),
                      'TORUS': ('radius2',)}.get(self.kind, ('height',) if prims.PRIMITIVES[self.kind][3] else ())
            if getattr(self, 'creation_method', '') == 'CUBE':
                stages = ()
        self.stage_index += 1
        if self.stage_index >= len(stages):
            self._bake(context)
            self.state = 'WAIT'
            self._status(context)
            return
        self.stage_prop = stages[self.stage_index]
        self.state = 'DIMENSION'
        if event:
            self.release_co = self._co(event)
        self._status(context)

    def _update_creation_stage(self, context, event):
        from . import snaps
        co = self._co(event)
        a = view3d_utils.region_2d_to_location_3d(self.region, self.rv3d, self.release_co, self.p0)
        b = view3d_utils.region_2d_to_location_3d(self.region, self.rv3d, co, self.p0)
        value = (b - a).length * (-1 if co.y < self.release_co.y else 1)
        unit = view3d_utils.region_2d_to_location_3d(self.region, self.rv3d, self.release_co + Vector((0, 1)), self.p0)
        pixels = 1 / max((unit - a).length, 1e-8)
        if (self.stage_prop == 'height' and self.rv3d.is_perspective
                and abs((self.rv3d.view_rotation @ Vector((0, 0, 1))).dot(self.n)) < .97):
            value = ray_line_height(self.region, self.rv3d, co, self.obj.matrix_world.translation, self.n)
            pixels = None
        point = self.p0 + self.n * value
        point = snaps.snap_point(context, self.region, self.rv3d, co, point, (self.p0, self.n),
                                 exclude=(self.obj,), base=self.p0, axis=self.n, pixels_per_unit=pixels,
                                 commit=event.type == 'LEFTMOUSE')
        value = (point - self.p0).dot(self.n)
        p = self.obj.max_prim
        if self.stage_prop == 'wall_width':
            token = self.obj.as_pointer()
            prims._busy.add(token)
            try:
                p.side_width = p.front_width = p.back_width = max(abs(value), .0001)
            finally:
                prims._busy.discard(token)
            prims.rebuild(self.obj)
        else:
            setattr(p, self.stage_prop, value if self.stage_prop == 'height' else abs(value))
        self._redraw(context)

    def _bake(self, context):
        from . import snaps
        _finish(context, self.obj)
        self.obj = None
        snaps.consume_override(context)
        snaps.clear_preview()
        if context.window:
            bpy.ops.ed.undo_push(message='Create ' + prims.PRIMITIVES[self.kind][0])

    def _discard(self):
        try:
            if self.obj and self.obj.name in bpy.data.objects:
                mesh = self.obj.data
                bpy.data.objects.remove(self.obj, do_unlink=True)
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
        except ReferenceError:
            pass
        self.obj = None

    def _leave(self, context):
        self._discard()
        if self.timer is not None:
            context.window_manager.event_timer_remove(self.timer)
            self.timer = None
        if self in _running:
            _running.remove(self)
        if self.session == MAX_OT_create._session:
            _session_end(context)
            context.workspace.status_text_set(None)
        return {'FINISHED'}

    def modal(self, context, event):
        if self.session != MAX_OT_create._session or context.window.screen != self.screen:
            return self._leave(context)
        from . import snaps
        if snaps.override_event(self, context, event, dragging=self.state != 'WAIT'):
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            if self.obj:
                self._discard()
                self.state = 'WAIT'
                self._status(context)
                return {'RUNNING_MODAL'}
            return self._leave(context)
        if event.type == 'TIMER':
            return {'RUNNING_MODAL'}
        if self.state == 'WAIT' and event.ctrl and event.type == 'Z':
            return {'PASS_THROUGH'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} or event.type.startswith('NDOF'):
            return {'PASS_THROUGH'}
        area, region = region_under_mouse(context, event.mouse_x, event.mouse_y)
        if region is None or self.state != 'WAIT' and region != self.region:
            if self.state == 'BASE' and event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self._discard()
                self.state = 'WAIT'
                self._status(context)
            return {'PASS_THROUGH'}
        if self.state == 'WAIT' and event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            from . import keyboard_entry, snaps
            self.region, self.rv3d = region, region.data
            self.u, self.v, self.n = construction_frame(self.rv3d)
            self.p0 = None
            point = self._base_point(context, event)
            if point is None:
                return {'RUNNING_MODAL'}
            self.p0 = point
            self.creation_method = keyboard_entry.method(context, self.kind)
            label = prims.PRIMITIVES[self.kind][0]
            self.obj = new_object(context, _name(label), bpy.data.meshes.new(label))
            self.footprint_valid = False
            self.stage_index = -1
            self.stage_prop = ''
            self.state = 'BASE'
            self._footprint(context, event)
            self._status(context)
        elif self.state == 'BASE':
            if event.type == 'MOUSEMOVE':
                self._footprint(context, event)
            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self._footprint(context, event)
                if not self.footprint_valid:
                    self._discard()
                    self.state = 'WAIT'
                else:
                    self.release_co = self._co(event)
                    self._next_creation_stage(context, event)
        elif self.state == 'DIMENSION':
            if event.type == 'MOUSEMOVE':
                self._update_creation_stage(context, event)
            elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                self._update_creation_stage(context, event)
                self._next_creation_stage(context, event)
        return {'RUNNING_MODAL'}


class MAX_OT_create_shape(bpy.types.Operator):
    """Create a supported spline on the construction grid"""
    bl_idname = 'max.create_shape'
    bl_label = 'Create Shape'
    bl_options = {'REGISTER', 'UNDO'}
    kind: EnumProperty(items=[(kind, label, '') for kind, label, icon in SHAPES])
    radius: FloatProperty(default=1, min=.001)
    sides: IntProperty(default=6, min=3, max=64)

    def invoke(self, context, event):
        if self.kind == 'LINE':
            return bpy.ops.max.line('INVOKE_DEFAULT')
        return self.execute(context)

    def execute(self, context):
        if self.kind == 'LINE':
            self.report({'INFO'}, 'Use the Line tool in a viewport to place knots')
            return {'CANCELLED'}
        _session_end(context)
        from . import line_tool
        line_tool.finish_line(context)
        context.window_manager.max_line.shape_kind = self.kind
        label = dict((k, label) for k, label, _ in SHAPES)[self.kind]
        data = bpy.data.curves.new(label, 'FONT' if self.kind == 'TEXT' else 'CURVE')
        data.dimensions = '2D' if self.kind == 'TEXT' else '3D'
        if self.kind == 'TEXT':
            data.body = 'MAX Text'
        else:
            radius = self.radius
            count = self.sides if self.kind == 'NGON' else 10 if self.kind == 'STAR' else 97 if self.kind == 'HELIX' else 33
            if self.kind == 'RECTANGLE':
                points = [(-radius, -radius, 0), (radius, -radius, 0), (radius, radius, 0), (-radius, radius, 0)]
            else:
                points = []
                for i in range(count):
                    angle = (math.pi * i / (count-1) if self.kind == 'ARC' else math.tau * 3*i/(count-1) if self.kind == 'HELIX' else math.tau*i/count)
                    r = radius * (.5 if self.kind == 'STAR' and i % 2 else 1)
                    points.append((r*math.cos(angle), r*math.sin(angle) * (.5 if self.kind == 'ELLIPSE' else 1),
                                   2*radius*i/(count-1) if self.kind == 'HELIX' else 0))
            spline = data.splines.new('POLY')
            spline.points.add(len(points)-1)
            for vertex, co in zip(spline.points, points):
                vertex.co = (*co, 1)
            spline.use_cyclic_u = self.kind not in {'ARC', 'HELIX'}
        ob = new_object(context, _name(label), data)
        from .keyboard_entry import active_frame
        u, v, n = active_frame(context)
        ob.matrix_world = Matrix((u, v, n)).transposed().to_4x4()
        _finish(context, ob)
        return {'FINISHED'}


def _target(context, ob):
    target = bpy.data.objects.new(_name(ob.name.rstrip('0123456789') + ' Target'), None)
    (context.collection or context.scene.collection).objects.link(target)
    target.empty_display_type = 'PLAIN_AXES'
    target.location = (0, 0, -5)
    constraint = ob.constraints.new('TRACK_TO')
    constraint.target = target
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'


class MAX_OT_create_light(bpy.types.Operator):
    """Create a standard light equivalent. Area uses the available renderer's area light"""
    bl_idname = 'max.create_light'
    bl_label = 'Create Light'
    bl_options = {'REGISTER', 'UNDO'}
    kind: EnumProperty(items=[(k, label, '') for k, label, _ in LIGHTS])

    def execute(self, context):
        label = next(label for kind, label, _ in LIGHTS if kind == self.kind)
        if self.kind == 'SKYLIGHT':
            world = context.scene.world or bpy.data.worlds.new('Skylight')
            context.scene.world = world
            world.use_nodes = True
            background = next((node for node in world.node_tree.nodes if node.type == 'BACKGROUND'), None)
            if background:
                background.inputs['Color'].default_value = (.6, .7, 1, 1)
                background.inputs['Strength'].default_value = 1
            return {'FINISHED'}
        light_type = 'SPOT' if 'SPOT' in self.kind else 'SUN' if 'DIRECT' in self.kind else 'POINT' if self.kind == 'OMNI' else 'AREA'
        data = bpy.data.lights.new(label, light_type)
        data.energy = 1000 if light_type != 'SUN' else 1
        ob = new_object(context, _name(label), data)
        if self.kind.startswith('TARGET_'):
            _target(context, ob)
        return {'FINISHED'}


class MAX_OT_create_camera(bpy.types.Operator):
    """Create a free camera or a camera with a separately selectable target"""
    bl_idname = 'max.create_camera'
    bl_label = 'Create Camera'
    bl_options = {'REGISTER', 'UNDO'}
    target: BoolProperty(default=True)

    def execute(self, context):
        label = 'Target Camera' if self.target else 'Free Camera'
        ob = new_object(context, _name(label), bpy.data.cameras.new(label))
        if self.target:
            _target(context, ob)
        return {'FINISHED'}


class MAX_OT_create_helper(bpy.types.Operator):
    """Create a supported helper. ExposeTM is unavailable"""
    bl_idname = 'max.create_helper'
    bl_label = 'Create Helper'
    bl_options = {'REGISTER', 'UNDO'}
    kind: EnumProperty(items=[(k, label, '') for k, label, _ in HELPERS] + [('ARROWS', 'ExposeTM (unavailable)', '')])

    def execute(self, context):
        if self.kind == 'ARROWS':
            self.report({'WARNING'}, 'ExposeTM is unavailable')
            return {'CANCELLED'}
        label = next(label for key, label, _ in HELPERS if key == self.kind)
        ob = new_object(context, _name(label), None)
        ob.empty_display_type = {'DUMMY': 'CUBE', 'POINT': 'PLAIN_AXES', 'SPHERE': 'SPHERE',
                                 'CIRCLE': 'CIRCLE', 'CONE': 'CONE'}[self.kind]
        return {'FINISHED'}


def draw_object_types(layout, context):
    """Wave-2 Object Type callback with ordered, truthful disabled entries."""
    wm = context.window_manager
    layout.operator_context = 'INVOKE_DEFAULT'
    category, family = wm.max_create_cat, wm.max_create_sub
    if category == 'GEOMETRY' and family in {'STANDARD', 'EXTENDED'}:
        order = STANDARD_ORDER if family == 'STANDARD' else EXTENDED_ORDER
        items = [(key, prims.PRIMITIVES[key][0] if key in prims.PRIMITIVES else
                  {'TEXTPLUS': 'TextPlus', 'TEAPOT': 'Teapot', 'RINGWAVE': 'RingWave'}.get(key, key.title()),
                  'max.create', 'kind', key in prims.PRIMITIVES) for key in order]
    elif category == 'SHAPES':
        order = ('LINE', 'RECTANGLE', 'CIRCLE', 'ELLIPSE', 'ARC', 'DONUT', 'NGON', 'STAR', 'TEXT', 'HELIX', 'EGG', 'SECTION', 'FREEHAND')
        supported = {key: label for key, label, _ in SHAPES}
        items = [(key, supported.get(key, key.title()), 'max.create_shape', 'kind', key in supported) for key in order]
    elif category == 'LIGHTS':
        items = [(key, label, 'max.create_light', 'kind', True) for key, label, _ in LIGHTS]
    elif category == 'CAMERAS':
        items = [(True, 'Target Camera', 'max.create_camera', 'target', True), (False, 'Free Camera', 'max.create_camera', 'target', True)]
    elif category == 'HELPERS':
        items = [(key, label, 'max.create_helper', 'kind', True) for key, label, _ in HELPERS]
        items.extend([('ARROWS', 'ExposeTM', 'max.create_helper', 'kind', False), ('TAPE', 'Tape', 'max.create_helper', 'kind', False)])
    else:
        layout.label(text='No supported creator in this family')
        return
    if category in {'GEOMETRY', 'SHAPES'}:
        row = layout.row()
        row.enabled = False
        row.label(text='AutoGrid (unavailable)', icon='CHECKBOX_DEHLT')
    for index in range(0, len(items), 2):
        row = layout.row(align=True)
        for key, label, route, prop, enabled in items[index:index+2]:
            cell = row.row(align=True)
            cell.enabled = enabled
            operator = cell.operator(route, text=label)
            if enabled:
                setattr(operator, prop, key)


def install_ui(host):
    """Install Object Type and Parameters through the host's rollout/when adapter."""
    if id(host) in _ui_hosts:
        return _ui_hosts[id(host)][1]
    before = set(getattr(host, 'ROLLOUTS', ()))
    register()
    host.rollout('Object Type', {'CREATE'}, 20)(draw_object_types)

    @host.rollout('Name and Color', {'CREATE'}, 30)
    @host.when(lambda context: context.object is not None)
    def creation_name_color(layout, context):
        row = layout.row(align=True)
        row.prop(context.object, 'name', text='')
        row.prop(context.object, 'color', text='')

    from . import keyboard_entry
    host.rollout('Creation Method', {'CREATE'}, 40)(host.when(keyboard_entry.visible)(keyboard_entry.draw_method))
    host.rollout('Keyboard Entry', {'CREATE'}, 50, closed=True)(host.when(keyboard_entry.visible)(keyboard_entry.draw_keyboard))

    @host.rollout('Parameters', {'CREATE', 'MODIFY'}, 60)
    @host.when(lambda context: context.object is not None and context.object.type == 'MESH' and bool(context.object.max_prim.kind) and
               (context.window_manager.max_cmd_tab == 'MODIFY' or context.window_manager.max_create_cat == 'GEOMETRY'))
    def creation_parameters(layout, context):
        prims.draw(layout, context.object)
    installed = tuple(cls for cls in getattr(host, 'ROLLOUTS', ()) if cls not in before)
    _ui_hosts[id(host)] = (host, installed)
    return installed


def uninstall_ui(host):
    entry = _ui_hosts.pop(id(host), None)
    if entry is None:
        return
    for cls in reversed(entry[1]):
        if getattr(bpy.types, cls.__name__, None) is cls:
            bpy.utils.unregister_class(cls)
        if cls in host.ROLLOUTS:
            host.ROLLOUTS.remove(cls)


classes = (MAX_OT_create, MAX_OT_create_shape, MAX_OT_create_light, MAX_OT_create_camera, MAX_OT_create_helper)


def register():
    if _load_reset not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_load_reset)


def unregister():
    _session_end(bpy.context)
    for host, installed in list(_ui_hosts.values()):
        uninstall_ui(host)
    if _load_reset in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_load_reset)
