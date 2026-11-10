"""Max Symmetry parameters and its movable Mirror sub-object."""
import uuid

import bpy
from bpy.app.handlers import persistent
from bpy.props import EnumProperty, StringProperty
from mathutils import Matrix, Vector
from . import symmetry_nodes

HELPER = 'max_symmetry_plane'
STATE = 'max_symmetry_planes'
COLLECTION = '.3ds Maxxed Symmetry'
_draw_handle = None
_enabled = False
_busy = False

_INPUTS = {'use_axis': 'Axes', 'use_bisect_flip_axis': 'Flips',
           'slice': 'Slice', 'bisect_threshold': 'Slice Threshold',
           'use_mirror_merge': 'Weld', 'weld': 'Weld',
           'merge_threshold': 'Weld Threshold', 'proximity': 'Proximity',
           'radial': 'Radial', 'count': 'Count', 'radial_axis': 'Radial Axis',
           'mirror_symmetry': 'Mirror Symmetry', 'radial_flip': 'Radial Flip'}


def raw(mod):
    return mod.mod if isinstance(mod, Settings) else mod


def plane(mod):
    mod = raw(mod)
    if mod.type == 'MIRROR':
        return mod.mirror_object
    return mod.node_group.nodes['Mirror frame'].inputs['Object'].default_value


class Settings:
    """Named parameters backed by saved native modifier sockets."""
    def __init__(self, mod):
        object.__setattr__(self, 'mod', raw(mod))

    def path(self, key):
        name = _INPUTS[key]
        socket = next(s for s in self.mod.node_group.interface.items_tree
                      if s.item_type == 'SOCKET' and s.in_out == 'INPUT' and s.name == name)
        return socket.identifier

    def __getattr__(self, key):
        if key == 'mirror_object':
            return plane(self.mod)
        if key == 'use_bisect_axis':
            return (self.slice,)*3
        if key in _INPUTS:
            return self.mod[self.path(key)]
        return getattr(self.mod, key)

    def __setattr__(self, key, value):
        if key == 'use_bisect_axis':
            self.slice = any(value)
        elif key in _INPUTS:
            if key in {'use_axis', 'use_bisect_flip_axis'}:
                value = tuple(float(x) for x in value)
            self.mod[self.path(key)] = value
            self.mod.id_data.update_tag()
        else:
            setattr(self.mod, key, value)

    def prop(self, layout, key, **kwargs):
        layout.prop(self.mod, '["'+self.path(key)+'"]', **kwargs)


def settings(mod):
    return Settings(mod)


def is_symmetry(mod):
    mod = raw(mod)
    if mod is not None and mod.type == 'NODES':
        return bool(mod.node_group and mod.node_group.get(symmetry_nodes.MARKER))
    if mod is None or mod.type != 'MIRROR':
        return False
    if mod.mirror_object is not None and mod.mirror_object.get(HELPER):
        return True
    uid = int(getattr(mod, 'persistent_uid', 0))
    return bool(uid and any(rec.get('uid') == uid for rec in _records(mod.id_data).values()))


def owner(context):
    ob = context.view_layer.objects.active
    if ob is not None and ob.get(HELPER):
        return ob.get('owner')
    return ob


def editing(context):
    ob = context.view_layer.objects.active
    return ob is not None and bool(ob.get(HELPER))


def _matrix_values(plane):
    return [v for row in plane.matrix_basis for v in row]


def _records(ob):
    data = ob.get(STATE)
    return data.to_dict() if data is not None else {}


def _collection():
    return next((c for c in bpy.data.collections if c.get(HELPER)), None)


def _remember(ob, mod):
    plane = settings(mod).mirror_object
    records = _records(ob)
    record = dict(name=mod.name, matrix=_matrix_values(plane),
                  uid=int(getattr(mod, 'persistent_uid', 0)))
    if records.get(plane['token']) != record:
        records[plane['token']] = record
        ob[STATE] = records


def _new_plane(ob, mod, token=None, matrix=None):
    collection = _collection()
    if collection is None:
        collection = bpy.data.collections.new(COLLECTION)
        collection[HELPER] = True
    for scene in ob.users_scene or (bpy.context.scene,):
        if collection not in tuple(scene.collection.children):
            scene.collection.children.link(collection)
    collection.hide_render = True
    plane = bpy.data.objects.new('.Symmetry Mirror', None)
    collection.objects.link(plane)
    plane[HELPER] = True
    plane['token'] = token or uuid.uuid4().hex
    plane['owner'] = ob
    plane.parent = ob
    plane.matrix_parent_inverse.identity()
    plane.matrix_basis = matrix if matrix is not None else Matrix.Identity(4)
    plane.empty_display_type = 'PLAIN_AXES'
    plane.empty_display_size = .001
    plane.hide_render = True
    plane.hide_select = True
    plane.hide_set(True)
    if raw(mod).type == 'MIRROR':
        raw(mod).mirror_object = plane
    else:
        raw(mod).node_group.nodes['Mirror frame'].inputs['Object'].default_value = plane
    _remember(ob, mod)
    return plane


def add(ob):
    mod = ob.modifiers.new('Symmetry', 'NODES')
    token = uuid.uuid4().hex
    mod.node_group = symmetry_nodes.build(token)
    mod.show_in_editmode = True
    mod.show_on_cage = False
    mod.show_expanded = False
    _new_plane(ob, mod, token)
    ob.modifiers.active = mod
    return mod


def _upgrade(ob, old):
    """Keep scenes saved by the earlier native-Mirror implementation usable."""
    index, name = ob.modifiers.find(old.name), old.name
    helper = old.mirror_object
    values = {key: getattr(old, key) for key in
              ('merge_threshold', 'bisect_threshold', 'use_mirror_merge')}
    values['use_axis'] = tuple(old.use_axis)
    values['use_bisect_flip_axis'] = tuple(old.use_bisect_flip_axis)
    values['slice'] = any(old.use_bisect_axis)
    values['proximity'] = True
    display = {key: getattr(old, key) for key in
               ('show_viewport', 'show_render', 'show_in_editmode', 'show_on_cage', 'show_expanded')}
    mod = ob.modifiers.new('Symmetry migration', 'NODES')
    mod.node_group = symmetry_nodes.build(helper['token'])
    mod.node_group.nodes['Mirror frame'].inputs['Object'].default_value = helper
    for key, value in values.items():
        setattr(settings(mod), key, value)
    for key, value in display.items():
        setattr(mod, key, value)
    active = ob.modifiers.active == old
    ob.modifiers.remove(old)
    mod.name = name
    ob.modifiers.move(ob.modifiers.find(mod.name), index)
    if active:
        ob.modifiers.active = mod
    return mod


def leave(context):
    """Restore the mesh selection when leaving the Mirror stack level."""
    if not editing(context):
        return owner(context)
    plane = context.view_layer.objects.active
    ob = plane.get('owner')
    plane.select_set(False)
    plane.hide_set(True)
    plane.hide_select = True
    if ob and ob.name in context.view_layer.objects:
        ob.select_set(True)
        context.view_layer.objects.active = ob
    return ob


def enter(context, mod):
    mod = raw(mod)
    leave(context)
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    ob = mod.id_data
    for selected in context.selected_objects:
        selected.select_set(False)
    plane = settings(mod).mirror_object
    plane.hide_select = False
    plane.hide_set(False)
    plane.select_set(True)
    context.view_layer.objects.active = plane
    ob.modifiers.active = mod
    mod.show_expanded = True
    context.window_manager.max_sublevel = 0


def reconcile():
    """Repair saved references and remove only this feature's orphan helpers."""
    global _busy
    if _busy or not _enabled:
        return
    _busy = True
    try:
        used = set()
        for ob in list(bpy.data.objects):
            if ob.type != 'MESH':
                continue
            records = _records(ob)
            live_tokens = set()
            for mod in list(ob.modifiers):
                if not is_symmetry(mod):
                    continue
                current = settings(mod).mirror_object
                if current is not None and current.get(HELPER):
                    plane = current
                    if plane.get('owner') != ob or plane in used:
                        if mod.type == 'NODES':
                            mod.node_group = mod.node_group.copy()
                            mod.node_group[symmetry_nodes.MARKER] = uuid.uuid4().hex
                        plane = _new_plane(ob, mod, matrix=plane.matrix_basis.copy())
                else:
                    uid = int(getattr(mod, 'persistent_uid', 0))
                    match = next(((token, rec) for token, rec in records.items()
                                  if (rec.get('uid') == uid if uid and rec.get('uid')
                                   else rec['name'] == mod.name)), None)
                    if match is None:
                        # The native node group retains Symmetry identity even
                        # after the user deletes all helper scene data.
                        plane = _new_plane(ob, mod)
                        used.add(plane)
                        live_tokens.add(plane['token'])
                        continue
                    token, rec = match
                    values = rec['matrix']
                    plane = _new_plane(ob, mod, token, Matrix([values[i:i+4] for i in range(0, 16, 4)]))
                if mod.type == 'MIRROR':
                    mod = _upgrade(ob, mod)
                elif mod.node_group.get('max_symmetry_revision', 0) < symmetry_nodes.REVISION:
                    # Node graphs persist in .blend files. Rebuild older
                    # engines so existing scenes receive numerical/perf fixes.
                    values = {key: (tuple(getattr(settings(mod), key))
                                    if key in {'use_axis', 'use_bisect_flip_axis'}
                                    else getattr(settings(mod), key)) for key in _INPUTS}
                    mod.node_group = symmetry_nodes.build(mod.node_group[symmetry_nodes.MARKER])
                    mod.node_group.nodes['Mirror frame'].inputs['Object'].default_value = plane
                    for key, value in values.items():
                        setattr(settings(mod), key, value)
                used.add(plane)
                live_tokens.add(plane['token'])
                _remember(ob, mod)
                # Timers can run while area reconstruction removes the
                # area-provided active_object context member.
                if bpy.context.view_layer.objects.active != plane:
                    plane.hide_set(True)
                    plane.hide_select = True
            records = _records(ob)
            kept = {token: rec for token, rec in records.items() if token in live_tokens}
            if kept != records:
                if kept:
                    ob[STATE] = kept
                else:
                    del ob[STATE]
        for plane in list(bpy.data.objects):
            if plane.get(HELPER) and plane not in used:
                if bpy.context.view_layer.objects.active == plane:
                    leave(bpy.context)
                bpy.data.objects.remove(plane, do_unlink=True)
        collection = _collection()
        if collection and not collection.objects:
            bpy.data.collections.remove(collection)
        for group in list(bpy.data.node_groups):
            if group.get(symmetry_nodes.MARKER) and group.users == 0:
                bpy.data.node_groups.remove(group)
    finally:
        _busy = False


def _maintain():
    if not _enabled:
        return None
    reconcile()
    return None


@persistent
def _changed(*_):
    if _enabled and not _busy and not bpy.app.background and not bpy.app.timers.is_registered(_maintain):
        bpy.app.timers.register(_maintain, first_interval=.05)


@persistent
def _loaded(*_):
    # The mesh is the persisted stack selection, even if saved at Mirror level.
    leave(bpy.context)
    reconcile()


@persistent
def _undo(*_):
    reconcile()


def draw_stack(layout, context, ob):
    if not any(is_symmetry(m) for m in ob.modifiers):
        return False
    from . import poly_tools
    box = layout.column(align=True)
    for mod in reversed(ob.modifiers):
        if poly_tools.is_font_pivot(mod):
            continue
        row = box.row(align=True)
        row.context_pointer_set('max_icon_modifier', mod)
        row.operator('wm.context_toggle', text='', emboss=False,
                     icon='HIDE_OFF' if mod.show_viewport else 'HIDE_ON').data_path = 'max_icon_modifier.show_viewport'
        if is_symmetry(mod):
            op = row.operator('max.symmetry_action', text='', emboss=False,
                              icon='TRIA_DOWN' if mod.show_expanded else 'TRIA_RIGHT')
            op.name, op.action = mod.name, 'EXPAND'
        row.operator('max.modifier_set_active', text=mod.name,
                     depress=(mod.is_active and not editing(context) and context.mode == 'OBJECT')).name = mod.name
        if is_symmetry(mod) and mod.show_expanded:
            row = box.row(align=True)
            row.label(text='', icon='BLANK1')
            op = row.operator('max.symmetry_action', text='Mirror',
                              depress=(context.active_object == plane(mod)))
            op.name, op.action = mod.name, 'MIRROR'
    return True


def draw(layout, ob, mod):
    mod = settings(mod)
    layout.use_property_split = False
    layout.use_property_decorate = False
    row = layout.row(align=True)
    row.menu('MAX_MT_symmetry_type', text='Radial' if mod.radial else 'Planar')
    box = layout.column(align=True)
    box.label(text='Mirror Axis:')
    for i, axis in enumerate('XYZ'):
        row = box.row(align=True)
        split = row.split(factor=.52, align=True)
        selected = mod.radial_axis == i if mod.radial else mod.use_axis[i]
        op = split.operator('max.symmetry_action', text=axis, emboss=False,
                            icon='RADIOBUT_ON' if selected else 'RADIOBUT_OFF')
        op.name, op.action = mod.name, 'AXIS_'+axis
        if not mod.radial:
            sub = split.row(align=True)
            sub.enabled = bool(mod.use_axis[i])
            op = sub.operator('max.symmetry_action', text='Flip', emboss=False,
                              icon='CHECKBOX_HLT' if mod.use_bisect_flip_axis[i] else 'CHECKBOX_DEHLT')
            op.name, op.action = mod.name, 'FLIP_'+axis
    row = layout.row(align=True)
    op = row.operator('max.symmetry_pick', text='Align to Face')
    op.name, op.kind = mod.name, 'FACE'
    op = row.operator('max.symmetry_action', text='', icon='FILE_REFRESH')
    op.name, op.action = mod.name, 'RESET'
    op = layout.operator('max.symmetry_pick', text='Pick Object')
    op.name, op.kind = mod.name, 'OBJECT'
    box = layout.column(align=True)
    box.label(text='Symmetry Options:')
    if mod.radial:
        row = box.row(align=True)
        split = row.split(factor=.55, align=True)
        label = split.row()
        label.alignment = 'RIGHT'
        label.label(text='Count:')
        mod.prop(split, 'count', text='')
        row = box.row(align=True)
        mod.prop(row, 'mirror_symmetry', text='Mirror Symmetry')
        sub = row.row(align=True)
        sub.enabled = mod.mirror_symmetry
        mod.prop(sub, 'radial_flip', text='Flip')
    # Slice is one switch in Max, independent of which axes are enabled.
    op = box.operator('max.symmetry_action', text='Slice Along Mirror', emboss=False,
                      icon='CHECKBOX_HLT' if any(mod.use_bisect_axis) else 'CHECKBOX_DEHLT')
    op.name, op.action = mod.name, 'SLICE'

    def spinner(prop, enabled):
        from . import max_widgets
        return max_widgets.spinner(box, mod.mod, '["'+mod.path(prop)+'"]',
                                   'Threshold', enabled=enabled)

    spinner('bisect_threshold', any(mod.use_bisect_axis))
    mod.prop(box, 'use_mirror_merge', text='Weld Seam')
    spinner('merge_threshold', mod.use_mirror_merge)
    mod.prop(box, 'proximity', text='Use Proximity Weld')


class MAX_MT_symmetry_type(bpy.types.Menu):
    bl_label = 'Symmetry Type'

    def draw(self, context):
        ob = owner(context)
        mod = ob.modifiers.active if ob else None
        if not is_symmetry(mod):
            return
        for action in ('PLANAR', 'RADIAL'):
            active = settings(mod).radial == (action == 'RADIAL')
            op = self.layout.operator('max.symmetry_action', text=action.title(),
                                      icon='RADIOBUT_ON' if active else 'RADIOBUT_OFF')
            op.name, op.action = mod.name, action


class MAX_OT_symmetry_action(bpy.types.Operator):
    """Edit the Symmetry mirror plane or its stack entry"""
    bl_idname = 'max.symmetry_action'
    bl_label = 'Symmetry'
    bl_options = {'REGISTER', 'UNDO'}
    name: StringProperty()
    action: EnumProperty(items=[(x, x.title(), '') for x in
                         ('MIRROR', 'EXPAND', 'RESET', 'SLICE', 'REMOVE', 'APPLY', 'UP', 'DOWN',
                          'PLANAR', 'RADIAL', 'AXIS_X', 'AXIS_Y', 'AXIS_Z', 'FLIP_X', 'FLIP_Y', 'FLIP_Z')])

    def execute(self, context):
        ob = owner(context)
        mod = ob.modifiers.get(self.name) if ob else None
        if not is_symmetry(mod):
            return {'CANCELLED'}
        mod = settings(mod)
        if self.action == 'MIRROR':
            if context.active_object == mod.mirror_object:
                leave(context)
            else:
                enter(context, mod)
        elif self.action == 'EXPAND':
            mod.show_expanded = not mod.show_expanded
            if not mod.show_expanded:
                leave(context)
        elif self.action == 'RESET':
            mod.mirror_object.matrix_basis = Matrix.Identity(4)
        elif self.action == 'SLICE':
            value = not any(mod.use_bisect_axis)
            mod.use_bisect_axis = (value, value, value)
        elif self.action in {'REMOVE', 'APPLY'}:
            leave(context)
            if self.action == 'APPLY':
                with context.temp_override(object=ob, active_object=ob):
                    if bpy.ops.object.modifier_apply(modifier=mod.name) != {'FINISHED'}:
                        return {'CANCELLED'}
            else:
                ob.modifiers.remove(raw(mod))
            reconcile()
        elif self.action in {'PLANAR', 'RADIAL'}:
            mod.radial = self.action == 'RADIAL'
        elif self.action.startswith('AXIS_'):
            axis = 'XYZ'.index(self.action[-1])
            if mod.radial:
                mod.radial_axis = axis
            else:
                axes = list(mod.use_axis)
                axes[axis] = not axes[axis]
                mod.use_axis = axes
        elif self.action.startswith('FLIP_'):
            axis = 'XYZ'.index(self.action[-1])
            flips = list(mod.use_bisect_flip_axis)
            flips[axis] = not flips[axis]
            mod.use_bisect_flip_axis = flips
        else:
            index = ob.modifiers.find(mod.name)
            target = index + (-1 if self.action == 'UP' else 1)
            if 0 <= target < len(ob.modifiers):
                ob.modifiers.move(index, target)
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


class MAX_OT_symmetry_pick(bpy.types.Operator):
    """Click a face or reference object to place the Mirror gizmo. Right-click cancels"""
    bl_idname = 'max.symmetry_pick'
    bl_label = 'Symmetry alignment'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}
    name: StringProperty()
    kind: EnumProperty(items=[('FACE', 'Align to Face', ''), ('OBJECT', 'Pick Object', '')])

    def invoke(self, context, event):
        ob = owner(context)
        if ob is None or not is_symmetry(ob.modifiers.get(self.name)):
            return {'CANCELLED'}
        self._owner = ob
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not _enabled or event.type in {'RIGHTMOUSE', 'ESC'}:
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            from bpy_extras import view3d_utils
            from .create import region_under_mouse
            area, region = region_under_mouse(context, event.mouse_x, event.mouse_y)
            if area is None:
                return {'RUNNING_MODAL'}
            # Use the same region picker as the add-on's creation tools.
            with context.temp_override(area=area, region=region):
                rv3d = context.region_data
            xy = (event.mouse_x-region.x, event.mouse_y-region.y)
            origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, xy)
            direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, xy)
            found, point, normal, _, target, _ = context.scene.ray_cast(context.evaluated_depsgraph_get(), origin, direction)
            if found:
                mod = self._owner.modifiers.get(self.name)
                if not is_symmetry(mod):
                    return {'CANCELLED'}
                mod = settings(mod)
                if self.kind == 'OBJECT':
                    mod.mirror_object.matrix_world = target.matrix_world.copy()
                else:
                    axis = mod.radial_axis if mod.radial else next((i for i, enabled in enumerate(mod.use_axis) if enabled), 0)
                    rotation = Vector(tuple(1 if i == axis else 0 for i in range(3))).rotation_difference(normal)
                    mod.mirror_object.matrix_world = Matrix.Translation(point) @ rotation.to_matrix().to_4x4()
                return {'FINISHED'}
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


def _draw_plane():
    context = bpy.context
    if not editing(context):
        return
    plane = context.active_object
    ob = owner(context)
    mod = next((m for m in ob.modifiers if is_symmetry(m) and settings(m).mirror_object == plane), None) if ob else None
    if mod is None:
        return
    mod = settings(mod)
    import gpu
    from gpu_extras.batch import batch_for_shader
    size = max((Vector(c).length for c in ob.bound_box), default=1) * .65
    size = max(size, .25)
    vertices = []
    if mod.radial:
        import math
        axis = mod.radial_axis
        a, b = [i for i in range(3) if i != axis]
        for i in range(64):
            for angle in (math.tau*i/64, math.tau*(i+1)/64):
                p = Vector((0, 0, 0))
                p[a], p[b] = math.cos(angle)*size, math.sin(angle)*size
                vertices.append(plane.matrix_world @ p)
        for i in range(mod.count):
            p = Vector((0, 0, 0))
            p[a], p[b] = math.cos(math.tau*i/mod.count)*size, math.sin(math.tau*i/mod.count)*size
            vertices.extend((plane.matrix_world.translation, plane.matrix_world @ p))
        p = Vector((0, 0, 0))
        p[axis] = size
        vertices.extend((plane.matrix_world @ -p, plane.matrix_world @ p))
    for axis, enabled in enumerate(mod.use_axis):
        if mod.radial or not enabled:
            continue
        a, b = [i for i in range(3) if i != axis]
        corners = []
        for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            p = Vector((0, 0, 0))
            p[a], p[b] = u*size, v*size
            corners.append(plane.matrix_world @ p)
        for i in range(4):
            vertices.extend((corners[i], corners[(i+1) % 4]))
        start = plane.matrix_world.translation
        tip = Vector((0, 0, 0))
        tip[axis] = (-1 if mod.use_bisect_flip_axis[axis] else 1)*size*.4
        vertices.extend((start, plane.matrix_world @ tip))
    if not vertices:
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('NONE')
    gpu.state.line_width_set(2)
    try:
        shader.bind()
        shader.uniform_float('color', (1, .75, .05, 1))
        batch_for_shader(shader, 'LINES', {'pos': vertices}).draw(shader)
    finally:
        gpu.state.line_width_set(1)
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('NONE')


classes = (MAX_MT_symmetry_type, MAX_OT_symmetry_action, MAX_OT_symmetry_pick)


def register():
    global _enabled, _draw_handle
    _enabled = True
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, _changed),
                               (bpy.app.handlers.load_post, _loaded),
                               (bpy.app.handlers.undo_post, _undo),
                               (bpy.app.handlers.redo_post, _undo),
                               (bpy.app.handlers.save_pre, _undo)):
        if callback not in handlers:
            handlers.append(callback)
    # Blender restricts bpy.data during addon_utils.enable(). Restore on the
    # first timer tick, after registration has returned to a usable context.
    if not bpy.app.timers.is_registered(_maintain):
        bpy.app.timers.register(_maintain, first_interval=0)
    if not bpy.app.background:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_plane, (), 'WINDOW', 'POST_VIEW')


def unregister():
    global _enabled, _draw_handle
    leave(bpy.context)
    reconcile()
    _enabled = False
    if bpy.app.timers.is_registered(_maintain):
        bpy.app.timers.unregister(_maintain)
    for handlers, callback in ((bpy.app.handlers.depsgraph_update_post, _changed),
                               (bpy.app.handlers.load_post, _loaded),
                               (bpy.app.handlers.undo_post, _undo),
                               (bpy.app.handlers.redo_post, _undo),
                               (bpy.app.handlers.save_pre, _undo)):
        if callback in handlers:
            handlers.remove(callback)
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None
    # These are native scene dependencies, not runtime registrations. Keeping
    # them makes render, export and editing evaluate identically while disabled.
