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
    if getattr(context, 'region_data', None) is not None or not context.window:
        return {}
    from . import max_chrome
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
        field.prop(context.window_manager, 'max_chrome_' + field_name, index=i, text=name + ':')
    row.separator()
    row.label(text=grid_text(context))


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


classes = (MAX_OT_chrome_typein,)
