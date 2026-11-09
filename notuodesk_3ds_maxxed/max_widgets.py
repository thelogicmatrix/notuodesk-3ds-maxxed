"""Compact parameter rows shared by Command Panel drawing callbacks."""
import math
import bpy
from bpy.props import FloatProperty, IntProperty, StringProperty

_spinner_policy = None


def set_spinner_policy(callback=None):
    """Host callback(context, data, property) returns enabled, increment in data units."""
    global _spinner_policy
    _spinner_policy = callback


def snap_value(value, increment, enabled=True):
    if not enabled or increment <= 0 or not math.isfinite(value):
        return value
    return round(value / increment) * increment


def compact(layout):
    layout.use_property_split = False
    layout.use_property_decorate = False
    return layout


def _read(data, prop, index=-1):
    value = data.path_resolve(prop)
    return value[index] if index >= 0 else value


def _write(data, prop, value, index=-1):
    current = _read(data, prop, index)
    value = int(round(value)) if isinstance(current, int) and not isinstance(current, bool) else value
    if index >= 0:
        vector = list(data.path_resolve(prop))
        vector[index] = value
        value = vector
    if prop.startswith('["') and prop.endswith('"]'):
        data[prop[2:-2]] = value
    else:
        setattr(data, prop, value)
    owner = getattr(data, 'id_data', None)
    if owner:
        owner.update_tag()


def spinner(layout, data, prop, label, *, enabled=True, step=.1, arrows=True, index=-1):
    if _spinner_policy:
        snap_enabled, snap_increment = _spinner_policy(bpy.context, data, prop)
        if snap_enabled and snap_increment > 0:
            step = snap_increment
    row = compact(layout.row(align=True))
    row.enabled = enabled
    split = row.split(factor=.53, align=True)
    left = split.row()
    left.alignment = 'RIGHT'
    left.label(text=label.rstrip(':') + ':')
    field = split.row(align=True)
    field.prop(data, prop, text='', index=index)
    if arrows:
        field.context_pointer_set('max_widget_owner', data)
        buttons = field.column(align=True)
        buttons.ui_units_x = .65
        buttons.scale_y = .5
        for sign, icon in ((1, 'TRIA_UP'), (-1, 'TRIA_DOWN')):
            op = buttons.operator('max.widget_adjust', text='', icon=icon, emboss=False)
            op.property_name = prop
            op.property_index = index
            op.increment = step * sign
    return row


def checkbox(layout, data, prop, label=None, *, enabled=True):
    row = compact(layout.row(align=True))
    row.enabled = enabled
    row.prop(data, prop, text=label if label is not None else '')
    return row


def radios(layout, data, prop, items, *, enabled=True):
    row = compact(layout.row(align=True))
    row.enabled = enabled
    row.emboss = 'NONE'
    value = getattr(data, prop)
    for identifier, label in items:
        row.prop_enum(data, prop, identifier, text=label,
                      icon='RADIOBUT_ON' if value == identifier else 'RADIOBUT_OFF')
    return row


def command(layout, operator, text, *, settings=None, settings_icon='PREFERENCES', enabled=True):
    row = compact(layout.row(align=True))
    row.enabled = enabled
    main = row.operator(operator, text=text)
    companion = row.operator(settings, text='', icon=settings_icon) if settings else None
    return main, companion


def group(layout, title):
    box = compact(layout.box())
    box.label(text=title)
    return box.column(align=True)


class MAX_OT_widget_adjust(bpy.types.Operator):
    bl_idname = 'max.widget_adjust'
    bl_label = 'Adjust Spinner'
    bl_description = 'Click to step, drag to adjust, right-click or Esc to cancel'
    bl_options = {'INTERNAL', 'UNDO'}
    property_name: StringProperty()
    property_index: IntProperty(default=-1)
    increment: FloatProperty(default=.1)

    def _change(self, context, delta):
        enabled, increment = _spinner_policy(context, self.data, self.property_name) if _spinner_policy else (False, 0.)
        candidate = self.original + delta
        _write(self.data, self.property_name, snap_value(candidate, increment, enabled), self.property_index)

    def invoke(self, context, event):
        self.data = getattr(context, 'max_widget_owner', None)
        if self.data is None:
            return {'CANCELLED'}
        self.original = _read(self.data, self.property_name, self.property_index)
        self.start_y = event.mouse_y
        self._change(context, self.increment)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            _write(self.data, self.property_name, self.original, self.property_index)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        if event.type == 'MOUSEMOVE':
            multiplier = .1 if event.shift else 1.
            self._change(context, self.increment + (event.mouse_y-self.start_y) * abs(self.increment) * multiplier)
        return {'RUNNING_MODAL'}


classes = (MAX_OT_widget_adjust,)
