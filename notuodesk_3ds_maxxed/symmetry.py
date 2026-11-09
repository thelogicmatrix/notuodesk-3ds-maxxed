"""Max Symmetry parameters and its movable Mirror sub-object."""
import uuid

import bpy
from bpy.app.handlers import persistent
from bpy.props import EnumProperty, StringProperty
from mathutils import Matrix, Vector

HELPER = 'max_symmetry_plane'
STATE = 'max_symmetry_planes'
COLLECTION = '.3ds Maxxed Symmetry'
_draw_handle = None
_enabled = False
_busy = False


def is_symmetry(mod):
    return (mod is not None and mod.type == 'MIRROR'
            and mod.mirror_object is not None and bool(mod.mirror_object.get(HELPER)))


def owner(context):
    ob = context.active_object
    if ob is not None and ob.get(HELPER):
        return ob.get('owner')
    return ob


def editing(context):
    ob = context.active_object
    return ob is not None and bool(ob.get(HELPER))


def _matrix_values(plane):
    return [v for row in plane.matrix_basis for v in row]


def _records(ob):
    data = ob.get(STATE)
    return data.to_dict() if data is not None else {}


def _collection():
    return next((c for c in bpy.data.collections if c.get(HELPER)), None)


def _remember(ob, mod):
    plane = mod.mirror_object
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
    mod.mirror_object = plane
    _remember(ob, mod)
    return plane


def add(ob):
    mod = ob.modifiers.new('Symmetry', 'MIRROR')
    mod.use_axis = (True, False, False)
    mod.use_bisect_axis = (True, True, True)
    mod.use_bisect_flip_axis = (False, False, False)
    mod.use_mirror_merge = True
    mod.merge_threshold = .01
    mod.bisect_threshold = .01
    mod.show_in_editmode = True
    mod.show_on_cage = False
    mod.show_expanded = False
    _new_plane(ob, mod)
    ob.modifiers.active = mod
    return mod


def leave(context):
    """Restore the mesh selection when leaving the Mirror stack level."""
    if not editing(context):
        return owner(context)
    plane = context.active_object
    ob = plane.get('owner')
    plane.select_set(False)
    plane.hide_set(True)
    plane.hide_select = True
    if ob and ob.name in context.view_layer.objects:
        ob.select_set(True)
        context.view_layer.objects.active = ob
    return ob


def enter(context, mod):
    leave(context)
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    ob = mod.id_data
    for selected in context.selected_objects:
        selected.select_set(False)
    plane = mod.mirror_object
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
            for mod in ob.modifiers:
                if mod.type != 'MIRROR':
                    continue
                if is_symmetry(mod):
                    plane = mod.mirror_object
                    if plane.get('owner') != ob or plane in used:
                        plane = _new_plane(ob, mod, matrix=plane.matrix_basis.copy())
                else:
                    uid = int(getattr(mod, 'persistent_uid', 0))
                    match = next(((token, rec) for token, rec in records.items()
                                  if rec.get('suspended') and
                                  (rec.get('uid') == uid if uid and rec.get('uid')
                                   else rec['name'] == mod.name)), None)
                    if match is None:
                        continue
                    token, rec = match
                    values = rec['matrix']
                    plane = _new_plane(ob, mod, token, Matrix([values[i:i+4] for i in range(0, 16, 4)]))
                used.add(plane)
                live_tokens.add(plane['token'])
                _remember(ob, mod)
                if bpy.context.active_object != plane:
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
                if bpy.context.active_object == plane:
                    leave(bpy.context)
                bpy.data.objects.remove(plane, do_unlink=True)
        collection = _collection()
        if collection and not collection.objects:
            bpy.data.collections.remove(collection)
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
    box = layout.box().column(align=True)
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
                              depress=(context.active_object == mod.mirror_object))
            op.name, op.action = mod.name, 'MIRROR'
    return True


def draw(layout, ob, mod):
    layout.use_property_split = False
    layout.use_property_decorate = False
    row = layout.row(align=True)
    row.menu('MAX_MT_symmetry_type', text='Planar')
    box = layout.box().column(align=True)
    box.label(text='Mirror Axis:')
    for i, axis in enumerate('XYZ'):
        row = box.row(align=True)
        split = row.split(factor=.52, align=True)
        split.prop(mod, 'use_axis', index=i, text=axis, emboss=False,
                   icon='RADIOBUT_ON' if mod.use_axis[i] else 'RADIOBUT_OFF')
        sub = split.row(align=True)
        sub.enabled = mod.use_axis[i]
        sub.prop(mod, 'use_bisect_flip_axis', index=i, text='Flip')
    row = layout.row(align=True)
    op = row.operator('max.symmetry_pick', text='Align to Face')
    op.name, op.kind = mod.name, 'FACE'
    op = row.operator('max.symmetry_action', text='', icon='FILE_REFRESH')
    op.name, op.action = mod.name, 'RESET'
    op = layout.operator('max.symmetry_pick', text='Pick Object')
    op.name, op.kind = mod.name, 'OBJECT'
    box = layout.box().column(align=True)
    box.label(text='Symmetry Options:')
    # Slice is one switch in Max, independent of which axes are enabled.
    op = box.operator('max.symmetry_action', text='Slice Along Mirror', emboss=False,
                      icon='CHECKBOX_HLT' if any(mod.use_bisect_axis) else 'CHECKBOX_DEHLT')
    op.name, op.action = mod.name, 'SLICE'

    def spinner(prop, enabled):
        row = box.row(align=True)
        row.enabled = enabled
        split = row.split(factor=.55, align=True)
        label = split.row()
        label.alignment = 'RIGHT'
        label.label(text='Threshold:')
        split.prop(mod, prop, text='')

    spinner('bisect_threshold', any(mod.use_bisect_axis))
    box.prop(mod, 'use_mirror_merge', text='Weld Seam')
    spinner('merge_threshold', mod.use_mirror_merge)
    row = box.row()
    row.enabled = False
    row.label(text='Use Proximity Weld', icon='CHECKBOX_HLT')
    box.label(text='Mirror uses proximity welding.')


class MAX_MT_symmetry_type(bpy.types.Menu):
    bl_label = 'Symmetry Type'

    def draw(self, context):
        self.layout.label(text='Planar', icon='RADIOBUT_ON')
        row = self.layout.row()
        row.enabled = False
        row.label(text='Radial', icon='RADIOBUT_OFF')
        self.layout.label(text='Radial needs a separate geometry engine.')


class MAX_OT_symmetry_action(bpy.types.Operator):
    """Edit the Symmetry mirror plane or its stack entry"""
    bl_idname = 'max.symmetry_action'
    bl_label = 'Symmetry'
    bl_options = {'REGISTER', 'UNDO'}
    name: StringProperty()
    action: EnumProperty(items=[(x, x.title(), '') for x in
                         ('MIRROR', 'EXPAND', 'RESET', 'SLICE', 'REMOVE', 'APPLY', 'UP', 'DOWN')])

    def execute(self, context):
        ob = owner(context)
        mod = ob.modifiers.get(self.name) if ob else None
        if not is_symmetry(mod):
            return {'CANCELLED'}
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
                    bpy.ops.object.modifier_apply(modifier=mod.name)
            else:
                ob.modifiers.remove(mod)
            reconcile()
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
                if self.kind == 'OBJECT':
                    mod.mirror_object.matrix_world = target.matrix_world.copy()
                else:
                    axis = next((i for i, enabled in enumerate(mod.use_axis) if enabled), 0)
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
    mod = next((m for m in ob.modifiers if is_symmetry(m) and m.mirror_object == plane), None) if ob else None
    if mod is None:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    size = max((Vector(c).length for c in ob.bound_box), default=1) * .65
    size = max(size, .25)
    vertices = []
    for axis, enabled in enumerate(mod.use_axis):
        if not enabled:
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
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and STATE in ob:
            records = _records(ob)
            for record in records.values():
                record['suspended'] = True
            ob[STATE] = records
    for plane in list(bpy.data.objects):
        if plane.get(HELPER):
            bpy.data.objects.remove(plane, do_unlink=True)
    collection = _collection()
    if collection and not collection.objects:
        bpy.data.collections.remove(collection)
