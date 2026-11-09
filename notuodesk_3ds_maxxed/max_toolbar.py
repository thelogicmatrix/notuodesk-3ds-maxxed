"""Ordered Main Toolbar. Transform, snap, icon and mode services keep their ownership."""
import bpy
import gpu
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, PointerProperty, StringProperty
from . import max_icons, max_status

_commands = {}
_selections = set()


def bounds_hit(points, rectangle, crossing):
    """Window encloses object bounds. Crossing intersects the projected bounds."""
    if not points:
        return False
    x0,y0,x1,y1 = rectangle
    left, right = min(p.x for p in points), max(p.x for p in points)
    bottom, top = min(p.y for p in points), max(p.y for p in points)
    if crossing:
        return right >= x0 and left <= x1 and top >= y0 and bottom <= y1
    return x0 <= left and right <= x1 and y0 <= bottom and top <= y1


def cancel_pending():
    for operator in tuple(_selections):
        operator.cleanup()


class MAX_OT_chrome_rectangle(bpy.types.Operator):
    bl_idname = 'max.chrome_rectangle'
    bl_label = 'Rectangular Selection'
    bl_description = 'Drag a Window or Crossing rectangle over visible object bounds. Right-click cancels'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT'

    def invoke(self, context, event):
        self.area = context.area
        self.window = context.window
        self.start = self.end = None
        self.handle = bpy.types.SpaceView3D.draw_handler_add(self._draw_rectangle, (), 'WINDOW', 'POST_PIXEL')
        _selections.add(self)
        self.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _draw_rectangle(self):
        if bpy.context.area != self.area or self.start is None:
            return
        x0,y0 = self.start
        x1,y1 = self.end
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        batch = batch_for_shader(shader,'LINE_STRIP',{'pos':[(x0,y0),(x1,y0),(x1,y1),(x0,y1),(x0,y0)]})
        shader.bind()
        shader.uniform_float('color', (1.,.8,.1,1.))
        batch.draw(shader)

    def cleanup(self):
        if self.handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle,'WINDOW')
            self.handle = None
        try:
            self.window.cursor_modal_restore()
            self.area.tag_redraw()
        except ReferenceError:
            pass
        _selections.discard(self)

    def cancel(self, context):
        self.cleanup()

    def modal(self, context, event):
        if self not in _selections:
            return {'CANCELLED'}
        if context.area != self.area or event.type in {'ESC','RIGHTMOUSE'}:
            self.cleanup()
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self.start = self.end = (event.mouse_region_x,event.mouse_region_y)
            self.extend, self.subtract = event.shift, event.ctrl
        elif event.type == 'MOUSEMOVE' and self.start is not None:
            self.end = (event.mouse_region_x,event.mouse_region_y)
            self.area.tag_redraw()
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE' and self.start is not None:
            x0,y0 = self.start
            x1,y1 = self.end
            rectangle = min(x0,x1),min(y0,y1),max(x0,x1),max(y0,y1)
            found = []
            for ob in context.visible_objects:
                if ob.hide_select:
                    continue
                corners = [location_3d_to_region_2d(context.region,context.region_data,ob.matrix_world @ Vector(point))
                           for point in ob.bound_box]
                points = [point for point in corners if point is not None]
                if bounds_hit(points,rectangle,context.window_manager.max_chrome_crossing):
                    found.append(ob)
            if not self.extend and not self.subtract:
                for ob in context.selected_objects:
                    ob.select_set(False)
            for ob in found:
                ob.select_set(not self.subtract)
            context.view_layer.objects.active = next(iter(context.selected_objects),None)
            self.cleanup()
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


def configure(commands=None):
    """Map optional host action names to operator IDs after the corresponding batch lands."""
    _commands.clear()
    _commands.update(commands or {})


def available(idname):
    try:
        category, name = idname.split('.')
        getattr(getattr(bpy.ops, category), name).get_rna_type()
        return True
    except (AttributeError, RuntimeError, ValueError):
        return False


def button(layout, command, art, fallback='DOT', *, pressed=False, reason='', **props):
    row = layout.row(align=True)
    row.enabled = available(command) and not reason
    if not row.enabled:
        op = row.operator('max.chrome_unavailable', text='', **max_icons.ui(art, fallback))
        op.reason = reason or 'This command is unavailable until its module is installed'
    else:
        op = row.operator(command, text='', depress=pressed, **max_icons.ui(art, fallback))
        for key, value in props.items():
            setattr(op, key, value)
    return op


def optional(layout, name, art, label):
    button(layout, _commands.get(name, 'max.chrome_unavailable'), art,
           reason='' if name in _commands else label + ' is unavailable until its host module is installed')


class MAX_OT_chrome_unavailable(bpy.types.Operator):
    bl_idname = 'max.chrome_unavailable'
    bl_label = 'Unavailable Command'
    bl_description = 'This command is not supported by the installed modules'
    reason: StringProperty(default='This command is unavailable')

    @classmethod
    def description(cls, context, properties):
        return properties.reason

    def execute(self, context):
        self.report({'WARNING'}, self.reason)
        return {'CANCELLED'}


class MAX_PG_chrome_member(bpy.types.PropertyGroup):
    object: PointerProperty(type=bpy.types.Object)


class MAX_PG_chrome_set(bpy.types.PropertyGroup):
    members: CollectionProperty(type=MAX_PG_chrome_member)


class MAX_OT_chrome_named_set(bpy.types.Operator):
    bl_idname = 'max.chrome_named_set'
    bl_label = 'Named Selection Set'
    bl_description = 'Save, recall or remove an object selection set'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[(v,v.title(),'') for v in ('SAVE', 'RECALL', 'REMOVE')])
    name: StringProperty(name='Selection Set')

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self) if self.action == 'SAVE' else self.execute(context)

    def draw(self, context):
        self.layout.prop(self, 'name', text='Name')

    def execute(self, context):
        if context.mode != 'OBJECT':
            self.report({'WARNING'}, 'Named sets currently store object selections')
            return {'CANCELLED'}
        sets = context.scene.max_chrome_sets
        name = self.name.strip()
        if not name:
            return {'CANCELLED'}
        entry = sets.get(name)
        if self.action == 'SAVE':
            if not context.selected_objects:
                self.report({'WARNING'}, 'Select objects before saving a set')
                return {'CANCELLED'}
            if not entry:
                entry = sets.add()
                entry.name = name
            entry.members.clear()
            for ob in context.selected_objects:
                entry.members.add().object = ob
        elif not entry:
            return {'CANCELLED'}
        elif self.action == 'REMOVE':
            sets.remove(sets.find(name))
        else:
            objects = [member.object for member in entry.members if member.object
                       and context.view_layer.objects.get(member.object.name) == member.object
                       and not member.object.hide_get() and not member.object.hide_select]
            for ob in context.selected_objects:
                ob.select_set(False)
            for ob in objects:
                ob.select_set(True)
            context.view_layer.objects.active = objects[0] if objects else None
        return {'FINISHED'}


class MAX_MT_chrome_sets(bpy.types.Menu):
    bl_label = 'Named Selection Sets'

    def draw(self, context):
        self.layout.operator('max.chrome_named_set', text='Create Selection Set...').action = 'SAVE'
        for entry in context.scene.max_chrome_sets:
            row = self.layout.row(align=True)
            op = row.operator('max.chrome_named_set', text=entry.name)
            op.action, op.name = 'RECALL', entry.name
            op = row.operator('max.chrome_named_set', text='', icon='X')
            op.action, op.name = 'REMOVE', entry.name


class MAX_OT_chrome_selection_tool(bpy.types.Operator):
    bl_idname = 'max.chrome_selection_tool'
    bl_label = 'Selection Region'
    bl_description = 'Use a rectangular, circular or lasso selection region'
    shape: EnumProperty(items=[('RECT','Rectangular Selection',''), ('CIRCLE','Circular Selection',''),
                              ('LASSO','Lasso Selection','')])

    def execute(self, context):
        if self.shape == 'RECT' and context.mode == 'OBJECT':
            bpy.ops.max.chrome_rectangle('INVOKE_DEFAULT')
            return {'FINISHED'}
        name = {'RECT':'builtin.select_box', 'CIRCLE':'builtin.select_circle', 'LASSO':'builtin.select_lasso'}[self.shape]
        bpy.ops.wm.tool_set_by_id(name=name)
        return {'FINISHED'}


class MAX_MT_chrome_region(bpy.types.Menu):
    bl_label = 'Selection Region'

    def draw(self, context):
        for shape, label in (('RECT','Rectangular Selection'), ('CIRCLE','Circular Selection')):
            self.layout.operator('max.chrome_selection_tool', text=label).shape = shape
        row = self.layout.row()
        row.enabled = False
        row.operator('max.chrome_unavailable', text='Fence Selection').reason = 'Fence selection is not supported'
        self.layout.operator('max.chrome_selection_tool', text='Lasso Selection').shape = 'LASSO'
        row = self.layout.row()
        row.enabled = False
        row.operator('max.chrome_unavailable', text='Paint Selection').reason = 'Paint selection is not supported'


class MAX_MT_chrome_align(bpy.types.Menu):
    bl_label = 'Align'

    def draw(self, context):
        for key, label in (('align','Align'), ('quick_align','Quick Align'), ('normal_align','Normal Align'),
                           ('place_highlight','Place Highlight'), ('align_camera','Align Camera'), ('align_view','Align To View')):
            command = _commands.get(key)
            row = self.layout.row()
            row.enabled = command is not None and available(command)
            if row.enabled:
                row.operator(command, text=label)
            else:
                row.operator('max.chrome_unavailable', text=label).reason = label + ' is unavailable'


class MAX_MT_chrome_scale(bpy.types.Menu):
    bl_label = 'Select and Scale'

    def draw(self, context):
        settings = getattr(context.scene, 'max_rotate', None)
        if settings:
            for mode in ('UNIFORM', 'NON_UNIFORM', 'SQUASH'):
                self.layout.operator('max.chrome_scale_mode', text={'UNIFORM':'Select and Uniform Scale',
                    'NON_UNIFORM':'Select and Non-Uniform Scale','SQUASH':'Select and Squash'}[mode],
                    icon='RADIOBUT_ON' if settings.scale_mode == mode else 'RADIOBUT_OFF').mode = mode
        else:
            self.layout.operator('max.select_transform', text='Select and Uniform Scale').kind = 'SCALE'
            for label in ('Non-Uniform Scale', 'Squash'):
                row = self.layout.row()
                row.enabled = False
                row.operator('max.chrome_unavailable', text=label).reason = 'The shared Scale module is not installed'


class MAX_OT_chrome_scale_mode(bpy.types.Operator):
    bl_idname = 'max.chrome_scale_mode'
    bl_label = 'Select and Scale'
    bl_description = 'Activate the shared Scale tool with this scale mode'
    mode: EnumProperty(items=[(v,v.title(),'') for v in ('UNIFORM','NON_UNIFORM','SQUASH')])

    def execute(self, context):
        settings = getattr(context.scene,'max_rotate',None)
        if not settings:
            return {'CANCELLED'}
        settings.scale_mode = self.mode
        from .snaps import select_transform
        select_transform(context,'SCALE')
        return {'FINISHED'}


class MAX_MT_chrome_center(bpy.types.Menu):
    bl_label = 'Use Center'

    def draw(self, context):
        settings = getattr(context.scene, 'max_rotate', None)
        if settings:
            for mode in ('PIVOT', 'SELECTION', 'COORDINATE'):
                self.layout.prop_enum(settings, 'center', mode)
        else:
            row = self.layout.row()
            row.enabled = False
            row.label(text='Transform centre adapter unavailable')


def draw(layout, context):
    """Keep XML-confirmed groups in order. Blender scrolls an overfull header."""
    owner = max_status.feedback()
    row = layout.row(align=True)
    button(row, 'ed.undo', 'undo', 'LOOP_BACK')
    button(row, 'ed.redo', 'redo', 'LOOP_FORWARDS')
    row.separator()
    button(row, 'wm.tool_set_by_id', 'link', 'LINKED', name='max.select_link',
           pressed=bool(owner and owner.tool_pressed(context, 'LINK')),
           reason='' if owner else 'Link picking requires the mode-feedback module')
    button(row, 'object.parent_clear', 'unlink', 'UNLINKED', type='CLEAR_KEEP_TRANSFORM')
    button(row, 'max.chrome_unavailable', 'bind_space_warp', reason='Space Warp binding is not supported')
    row.separator()
    # Filtering must affect actual selection. Do not offer an inert dropdown.
    disabled = row.row()
    disabled.enabled = False
    disabled.operator('max.chrome_unavailable', text='All').reason = 'Only the All selection filter is supported'
    button(row, 'wm.tool_set_by_id', 'select_object', 'RESTRICT_SELECT_OFF', name='builtin.select_box',
           pressed=bool(owner and owner.tool_pressed(context, 'SELECT')))
    optional(row, 'select_by_name', 'select_by_name', 'Select From Scene')
    row.menu('MAX_MT_chrome_region', text='', **max_icons.ui('region_rect', 'SELECT_SET'))
    sub = row.row(align=True)
    sub.enabled = context.mode == 'OBJECT'
    sub.prop(context.window_manager, 'max_chrome_crossing', text='', toggle=True,
             **max_icons.ui('window_crossing', 'SELECT_INTERSECT'))
    row.separator()
    for kind, art in (('MOVE','move'), ('ROTATE','rotate'), ('SCALE','scale')):
        button(row, 'max.select_transform', art, 'ORIENTATION_GLOBAL', kind=kind,
               pressed=bool(owner and owner.tool_pressed(context, kind)))
        if kind == 'SCALE':
            row.menu('MAX_MT_chrome_scale', text='', icon='DOWNARROW_HLT')
    optional(row, 'select_place', 'select_place', 'Select and Place')
    row.separator()
    settings = getattr(context.scene, 'max_rotate', None)
    if settings:
        row.prop(settings, 'reference', text='')
        if settings.reference == 'PICK':
            row.prop(settings, 'pick', text='')
    else:
        disabled = row.row()
        disabled.enabled = False
        disabled.label(text='Reference unavailable')
    row.menu('MAX_MT_chrome_center', text='', **max_icons.ui('pivot', 'PIVOT_MEDIAN'))
    row.separator()
    optional(row, 'shortcut_override', 'shortcut_override', 'Keyboard Shortcut Override')
    from . import snaps
    snaps.draw_toolbar(row, context)
    row.separator()
    row.menu('MAX_MT_chrome_sets', text='Named Selection Sets')
    row.separator()
    optional(row, 'mirror', 'mirror', 'Mirror')
    row.menu('MAX_MT_chrome_align', text='', **max_icons.ui('align', 'ALIGN_CENTER'))
    row.separator()
    for key, art, label in (('scene_explorer','scene_explorer','Scene Explorer'),
                            ('layer_explorer','layer_explorer','Layer Explorer'),
                            ('ribbon','ribbon','Toggle Ribbon'), ('track_view','track_view','Track View'),
                            ('schematic_view','schematic_view','Schematic View')):
        optional(row, key, art, label)


classes = (MAX_OT_chrome_unavailable, MAX_PG_chrome_member, MAX_PG_chrome_set,
           MAX_OT_chrome_named_set, MAX_MT_chrome_sets, MAX_OT_chrome_selection_tool,
           MAX_MT_chrome_region, MAX_MT_chrome_align, MAX_MT_chrome_scale, MAX_MT_chrome_center,
           MAX_OT_chrome_rectangle, MAX_OT_chrome_scale_mode)
