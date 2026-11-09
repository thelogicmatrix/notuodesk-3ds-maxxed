"""Supported Max modifier parameters. The wave-2 host owns panel registration."""
import bpy
import math
from bpy.props import EnumProperty, FloatProperty, IntProperty, PointerProperty
from . import ffd, gn_mods, max_widgets as w, turbosmooth

_targets = {}
_installations = {}
_SOLIDITY_VALUES = (2., .5, .4, .1)

CATALOGUE = (
    ('BEND', 'Bend', 'Bend angle and axis using simple deformation'),
    ('SHELL', 'Shell', 'Inner and outer shell thickness'),
    ('CHAMFER', 'Chamfer', 'Edge chamfer amount and segments'),
    ('ARRAY', 'Array', 'One-dimensional linear array'),
    ('BOOLEAN', 'Boolean', 'Union, intersection or subtraction against an operand'),
    ('UVW_MAP', 'UVW Map', 'Planar projection from a projector object'),
    *((kind.upper(), kind, 'Editable ' + kind + ' deformer') for kind in gn_mods.PARAMETERS),
    ('FFD2', 'FFD 2x2x2', 'Eight control points'),
    ('FFD3', 'FFD 3x3x3', 'Twenty-seven control points'),
    ('FFD4', 'FFD 4x4x4', 'Sixty-four control points'),
    ('FFD', 'FFD (box)', 'Settable cage dimensions'),
    ('TURBOSMOOTH', 'TurboSmooth', 'Subdivision with per-entry surface controls'),
)
LIMITS = {
    'BEND': 'Angle and principal axis. Direction and world-space limits are unavailable.',
    'SHELL': 'Inner/outer offsets of the input surface. Complex intersections can overlap.',
    'CHAMFER': 'Edge amount and segment count. Max quad chamfer modes are unavailable.',
    'ARRAY': 'One-dimensional constant translation. Rotation and scale arrays are unavailable.',
    'BOOLEAN': 'Exact mesh operations against one object. Material transfer follows Blender.',
    'UVW_MAP': 'Planar projector and existing UV channel. Box, spherical and cylindrical mapping are unavailable.',
    'Melt': 'Local Z collapse with radial spread. Material presets shape the falloff, not a physical simulation.',
    'Slice': 'Capped plane cut on solid meshes. Height is a local Z bounds fraction. Open, nonmanifold and uncapped cuts are unsupported.',
    'Noise': 'Spatial noise with a repeatable seed. Fractal Detail is the saved Maxxed input.',
    'FFD': 'Lattice interpolation equivalents. Conform uses nearest-face normals.',
    'TURBOSMOOTH': 'Catmull-Clark refinement. Creases preserve material and smoothing-group boundaries.',
}


def is_internal(mod):
    group = getattr(mod, 'node_group', None)
    return bool(group and (group.get('max_ts_support') or mod.name.startswith('_MAX Text Origin')))


def active_modifier(context):
    ob = context.object
    if ob and ob.type == 'LATTICE':
        return ffd.modifier(ob)
    if ob is None:
        return None
    index = getattr(ob, 'max_stack_index', None)
    if index == -1:
        return None
    if index is not None and 0 <= index < len(ob.modifiers):
        return ob.modifiers[index]
    chosen = ob.modifiers.get(ob.get('max_adapter_active', ''))
    return chosen or next((m for m in reversed(ob.modifiers) if not is_internal(m)), None)


def select_modifier(ob, mod):
    if not ob or not mod or mod.id_data != ob:
        return False
    _targets[ob.as_pointer()] = mod
    ob['max_adapter_active'] = mod.name
    if hasattr(ob, 'max_stack_index'):
        ob.max_stack_index = ob.modifiers.find(mod.name)
    if mod.type == 'LATTICE':
        ffd.select_modifier(ob, mod)
    elif mod.type == 'SUBSURF':
        turbosmooth.select_modifier(ob, mod)
    return True


def _shell(settings):
    ob = settings.id_data
    mod = _bound(ob) or ob.modifiers.get(ob.get('max_adapter_active', ''))
    if mod is None or mod.type != 'SOLIDIFY':
        index = getattr(ob, 'max_stack_index', -1)
        mod = ob.modifiers[index] if 0 <= index < len(ob.modifiers) else None
    return mod if mod and mod.type == 'SOLIDIFY' else None


def _shell_value(settings, sign):
    mod = _shell(settings)
    return mod.thickness * (1 + sign * mod.offset) * .5 if mod else 0.


def _shell_put(settings, value, sign):
    mod = _shell(settings)
    if mod:
        inner = value if sign == -1 else _shell_value(settings, -1)
        outer = value if sign == 1 else _shell_value(settings, 1)
        mod.thickness = inner + outer
        mod.offset = (outer-inner) / mod.thickness if abs(mod.thickness) > 1e-10 else 0.


class MaxModifierParameters(bpy.types.PropertyGroup):
    shell_inner: FloatProperty(name='Inner Amount', min=0, unit='LENGTH',
                               get=lambda s: _shell_value(s, -1), set=lambda s, v: _shell_put(s, v, -1))
    shell_outer: FloatProperty(name='Outer Amount', min=0, unit='LENGTH',
                               get=lambda s: _shell_value(s, 1), set=lambda s, v: _shell_put(s, v, 1))
    melt_solidity: EnumProperty(name='Solidity', items=(('ICE', 'Ice', ''), ('GLASS', 'Glass', ''),
                                                       ('JELLY', 'Jelly', ''), ('PLASTIC', 'Plastic', ''),
                                                       ('CUSTOM', 'Custom', 'Continuous saved or animated value')),
                                get=lambda s: _solidity_get(s), set=lambda s, v: _solidity_put(s, v))


def _solidity_modifier(settings):
    ob = settings.id_data
    mod = _bound(ob) or ob.modifiers.get(ob.get('max_adapter_active', ''))
    return mod if mod and gn_mods.identify(mod) == 'Melt' else None


def _solidity_get(settings):
    mod = _solidity_modifier(settings)
    value = gn_mods.value(mod, 'Solidity', 2.) if mod else 2.
    # Tolerate socket float precision without rounding arbitrary values to presets.
    return next((i for i, preset in enumerate(_SOLIDITY_VALUES)
                 if math.isclose(value, preset, rel_tol=0., abs_tol=1e-8)), 4)


def _solidity_put(settings, value):
    mod = _solidity_modifier(settings)
    if mod and 0 <= value < len(_SOLIDITY_VALUES):
        gn_mods.set_input(mod, 'Solidity', _SOLIDITY_VALUES[value])


def add_modifier(ob, kind):
    title = next((name for token, name, _ in CATALOGUE if token == kind), kind)
    if title in gn_mods.PARAMETERS:
        return gn_mods.add(ob, title)
    if kind.startswith('FFD'):
        return ffd.add(ob, int(kind[-1]) if kind[-1].isdigit() else 4)
    if kind == 'TURBOSMOOTH':
        return turbosmooth.add(ob)
    backend = {'BEND': 'SIMPLE_DEFORM', 'SHELL': 'SOLIDIFY', 'CHAMFER': 'BEVEL',
               'ARRAY': 'ARRAY', 'BOOLEAN': 'BOOLEAN', 'UVW_MAP': 'UV_PROJECT'}.get(kind)
    if backend is None or ob is None or ob.type != 'MESH':
        return None
    mod = ob.modifiers.new(title, backend)
    if kind == 'BEND':
        mod.deform_method = 'BEND'
    elif kind == 'ARRAY':
        mod.use_relative_offset = False
        mod.use_constant_offset = True
        mod.constant_offset_displace = (1, 0, 0)
    elif kind == 'BOOLEAN' and hasattr(mod, 'solver'):
        mod.solver = 'EXACT'
    return mod


class MAX_OT_modifier_list(bpy.types.Operator):
    bl_idname = 'max.modifier_list'
    bl_label = 'Modifier List'
    bl_description = 'Search the supported modifiers'
    bl_options = {'REGISTER', 'UNDO'}
    bl_property = 'kind'
    kind: EnumProperty(items=CATALOGUE)

    @classmethod
    def poll(cls, context):
        return bool(context.object and context.object.type == 'MESH' and context.object.mode == 'OBJECT')

    def invoke(self, context, _event):
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        mod = add_modifier(context.object, self.kind)
        if mod:
            select_modifier(context.object, mod)
            return {'FINISHED'}
        return {'CANCELLED'}


class MAX_OT_modifier_pick(bpy.types.Operator):
    bl_idname = 'max.modifier_pick'
    bl_label = 'Select Modifier'
    bl_description = 'Show the parameters for this stack entry'
    index: IntProperty(default=-1)

    def execute(self, context):
        ob = context.object
        if not ob:
            return {'CANCELLED'}
        if self.index == -1:
            if hasattr(ob, 'max_stack_index'):
                ob.max_stack_index = -1
            ob['max_adapter_active'] = ''
            return {'FINISHED'}
        if not 0 <= self.index < len(ob.modifiers):
            return {'CANCELLED'}
        return {'FINISHED'} if select_modifier(ob, ob.modifiers[self.index]) else {'CANCELLED'}


def draw_selector(layout, context):
    row = w.compact(layout.row())
    row.enabled = bool(context.object and context.object.type == 'MESH')
    row.operator('max.modifier_list', text='Modifier List', icon='DOWNARROW_HLT')


def stack_rows(ob):
    if ob is None:
        return ()
    rows = [(i, mod.name, ('Control Points', 'Lattice') if mod.type == 'LATTICE' else ())
            for i, mod in reversed(list(enumerate(ob.modifiers))) if not is_internal(mod)]
    rows.append((-1, ob.name, ()))
    return tuple(rows)


def draw_stack(layout, context):
    ob = context.object
    current = active_modifier(context)
    box = w.compact(layout.box())
    for index, label, children in stack_rows(ob):
        row = box.row(align=True)
        op = row.operator('max.modifier_pick', text=label, emboss=False,
                          icon='RADIOBUT_ON' if current and index >= 0 and ob.modifiers[index] == current else 'RADIOBUT_OFF')
        op.index = index
        if current and index >= 0 and ob.modifiers[index] == current:
            for level, child in zip(('POINTS', 'LATTICE'), children):
                line = box.row(align=True)
                line.separator(factor=2)
                line.operator('max.ffd_level', text=child, emboss=False).level = level


def _unavailable(layout, label):
    row = layout.row()
    row.enabled = False
    row.label(text=label)


def _named(layout, mod, names):
    available = dict((label, ident) for ident, label in gn_mods.inputs(mod))
    for label in names:
        ident = available.get(label)
        if ident is None or ident not in mod:
            _unavailable(layout, label)
            continue
        data, prop = gn_mods.input_ref(mod, ident)
        val = data.path_resolve(prop)
        if isinstance(val, bool):
            w.checkbox(layout, data, prop, label)
        else:
            w.spinner(layout, data, prop, label)


def _draw_ffd(layout, ob, mod):
    ffd.bind_modifier(ob, mod)
    if mod.object is None:
        _unavailable(layout, 'FFD cage is missing')
        return
    settings = ob.max_ffd
    dimensions = w.group(layout, 'Dimensions')
    for prop, label in (('points_u', 'Length'), ('points_v', 'Width'), ('points_w', 'Height')):
        w.spinner(dimensions, settings, prop, label, step=1)
    dimensions.label(text='Changing dimensions resets control points')
    display = w.group(layout, 'Display')
    w.checkbox(display, settings, 'show_lattice', 'Lattice')
    w.checkbox(display, settings, 'in_front', 'See-Through')
    deform = w.group(layout, 'Deform')
    w.radios(deform, settings, 'deform_mode', (('VOLUME', 'Only In Volume'), ('ALL', 'All Vertices')))
    w.spinner(deform, settings, 'falloff', 'Falloff', enabled=settings.deform_mode == 'ALL')
    control = w.group(layout, 'Control Points')
    w.command(control, 'max.ffd_fit', 'Fit to Object')
    w.command(control, 'max.ffd_reset', 'Reset')
    w.command(control, 'max.ffd_animate_all', 'Animate All')
    w.checkbox(control, settings, 'conform_inside', 'Inside Points')
    w.checkbox(control, settings, 'conform_outside', 'Outside Points')
    w.spinner(control, settings, 'offset', 'Offset')
    w.command(control, 'max.ffd_conform', 'Conform to Shape')
    equivalent = w.group(layout, 'Supported Interpolation')
    equivalent.prop(settings, 'interpolation', text='')


def _draw_ts(layout, ob, mod):
    turbosmooth.bind_modifier(ob, mod)
    settings = ob.max_turbosmooth
    main = w.group(layout, 'Main')
    w.spinner(main, settings, 'iterations', 'Iterations', step=1)
    w.checkbox(main, settings, 'render_iters_on', 'Render Iters')
    w.spinner(main, settings, 'render_iters', 'Render Iterations', enabled=settings.render_iters_on, step=1)
    w.checkbox(main, settings, 'isoline', 'Isoline Display')
    w.checkbox(main, settings, 'explicit_normals', 'Explicit Normals', enabled=hasattr(mod, 'use_custom_normals'))
    surface = w.group(layout, 'Surface Parameters')
    w.checkbox(surface, settings, 'smooth_result', 'Smooth Result')
    surface.label(text='Separate by:')
    w.checkbox(surface, settings, 'separate_materials', 'Materials')
    w.checkbox(surface, settings, 'separate_smoothing', 'Smoothing Groups')
    update = w.group(layout, 'Update Options')
    w.radios(update, settings, 'update_mode', (('ALWAYS', 'Always'), ('RENDER', 'When Rendering')))


def draw_parameters(layout, context, mod=None, *, extensions=False, advanced=False):
    mod = mod or active_modifier(context)
    if mod is None:
        _unavailable(layout, 'Select a modifier')
        return False
    ob = mod.id_data
    _targets[ob.as_pointer()] = mod
    w.compact(layout)
    if mod.type == 'LATTICE':
        _draw_ffd(layout, ob, mod)
    elif mod.type == 'SUBSURF':
        _draw_ts(layout, ob, mod)
    elif gn_mods.identify(mod):
        kind = gn_mods.identify(mod)
        parameters = w.group(layout, 'Parameters')
        names = [item[0] for item in gn_mods.PARAMETERS[kind]]
        if kind == 'Melt':
            names = ['Amount', '% of Melt Spread']
        _named(parameters, mod, names)
        if kind == 'Melt':
            parameters.label(text='Solidity')
            w.radios(parameters, ob.max_modifier_parameters, 'melt_solidity', (('ICE', 'Ice'), ('GLASS', 'Glass')))
            w.radios(parameters, ob.max_modifier_parameters, 'melt_solidity', (('JELLY', 'Jelly'), ('PLASTIC', 'Plastic')))
            if ob.max_modifier_parameters.melt_solidity == 'CUSTOM':
                _named(parameters, mod, ['Solidity'])
            _named(parameters, mod, ['Flip Axis'])
        if kind == 'Melt' and extensions:
            _named(w.group(layout, 'Maxxed Extensions'), mod, ['Irregularity', 'Drip Size', 'Seed'])
    elif mod.type == 'SIMPLE_DEFORM' and mod.deform_method == 'BEND':
        params = w.group(layout, 'Parameters')
        w.spinner(params, mod, 'angle', 'Angle')
        _unavailable(params, 'Direction')
        params.label(text='Bend Axis')
        w.radios(params, mod, 'deform_axis', tuple((a, a) for a in 'XYZ'))
        _unavailable(params, 'Limits')
    elif mod.type == 'SOLIDIFY':
        params = w.group(layout, 'Parameters')
        for prop, label in (('shell_inner', 'Inner Amount'), ('shell_outer', 'Outer Amount')):
            w.spinner(params, ob.max_modifier_parameters, prop, label)
        _unavailable(params, 'Bevel Edges')
    elif mod.type == 'BEVEL':
        params = w.group(layout, 'Parameters')
        w.spinner(params, mod, 'width', 'Amount')
        w.spinner(params, mod, 'segments', 'Segments', step=1)
        _unavailable(params, 'Quad Chamfer')
    elif mod.type == 'ARRAY' and mod.use_constant_offset and not mod.use_relative_offset:
        params = w.group(layout, 'Parameters')
        w.spinner(params, mod, 'count', '1D Count', step=1)
        for index, axis in enumerate('XYZ'):
            w.spinner(params, mod, 'constant_offset_displace', axis, index=index)
        _unavailable(params, 'Rotation')
        _unavailable(params, 'Scale')
    elif mod.type == 'BOOLEAN':
        params = w.group(layout, 'Parameters')
        w.radios(params, mod, 'operation', (('UNION', 'Union'), ('INTERSECT', 'Intersection'), ('DIFFERENCE', 'Subtraction')))
        params.prop(mod, 'object', text='Operand')
    elif mod.type == 'UV_PROJECT':
        params = w.group(layout, 'Parameters')
        params.label(text='Mapping: Planar')
        if mod.projectors:
            params.prop(mod.projectors[0], 'object', text='Gizmo')
        params.prop_search(mod, 'uv_layer', ob.data, 'uv_layers', text='Map Channel')
        for label in ('Box', 'Cylindrical', 'Spherical'):
            _unavailable(params, label)
    else:
        _unavailable(layout, 'Parameters unavailable')
        return False
    if advanced and mod.type == 'SUBSURF':
        params = w.group(layout, 'Advanced')
        for prop, label in (('quality', 'Quality'), ('uv_smooth', 'UV Smooth'), ('boundary_smooth', 'Boundary')):
            params.prop(mod, prop, text=label)
    return True


def install(host):
    """Host supplies rollout(label, tabs, order, closed=False) and when(predicate)."""
    key = id(host)
    if key in _installations:
        return _installations[key][0]
    before = set(host.ROLLOUTS)

    def modifier_parameters(layout, context):
        draw_parameters(layout, context)
    draw = host.when(lambda c: active_modifier(c) is not None)(modifier_parameters)
    result = host.rollout('Parameters', {'MODIFY'}, 40)(draw)
    _installations[key] = result, [cls for cls in host.ROLLOUTS if cls not in before]
    return result


def uninstall(host):
    record = _installations.pop(id(host), None)
    if record:
        for cls in reversed(record[1]):
            if getattr(cls, 'is_registered', False):
                bpy.utils.unregister_class(cls)
            if cls in host.ROLLOUTS:
                host.ROLLOUTS.remove(cls)


def register_props():
    if not hasattr(bpy.types.Object, 'max_modifier_parameters'):
        bpy.types.Object.max_modifier_parameters = PointerProperty(type=MaxModifierParameters)


def unregister_props():
    _targets.clear()
    if hasattr(bpy.types.Object, 'max_modifier_parameters'):
        del bpy.types.Object.max_modifier_parameters
    w.set_spinner_policy(None)


def _bound(ob):
    target = _targets.get(ob.as_pointer())
    try:
        return target if target and target.id_data == ob and ob.modifiers.get(target.name) == target else None
    except ReferenceError:
        _targets.pop(ob.as_pointer(), None)
        return None


classes = (MaxModifierParameters, MAX_OT_modifier_list, MAX_OT_modifier_pick)
