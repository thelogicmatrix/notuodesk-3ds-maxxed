"""Command Panel presentation and transient stack controls."""
import bpy
from bpy.app.handlers import persistent
from bpy.props import EnumProperty, StringProperty
from . import max_icons, max_widgets as w, modifier_ui, symmetry

_polls = []
_pins = {}
_end_results = {}
_installed = False
_rail_handle = None
_listeners = {}


def object_for(context):
    key = context.window.as_pointer() if context.window else 0
    pinned = _pins.get(key)
    try:
        if pinned and pinned.name in context.view_layer.objects:
            return pinned
    except ReferenceError:
        _pins.pop(key, None)
    return symmetry.owner(context)


def internal(mod):
    from . import poly_tools
    return modifier_ui.is_internal(mod) or poly_tools.is_font_pivot(mod)


def active(ob):
    if ob is None or ob.mode == 'EDIT':
        return None
    from . import editable_poly
    mod = ob.modifiers.active
    return mod if mod and not internal(mod) and not editable_poly.is_nurms(mod) else None


def _restore_end(ob):
    try:
        saved = _end_results.pop(ob.as_pointer(), None)
        if saved:
            for mod, visibility in saved[1]:
                try:
                    mod.show_viewport = visibility
                except ReferenceError:
                    pass
    except ReferenceError:
        pass


@persistent
def clear_runtime(_=None):
    _pins.clear()
    for ob, _ in tuple(_end_results.values()):
        _restore_end(ob)
    _end_results.clear()


def _panel_types(base):
    for cls in base.__subclasses__():
        yield cls
        yield from _panel_types(cls)


def _workspace_poll(original):
    # RNA callbacks must have exactly the declared positional arguments.
    def poll(panel, context):
        if context.workspace and context.workspace.name == '3ds Max':
            return False
        return original(context) if original else True
    return classmethod(poll)


def rail_width(context):
    return round(24 * context.preferences.system.ui_scale) + 1


def _draw_rail():
    context = bpy.context
    if not (_installed and context.workspace and context.workspace.name == '3ds Max'
            and context.region and context.region.type == 'UI'):
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    region = context.region
    x = region.width - rail_width(context)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('color', (0.1843, 0.1843, 0.1843, 1))
    batch_for_shader(shader, 'TRI_STRIP', {'pos': ((x, 0), (region.width, 0),
        (x, region.height), (region.width, region.height))}).draw(shader)


def attach_window(context):
    if not bpy.app.background and _installed and context.window and context.window.as_pointer() not in _listeners:
        bpy.ops.max.command_panel_rail('INVOKE_DEFAULT')


def _start_listeners():
    if _installed and not bpy.app.background:
        windows = tuple(bpy.context.window_manager.windows)
        alive = {window.as_pointer() for window in windows}
        for key in tuple(_listeners):
            if key not in alive:
                _listeners.pop(key, None)
        for window in windows:
            with bpy.context.temp_override(window=window):
                attach_window(bpy.context)
        return 1.0


@persistent
def _after_load(_):
    _listeners.clear()
    if _installed and not bpy.app.timers.is_registered(_start_listeners):
        bpy.app.timers.register(_start_listeners, first_interval=.1)


def install():
    """Suppress other sidebar categories only in the named Max workspace."""
    global _installed, _rail_handle
    if _installed:
        return
    _installed = True
    bpy.types.UI_MT_button_context_menu.append(stack_context_menu)
    for cls in _panel_types(bpy.types.Panel):
        if (getattr(cls, 'bl_space_type', '') != 'VIEW_3D' or
                getattr(cls, 'bl_region_type', '') != 'UI' or
                getattr(cls, 'bl_category', '') == 'Command Panel' or
                getattr(bpy.types, cls.__name__, None) is not cls):
            continue
        own = cls.__dict__.get('poll')
        previous = getattr(cls, 'poll', None)
        try:
            cls.poll = _workspace_poll(previous)
            _polls.append((cls, own))
        except (AttributeError, TypeError):
            continue
    bpy.types.WindowManager.max_hierarchy_tab = EnumProperty(
        name='Hierarchy', items=(('PIVOT', 'Pivot', ''), ('IK', 'IK', ''),
                                 ('LINK', 'Link Info', '')), default='PIVOT', options={'SKIP_SAVE'})
    if clear_runtime not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(clear_runtime)
    if _after_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_after_load)
    from . import mode_feedback
    mode_feedback.PASSIVE_MODALS.add('MAX_OT_command_panel_rail')
    if not bpy.app.background:
        _rail_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_rail, (), 'UI', 'POST_PIXEL')
        bpy.app.timers.register(_start_listeners, first_interval=.1)


def uninstall():
    global _installed, _rail_handle
    _installed = False
    bpy.types.UI_MT_button_context_menu.remove(stack_context_menu)
    _listeners.clear()
    if bpy.app.timers.is_registered(_start_listeners):
        bpy.app.timers.unregister(_start_listeners)
    if _rail_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_rail_handle, 'UI')
        _rail_handle = None
    from . import mode_feedback
    mode_feedback.PASSIVE_MODALS.discard('MAX_OT_command_panel_rail')
    clear_runtime()
    for cls, previous in reversed(_polls):
        if previous is None:
            if 'poll' in cls.__dict__:
                del cls.poll
        else:
            cls.poll = previous
    _polls.clear()
    if clear_runtime in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(clear_runtime)
    if _after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_after_load)
    if hasattr(bpy.types.WindowManager, 'max_hierarchy_tab'):
        del bpy.types.WindowManager.max_hierarchy_tab


class MAX_OT_command_panel_rail(bpy.types.Operator):
    bl_idname = 'max.command_panel_rail'
    bl_label = 'Command Panel Category Guard'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        self.window_id = context.window.as_pointer()
        if self.window_id in _listeners:
            return {'CANCELLED'}
        _listeners[self.window_id] = self
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not _installed or _listeners.get(self.window_id) != self:
            return {'CANCELLED'}
        if context.workspace and context.workspace.name == '3ds Max':
            for area in context.window.screen.areas:
                if area.type != 'VIEW_3D':
                    continue
                for region in area.regions:
                    if region.type == 'UI' and region.width > 1:
                        if (region.x + region.width - rail_width(context) <= event.mouse_x < region.x + region.width
                                and region.y <= event.mouse_y < region.y + region.height):
                            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


def tabs(layout, context, catalogue):
    row = w.compact(layout.row(align=True))
    for key, label, description, fallback, index in catalogue:
        row.prop_enum(context.window_manager, 'max_cmd_tab', key, text='')


def name_color(layout, ob):
    if ob:
        row = w.compact(layout.row(align=True))
        row.prop(ob, 'name', text='')
        color = row.row(align=True)
        color.ui_units_x = 1.4
        color.prop(ob, 'color', text='')


def stack_button(layout, ob, action, text='', *, art=None, fallback='NONE', name='', depress=False):
    row = layout.row(align=True)
    row.context_pointer_set('max_panel_owner', ob)
    op = row.operator('max.command_stack', text=text, emboss=bool(text), depress=depress,
                      **(max_icons.ui(art, fallback) if art else {}))
    op.action, op.name = action, name
    return op


def stack_context_menu(self, context):
    """Max's base-object conversion route on the native stack button menu."""
    button = getattr(context, 'button_operator', None)
    if button and button.bl_rna.identifier == 'MAX_OT_modifier_set_active' and not button.name:
        self.layout.separator()
        self.layout.menu('MAX_MT_convert', text='Convert To:')


def draw_stack(layout, context, ob):
    """One tree including the base object and retained Mirror/mesh levels."""
    from . import mode_feedback, prims
    box = w.compact(layout.box().column(align=True))
    # Symmetry owns its helper-aware tree; the base shares the same enclosure.
    if not symmetry.draw_stack(box, context, ob):
        current = active(ob)
        for index, label, children in modifier_ui.stack_rows(ob):
            if index < 0:
                continue
            mod = ob.modifiers[index]
            if internal(mod):
                continue
            row = box.row(align=True)
            row.context_pointer_set('max_icon_modifier', mod)
            row.operator('wm.context_toggle', text='', emboss=False,
                         **max_icons.ui('bulb_on' if mod.show_viewport else 'bulb_off',
                                        'HIDE_OFF' if mod.show_viewport else 'HIDE_ON')).data_path = 'max_icon_modifier.show_viewport'
            stack_button(row, ob, 'SELECT', label, name=mod.name, depress=mod == current)
            if mod == current:
                for token, child in zip(('POINTS', 'LATTICE'), children):
                    line = box.row(align=True)
                    line.separator(factor=1.5)
                    line.operator('max.ffd_level', text=child, emboss=False).level = token
    kind = ob.max_prim.kind if ob.type == 'MESH' else ''
    label = prims.PRIMITIVES[kind][0] if kind in prims.PRIMITIVES else (
        'Editable Poly' if ob.type == 'MESH' else 'Editable Spline' if ob.type == 'CURVE' else ob.type.title())
    mode_feedback.draw_stack_levels(box, context, ob, label,
                                   max_icons.ui('editable_poly' if ob.type == 'MESH' else 'object', 'OBJECT_DATA'))
    row = layout.row(align=True)
    key = context.window.as_pointer() if context.window else 0
    stack_button(row, ob, 'PIN', art='pin_stack', fallback='PINNED', depress=key in _pins)
    stack_button(row, ob, 'END_RESULT', art='show_end_result', fallback='MODIFIER',
                 depress=ob.as_pointer() not in _end_results)
    unique = row.row(align=True)
    unique.enabled = bool(ob.data and ob.data.users > 1 and active(ob) is None)
    stack_button(unique, ob, 'UNIQUE', art='make_unique', fallback='DUPLICATE')
    selected = row.row(align=True)
    selected.enabled = active(ob) is not None
    for action, art, fallback in (('REMOVE', 'remove_modifier', 'TRASH'), ('UP', 'up', 'TRIA_UP'),
                                   ('DOWN', 'down', 'TRIA_DOWN'), ('APPLY', 'caddy_ok', 'CHECKMARK')):
        stack_button(selected, ob, action, art=art, fallback=fallback)
    disabled = row.row(align=True)
    disabled.enabled = False
    disabled.operator('max.poly_unavailable', text='', icon='PREFERENCES').reason = 'Configure Modifier Sets is not supported'


def unavailable(layout, text, icon='NONE'):
    row = layout.row(align=True)
    row.enabled = False
    row.operator('max.poly_unavailable', text=text, icon=icon).reason = text + ' is not supported'


class MAX_OT_command_stack(bpy.types.Operator):
    bl_idname = 'max.command_stack'
    bl_label = 'Modifier Stack'
    bl_options = {'UNDO'}
    action: EnumProperty(items=tuple((s, label, '') for s, label in (
        ('SELECT', 'Select Stack Entry'), ('PIN', 'Pin Stack'), ('END_RESULT', 'Show End Result'),
        ('UNIQUE', 'Make Unique'), ('REMOVE', 'Remove Modifier'), ('UP', 'Move Up'),
        ('DOWN', 'Move Down'), ('APPLY', 'Collapse To'))))
    name: StringProperty()

    @classmethod
    def description(cls, context, properties):
        return next(item.name for item in cls.bl_rna.properties['action'].enum_items
                    if item.identifier == properties.action)

    def execute(self, context):
        ob = getattr(context, 'max_panel_owner', None) or object_for(context)
        if not ob:
            return {'CANCELLED'}
        key = context.window.as_pointer() if context.window else 0
        if self.action == 'PIN':
            if key in _pins:
                _pins.pop(key)
            else:
                _pins[key] = ob
            return {'FINISHED'}
        mod = active(ob)
        if self.action == 'SELECT':
            _restore_end(ob)
            mod = ob.modifiers.get(self.name)
            if mod and internal(mod):
                return {'CANCELLED'}
            with context.temp_override(object=ob, active_object=ob):
                return bpy.ops.max.modifier_set_active(name=self.name)
        if self.action == 'UNIQUE':
            if mod is None and ob.data and ob.data.users > 1:
                ob.data = ob.data.copy()
                return {'FINISHED'}
            return {'CANCELLED'}
        if self.action == 'END_RESULT':
            if ob.as_pointer() in _end_results:
                _restore_end(ob)
            elif mod:
                later = list(ob.modifiers)[list(ob.modifiers).index(mod)+1:]
                _end_results[ob.as_pointer()] = ob, [(m, m.show_viewport) for m in later]
                for m in later:
                    m.show_viewport = False
            return {'FINISHED'}
        if not mod or internal(mod):
            return {'CANCELLED'}
        _restore_end(ob)
        with context.temp_override(object=ob, active_object=ob):
            if symmetry.is_symmetry(mod):
                return bpy.ops.max.symmetry_action(name=mod.name, action=self.action)
            if self.action == 'REMOVE':
                ob.modifiers.remove(mod)
            elif self.action == 'APPLY':
                if ob.mode != 'OBJECT':
                    return {'CANCELLED'}
                bpy.ops.object.modifier_apply(modifier=mod.name)
            else:
                # Move real entries as units; never insert between TS and its helper.
                visible = [m for m in ob.modifiers if not internal(m)]
                index = visible.index(mod)
                target = index + (-1 if self.action == 'UP' else 1)
                if not 0 <= target < len(visible):
                    return {'CANCELLED'}
                bpy.ops.object.modifier_move_to_index(modifier=mod.name,
                    index=list(ob.modifiers).index(visible[target]))
            from . import turbosmooth
            if ob.type == 'MESH':
                turbosmooth.sync(ob)
        return {'FINISHED'}


classes = (MAX_OT_command_panel_rail, MAX_OT_command_stack)
