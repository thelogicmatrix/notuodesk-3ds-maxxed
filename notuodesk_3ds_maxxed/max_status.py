"""Status readouts and a prompt adapter. mode_feedback owns selection and guidance."""
import importlib
import math

import bpy
from mathutils import Matrix, Vector

_feedback = None
_reader = None
_writer = None
_live = {}
_message = ''
_edits = {}


def configure(*, feedback=None, reader=None, writer=None):
    """Bind feedback and optional shared transform read/write callbacks at integration."""
    global _feedback, _reader, _writer
    _feedback, _reader, _writer = feedback, reader, writer


def feedback():
    if _feedback:
        return _feedback
    try:
        return importlib.import_module('.mode_feedback', __package__)
    except ModuleNotFoundError as exc:
        if exc.name != __package__ + '.mode_feedback':
            raise
        return None


def selection_text(context):
    owner = feedback()
    return owner.selection_text(context) if owner else 'Selection feedback unavailable'


def prompt_text(context):
    if _message:
        return _message
    # Keep an active command's actionable instructions ahead of idle tool guidance.
    text = getattr(context.workspace, 'status_text', None)
    if text:
        return text
    owner = feedback()
    return owner.prompt_text(context) if owner else ''


def notify(message=''):
    global _message
    _message = message
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def publish(context, kind, values):
    """Shared transform owner publishes APPLIED start-relative XYZ during a modal drag."""
    _live[context.window.as_pointer() if context.window else 0] = (kind, tuple(values))


def clear(context=None):
    if context is None:
        _live.clear()
        _edits.clear()
        notify()
    else:
        _live.pop(context.window.as_pointer() if context.window else 0, None)


def tool(context):
    owner = feedback()
    if owner:
        return owner.active_tool(context)
    active = context.workspace.tools.from_space_view3d_mode(context.mode, create=False) if context.workspace else None
    name = active.idname if active else ''
    return next((kind for kind in ('MOVE', 'ROTATE', 'SCALE') if name.endswith(kind.lower())), 'MOVE')


def basis(context):
    override = _viewport(context)
    if override:
        with context.temp_override(**override):
            return _basis(bpy.context)
    return _basis(context)


def _viewport(context):
    from . import max_chrome
    if not context.window:
        return {}
    if getattr(context, 'region_data', None) is not None and not max_chrome.timeline_area(context.area):
        return {}
    areas = [area for area in context.window.screen.areas if area.type == 'VIEW_3D' and not max_chrome.timeline_area(area)]
    if not areas:
        return {}
    area = max(areas,key=lambda area:area.width*area.height)
    region = next((region for region in area.regions if region.type == 'WINDOW'),None)
    return {'area':area, 'region':region} if region else {}


def _basis(context):
    try:
        owner = importlib.import_module('.max_rotate', __package__)
    except ModuleNotFoundError as exc:
        if exc.name != __package__ + '.max_rotate':
            raise
        from . import snaps
        return snaps.orientation_basis(context)
    return owner.reference_basis(context)


def coordinate_origin(context):
    settings = getattr(context.scene, 'max_rotate', None)
    ob = context.active_object
    if settings:
        ref = settings.reference
        target = settings.pick if ref == 'PICK' else ob.parent if ref == 'PARENT' and ob else ob if ref == 'LOCAL' else None
        if target:
            return target.matrix_world.translation.copy()
    return Vector()


def readout(context, offset=False):
    """Return kind, XYZ and unit category, or no values for unsupported/mixed selection."""
    if _reader:
        override = _viewport(context)
        if override:
            with context.temp_override(**override):
                return _reader(bpy.context, offset)
        return _reader(context, offset)
    kind = tool(context)
    unit = {'MOVE': 'LENGTH', 'ROTATE': 'ROTATION', 'SCALE': 'PERCENT'}.get(kind, 'LENGTH')
    live = _live.get(context.window.as_pointer() if context.window else 0)
    if offset:
        return (kind, live[1] if live and live[0] == kind else None, unit)
    ob = context.active_object
    if not ob or not context.selected_objects:
        return kind, None, unit
    if context.mode != 'OBJECT' or len(context.selected_objects) != 1:
        # The shared transform owner must supply effective sub-object and mixed readouts.
        return kind, None, unit
    axes = basis(context)
    if kind == 'ROTATE':
        matrix = axes.inverted_safe() @ ob.matrix_world.to_quaternion().to_matrix() @ axes
        return kind, tuple(matrix.to_euler()), unit
    if kind == 'SCALE':
        matrix = axes.inverted_safe() @ ob.matrix_world.to_3x3() @ axes
        return kind, tuple(value * 100 for value in matrix.to_scale()), unit
    return kind, tuple(axes.inverted_safe() @ (ob.matrix_world.translation-coordinate_origin(context))), unit


def format_value(scene, value, unit):
    if unit == 'ROTATION':
        return f'{math.degrees(value):.2f}°'
    if unit == 'PERCENT':
        return f'{value:.2f}%'
    settings = scene.unit_settings
    if settings.system == 'NONE':
        return f'{value:.3f}'
    fixed = {'KILOMETERS':(1000,'km'), 'METERS':(1,'m'), 'CENTIMETERS':(.01,'cm'),
             'MILLIMETERS':(.001,'mm'), 'MICROMETERS':(.000001,'µm'),
             'MILES':(1609.344,'mi'), 'FEET':(.3048,'ft'), 'INCHES':(.0254,'in'),
             'THOU':(.0000254,'thou')}.get(settings.length_unit)
    if fixed:
        divisor, suffix = fixed
        return f'{value*settings.scale_length/divisor:.3f} {suffix}'
    return bpy.utils.units.to_string(settings.system, 'LENGTH', value * settings.scale_length,
                                     precision=4, split_unit=False)


def grid_text(context):
    from . import get_prefs
    prefs = get_prefs()
    spacing = prefs.snap_settings.grid_spacing if prefs else None
    return 'Grid = ' + (format_value(context.scene, spacing, 'LENGTH') if spacing is not None else 'unavailable')


def draw(layout, context):
    # Max's prompt is below the selection/type-in row. Blender's global status
    # header is the bottommost row, while the time host owns the row above it.
    if context.area is None or context.area.type not in {'VIEW_3D', 'DOPESHEET_EDITOR'}:
        row = layout.row(align=True)
        row.label(text=prompt_text(context))
        row.separator_spacer()
        frame = row.row(align=True)
        frame.ui_units_x = 4
        frame.prop(context.scene, 'frame_current', text='')
        row.operator('max.chrome_time_config', text='', icon='TIME')
        row.operator('max.chrome_key', text='Set Key').remove = False
        return
    row = layout.row(align=True)
    selection = row.row(align=True)
    selection.ui_units_x = 20
    selection.label(text=selection_text(context))
    row.separator()
    offset = getattr(context.window_manager, 'max_chrome_offset', False)
    row.prop(context.window_manager, 'max_chrome_offset', text='', icon='DRIVER_TRANSFORM', toggle=True)
    _, values, unit = readout(context, offset)
    field_name = {'ROTATION': 'rotation', 'PERCENT': 'scale'}.get(unit, 'position')
    for i, name in enumerate('XYZ'):
        field = row.row(align=True)
        field.ui_units_x = 4
        field.enabled = _writer is not None and values is not None
        field.label(text=name + ':')
        if values is None:
            field.operator('max.chrome_unavailable',text=' ',emboss=True).reason = 'No transform selection'
        else:
            field.prop(context.window_manager, 'max_chrome_' + field_name, index=i, text='')
    row.separator()
    row.label(text=grid_text(context))


def status_items(context):
    """The two 22px Max rows, in the same WINDOW region as the time track."""
    scale = context.preferences.system.ui_scale
    width = context.region.width/scale
    right = max(100,width-372)
    field_start = max(285,right-337)
    offset = context.window_manager.max_chrome_offset
    _,values,unit = readout(context,offset)
    items = [dict(key='listener',rect=(0,0,100,44),text='MAXScript',enabled=False),
             dict(key='selection',rect=(106,23,field_start-50,43),text=selection_text(context),enabled=True),
             dict(key='selection_lock',rect=(field_start-29,22,field_start-9,44),art='status_lock',enabled=False),
             dict(key='absolute_offset',rect=(field_start-8,22,field_start+14,44),
                  art='status_offset' if offset else 'status_absolute',enabled=True),
             dict(key='prompt',rect=(106,1,right-108,21),text=prompt_text(context),enabled=True),
             dict(key='time_tag',rect=(right-105,1,right,21),text='Add Time Tag',art='status_time_tag',enabled=True)]
    editing = _edits.get(context.window.as_pointer())
    for i,axis in enumerate('XYZ'):
        text = format_value(context.scene,values[i],unit) if values is not None else ''
        if editing and editing[0] == i:
            text = editing[1]+'|'
        x = field_start+17+i*74
        items.append(dict(key='xyz',axis=i,rect=(x,23,x+70,43),text=text,label=axis+':',
                          enabled=_writer is not None and values is not None))
    items.append(dict(key='grid',rect=(field_start+241,23,right,43),text=grid_text(context),enabled=True))
    for item in items:
        item['rect'] = tuple(value*scale for value in item['rect'])
    return items


def draw_pixels(context):
    from . import max_icons, max_timeline as time
    import gpu
    scale = context.preferences.system.ui_scale
    time._rectangle(0,0,context.region.width,44*scale,(.267,.267,.267,1))
    gpu.state.blend_set('ALPHA')
    for item in status_items(context):
        x0,y0,x1,y1 = item['rect']
        key = item['key']
        if key == 'listener':
            time._frame(x0+scale,y0+scale,x1-scale,y1-scale,(.65,.65,.65,1))
            time._rectangle(x0+3*scale,23*scale,x1-3*scale,41*scale,(.65,.58,.58,1))
            time._rectangle(x0+3*scale,3*scale,x1-3*scale,21*scale,(.82,.82,.82,1))
            time._text(x0+5*scale,7*scale,'MAXScript',round(10*scale),(.28,.28,.28,1))
            continue
        if key in {'selection','prompt','grid','time_tag'}:
            time._frame(x0,y0,x1,y1,(.267,.267,.267,1))
        if key == 'xyz':
            time._text(x0,y0+6*scale,item['label'],round(10*scale))
            time._frame(x0+14*scale,y0,x1,y1,(.33,.33,.33,1))
            # Reserve the narrow spinner gutter, including inactive empty fields.
            time._rectangle(x1-7*scale,y0+scale,x1-6*scale,y1-scale,(.25,.25,.25,1))
            time._text(x1-7*scale,y0+9*scale,'\u2303',round(7*scale))
            time._text(x1-7*scale,y0+2*scale,'\u2304',round(7*scale))
        if item.get('art'):
            gpu.state.blend_set('ALPHA')
            max_icons.draw(item['art'],x0+10*scale,(y0+y1)/2,18*scale)
        if item.get('text'):
            dx = 16 if key == 'xyz' else 23 if item.get('art') else 5
            # Long selection or command text must not overwrite the next field.
            import blf
            face = time.font()
            blf.size(face,round(10*scale))
            blf.enable(face,blf.CLIPPING)
            blf.clipping(face,x0+dx*scale,y0,x1-(8 if key=='xyz' else 2)*scale,y1)
            time._text(x0+dx*scale,y0+6*scale,item['text'],round(10*scale))
            blf.disable(face,blf.CLIPPING)
        if not item['enabled'] and key != 'xyz':
            gpu.state.blend_set('ALPHA')
            time._rectangle(x0,y0,x1,y1,(.267,.267,.267,.45))
    gpu.state.blend_set('NONE')


def pointer(context,x,y):
    item = next((item for item in status_items(context) if item['rect'][0] <= x < item['rect'][2]
                 and item['rect'][1] <= y < item['rect'][3]),None)
    if item is None:
        return False
    if not item['enabled']:
        return True
    if item['key'] == 'absolute_offset':
        context.window_manager.max_chrome_offset = not context.window_manager.max_chrome_offset
    elif item['key'] == 'time_tag':
        bpy.ops.max.chrome_time_tag('INVOKE_DEFAULT')
    elif item['key'] == 'xyz':
        scale = context.preferences.system.ui_scale
        step = 0
        if x >= item['rect'][2]-8*scale:
            step = 1 if y >= (item['rect'][1]+item['rect'][3])/2 else -1
        bpy.ops.max.chrome_number('INVOKE_DEFAULT',axis=item['axis'],step=step)
    return True


class MAX_OT_chrome_number(bpy.types.Operator):
    bl_idname = 'max.chrome_number'
    bl_label = 'Transform Coordinate'
    bl_description = 'Type a coordinate, Enter applies and right-click cancels'
    bl_options = {'UNDO', 'BLOCKING'}
    axis: bpy.props.IntProperty(min=0,max=2)
    step: bpy.props.IntProperty(default=0)

    def invoke(self, context, event):
        _,values,self.unit = readout(context,context.window_manager.max_chrome_offset)
        if values is None or _writer is None:
            return {'CANCELLED'}
        if self.step:
            values = list(values)
            values[self.axis] += self.step*(math.pi/180 if self.unit == 'ROTATION' else 1)
            set_values(context.window_manager,values)
            return {'FINISHED'}
        self.text = format_value(context.scene,values[self.axis],self.unit)
        self.replace = True
        self.window_id = context.window.as_pointer()
        _edits[self.window_id] = self.axis,self.text
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'ESC','RIGHTMOUSE'}:
            _edits.pop(self.window_id,None)
            context.area.tag_redraw()
            return {'CANCELLED'}
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if event.type in {'RET','NUMPAD_ENTER'}:
            try:
                text = self.text.replace('%','').replace('\u00b0','').strip()
                if self.unit == 'ROTATION':
                    value = math.radians(float(text))
                elif self.unit == 'LENGTH' and context.scene.unit_settings.system != 'NONE':
                    settings = context.scene.unit_settings
                    value = bpy.utils.units.to_value(settings.system,'LENGTH',text)/settings.scale_length
                else:
                    value = float(text)
                _,values,_ = readout(context,context.window_manager.max_chrome_offset)
                if values is None:
                    raise ValueError('Transform selection changed')
                values = list(values)
                values[self.axis] = value
                set_values(context.window_manager,values)
            except (ValueError,TypeError):
                self.report({'WARNING'},'Enter a valid coordinate')
                return {'RUNNING_MODAL'}
            _edits.pop(self.window_id,None)
            context.area.tag_redraw()
            return {'FINISHED'}
        if event.type == 'A' and event.ctrl:
            self.replace = True
        elif event.type == 'BACK_SPACE':
            self.text = '' if self.replace else self.text[:-1]
            self.replace = False
        elif event.type == 'V' and event.ctrl:
            self.text = context.window_manager.clipboard if self.replace else self.text+context.window_manager.clipboard
            self.replace = False
        elif event.unicode and event.unicode.isprintable():
            self.text = event.unicode if self.replace else self.text+event.unicode
            self.replace = False
        _edits[self.window_id] = self.axis,self.text
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}


def get_values(self):
    _, values, _ = readout(bpy.context, self.max_chrome_offset)
    return values if values is not None else (0., 0., 0.)


def set_values(self, values):
    context = bpy.context
    if _writer is None or readout(context, self.max_chrome_offset)[1] is None:
        return
    override = _viewport(context)
    if override:
        with context.temp_override(**override):
            _writer(bpy.context, tuple(values), self.max_chrome_offset)
    else:
        _writer(context, tuple(values), self.max_chrome_offset)


class MAX_OT_chrome_typein(bpy.types.Operator):
    bl_idname = 'max.chrome_typein'
    bl_label = 'Transform Type-In'
    bl_description = 'Enter X, Y and Z through the shared transform adapter'
    bl_options = {'REGISTER', 'UNDO'}
    move_values: bpy.props.FloatVectorProperty(name='Position', size=3, subtype='TRANSLATION', unit='LENGTH')
    rotate_values: bpy.props.FloatVectorProperty(name='Rotation', size=3, subtype='EULER', unit='ROTATION')
    scale_values: bpy.props.FloatVectorProperty(name='Scale (%)', size=3, default=(100,100,100))

    def _field(self, context):
        kind, _, _ = readout(context, context.window_manager.max_chrome_offset)
        return {'ROTATE':'rotate_values','SCALE':'scale_values'}.get(kind,'move_values')

    @classmethod
    def poll(cls, context):
        return _writer is not None

    def invoke(self, context, event):
        _, values, _ = readout(context, context.window_manager.max_chrome_offset)
        if values is None:
            return {'CANCELLED'}
        setattr(self, self._field(context), values)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        for i, axis in enumerate('XYZ'):
            self.layout.prop(self, self._field(context), index=i, text=axis)

    def execute(self, context):
        if not _writer:
            return {'CANCELLED'}
        values = tuple(getattr(self,self._field(context)))
        override = _viewport(context)
        if override:
            with context.temp_override(**override):
                result = _writer(bpy.context, values, context.window_manager.max_chrome_offset)
        else:
            result = _writer(context, values, context.window_manager.max_chrome_offset)
        return {'FINISHED'} if result else {'CANCELLED'}


classes = (MAX_OT_chrome_typein, MAX_OT_chrome_number)
