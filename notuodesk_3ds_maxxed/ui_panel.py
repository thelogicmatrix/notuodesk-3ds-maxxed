"""Maxxed Command Panel assembled from the independent feature adapters."""
import bpy
from bpy.props import IntProperty, StringProperty
from . import (command_panel_ui as host, create, editable_poly_ui, keyboard_entry,
               line_tool, loft, max_icons, max_widgets as w, modifier_ui, operators,
               plane_plus, prims, symmetry, vray)

TABS = [('CREATE', 'Create', 'ADD'), ('MODIFY', 'Modify', 'MODIFIER'),
        ('HIERARCHY', 'Hierarchy', 'OUTLINER'), ('MOTION', 'Motion', 'ANIM'),
        ('DISPLAY', 'Display', 'RESTRICT_VIEW_OFF'), ('UTILITIES', 'Utilities', 'TOOL_SETTINGS')]
CREATE_CATS = [('GEOMETRY', 'Geometry', 'MESH_CUBE'), ('SHAPES', 'Shapes', 'CURVE_DATA'),
               ('LIGHTS', 'Lights', 'LIGHT'), ('CAMERAS', 'Cameras', 'CAMERA_DATA'),
               ('HELPERS', 'Helpers', 'EMPTY_DATA'), ('SPACE_WARPS', 'Space Warps', 'FORCE_FORCE'),
               ('SYSTEMS', 'Systems', 'CONSTRAINT')]
# RNA enum tuples keep stable integer identities as well as the saved strings.
TABS = [(key, label, label, fallback, index) for index, (key, label, fallback) in enumerate(TABS)]
CREATE_CATS = [(key, label, label, fallback, index) for index, (key, label, fallback) in enumerate(CREATE_CATS)]
SUBTYPES = {
    'GEOMETRY': [('STANDARD', 'Standard Primitives'), ('EXTENDED', 'Extended Primitives'),
                 ('COMPOUND', 'Compound Objects'), ('VRAY', 'V-Ray'), ('JOKERMARTINI', 'JokerMartini')],
    'SHAPES': [('STANDARD', 'Splines')], 'LIGHTS': [('STANDARD', 'Standard'), ('VRAY', 'V-Ray')],
    'CAMERAS': [('STANDARD', 'Standard'), ('VRAY', 'V-Ray')],
    'HELPERS': [('STANDARD', 'Standard')], 'SPACE_WARPS': [('STANDARD', 'Space Warps')],
    'SYSTEMS': [('STANDARD', 'Systems')],
}
SUBLEVEL_ICONS = {1: 'VERTEXSEL', 2: 'EDGESEL', 3: 'EDGESEL', 4: 'FACESEL', 5: 'FACESEL'}
SUBLEVEL_NAMES = dict(enumerate(('vertex', 'edge', 'border', 'polygon', 'element'), 1))
EP_LABELS = {key: label for key, label, _ in operators.EDIT_POLY_OPS}
ROLLOUTS = []
BASE_NAMES = {'MESH': 'Editable Poly', 'CURVE': 'Editable Spline', 'FONT': 'Text',
              'SURFACE': 'NURBS Surface', 'LIGHT': 'Light', 'CAMERA': 'Camera',
              'EMPTY': 'Dummy', 'ARMATURE': 'Bones', 'META': 'Blob Mesh',
              'LATTICE': 'FFD', 'GREASEPENCIL': 'Grease Pencil', 'CURVES': 'Hair',
              'POINTCLOUD': 'Point Cloud', 'VOLUME': 'Volume'}
SKIP_PROPS = set()
MELT_PRESETS = [('Ice', 2.), ('Glass', .5), ('Jelly', .4), ('Plastic', .1)]


def base_name(ob):
    kind = ob.max_prim.kind if ob and ob.type == 'MESH' else ''
    return prims.PRIMITIVES[kind][0] if kind in prims.PRIMITIVES else BASE_NAMES.get(ob.type, ob.type.title()) if ob else ''


def tab(context):
    return context.window_manager.max_cmd_tab


def subtype_label(context):
    wm = context.window_manager
    return dict(SUBTYPES.get(wm.max_create_cat, ())).get(wm.max_create_sub, 'Standard')


def draw_prim_params(layout, ob):
    return plane_plus.draw(layout, ob) if ob.max_prim.kind == 'PLANEPLUS' else prims.draw(layout, ob)


def draw_modifier_params(layout, mod):
    if symmetry.is_symmetry(mod):
        return symmetry.draw(layout, mod.id_data, mod)
    return modifier_ui.draw_parameters(layout, bpy.context, mod)


def draw_base_params(layout, ob):
    with bpy.context.temp_override(object=ob, active_object=ob):
        return parameters(layout, bpy.context)


def _stack_get(ob):
    mod = host.active(ob)
    return list(ob.modifiers).index(mod) if mod else -1


def _stack_set(ob, value):
    mod = ob.modifiers[value] if 0 <= value < len(ob.modifiers) else None
    if mod and host.internal(mod):
        return
    if value == -1 or mod:
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.max.modifier_set_active(name=mod.name if mod else '')


def when(pred):
    def decorate(callback):
        callback.max_visible = pred
        return callback
    return decorate


class MAX_OT_rollout_toggle(bpy.types.Operator):
    bl_idname = 'max.rollout_toggle'
    bl_label = 'Expand or Collapse Rollout'
    bl_options = {'INTERNAL'}
    identifier: StringProperty()
    default_closed: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        key = '_max_rollout_' + self.identifier
        context.workspace[key] = not context.workspace.get(key, self.default_closed)
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}


def rollout(label, tabs, order, closed=False):
    def decorate(callback):
        identifier = 'MAX_PT_' + callback.__name__
        if any(cls.__name__ == identifier for cls in ROLLOUTS):
            return callback
        predicate = getattr(callback, 'max_visible', lambda context: True)
        def poll(cls, context):
            if context.window_manager.max_cmd_tab not in tabs:
                return False
            ob = host.object_for(context)
            if ob == context.object:
                return bool(predicate(context))
            with context.temp_override(object=ob, active_object=ob):
                return bool(predicate(context))
        def draw(self, context):
            w.compact(self.layout)
            collapsed = context.workspace.get('_max_rollout_' + identifier, closed)
            header = self.layout.row(align=True)
            header.scale_y = .85
            split = header.split(factor=.08, align=True)
            for cell, caption in ((split.row(align=True), '+' if collapsed else '-'),
                                  (split.row(align=True), label)):
                op = cell.operator('max.rollout_toggle', text=caption)
                op.identifier, op.default_closed = identifier, closed
            if collapsed:
                return
            body = self.layout.column(align=True)
            ob = host.object_for(context)
            if ob:
                body.context_pointer_set('object', ob)
                body.context_pointer_set('active_object', ob)
            with context.temp_override(object=ob, active_object=ob):
                callback(body, context)
        cls = type(identifier, (bpy.types.Panel,), {
            '__module__': __name__, 'bl_idname': identifier, 'bl_label': label,
            'bl_space_type': 'VIEW_3D', 'bl_region_type': 'UI', 'bl_category': 'Command Panel',
            'bl_parent_id': 'MAX_PT_command_panel', 'bl_order': order,
            'max_default_closed': closed,
            'bl_options': {'HIDE_HEADER'},
            'poll': classmethod(poll), 'draw': draw,
        })
        ROLLOUTS.append(cls)
        return callback
    return decorate


def is_poly(context):
    ob = host.object_for(context)
    return bool(ob and ob.type == 'MESH' and not ob.max_prim.kind and
                (_stack_get(ob) == -1 or ob.mode == 'EDIT') and not symmetry.editing(context))


_is_poly = is_poly


class MAX_UL_stack(bpy.types.UIList):
    """Compatibility list route. The ordinary host draws a unified tree."""
    def filter_items(self, context, data, propname):
        mods = getattr(data, propname)
        return [0 if host.internal(m) else self.bitflag_filter_item for m in mods], list(reversed(range(len(mods))))

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if not host.internal(item):
            layout.operator('max.modifier_set_active', text=item.name, emboss=False).name = item.name


class MAX_MT_create_subcat(bpy.types.Menu):
    bl_label = 'Category'
    def draw(self, context):
        wm = context.window_manager
        for token, label in SUBTYPES.get(wm.max_create_cat, ()):
            op = self.layout.operator('wm.context_set_enum', text=label)
            op.data_path, op.value = 'window_manager.max_create_sub', token


class MAX_PT_command_panel(bpy.types.Panel):
    bl_label = 'Command Panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Command Panel'
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def register(cls):
        host.install()

    @classmethod
    def unregister(cls):
        host.uninstall()

    def draw(self, context):
        layout = w.compact(self.layout)
        layout.operator_context = 'INVOKE_DEFAULT'
        wm = context.window_manager
        host.tabs(layout, context, TABS)
        ob = host.object_for(context)
        if ob:
            layout.context_pointer_set('object', ob)
            layout.context_pointer_set('active_object', ob)
        if wm.max_cmd_tab == 'CREATE':
            row = layout.row(align=True)
            for key, label, description, fallback, index in CREATE_CATS:
                row.prop_enum(wm, 'max_create_cat', key, text='')
            label = dict(SUBTYPES.get(wm.max_create_cat, ())).get(wm.max_create_sub,
                next(iter(SUBTYPES.get(wm.max_create_cat, (('', ''),))))[1])
            layout.menu('MAX_MT_create_subcat', text=label)
        elif wm.max_cmd_tab == 'MODIFY':
            host.name_color(layout, ob)
            row = layout.row(align=True)
            row.enabled = bool(ob and ob.type in {'MESH', 'CURVE', 'FONT'})
            row.operator_context = 'INVOKE_DEFAULT'
            row.operator('max.modifier_search', text='Modifier List', icon='DOWNARROW_HLT')
            if ob:
                host.draw_stack(layout, context, ob)
        elif wm.max_cmd_tab == 'HIERARCHY':
            layout.prop(wm, 'max_hierarchy_tab', expand=True)


@rollout('Object Type', {'CREATE'}, 1)
def create_object_type(layout, context):
    wm = context.window_manager
    if wm.max_create_sub == 'JOKERMARTINI' and wm.max_create_cat == 'GEOMETRY':
        layout.operator('max.plane_plus', text='PlanePlus')
    elif wm.max_create_sub == 'COMPOUND' and wm.max_create_cat == 'GEOMETRY':
        layout.operator('max.loft_start', text='Loft')
    elif wm.max_create_sub == 'VRAY' and wm.max_create_cat in {'GEOMETRY', 'LIGHTS', 'CAMERAS'}:
        route = {'GEOMETRY': 'max.vray_plane', 'CAMERAS': 'max.vray_camera', 'LIGHTS': 'max.vray_light'}[wm.max_create_cat]
        if wm.max_create_cat == 'LIGHTS':
            for kind, label in (('PLANE', 'VRayLight'), ('DOME', 'VRayDomeLight'), ('IES', 'VRayIES')):
                layout.operator(route, text=label).kind = kind
        else:
            layout.operator(route, text='VRayPlane' if wm.max_create_cat == 'GEOMETRY' else 'VRayPhysicalCamera')
    else:
        create.draw_object_types(layout, context)


@rollout('Name and Color', {'CREATE'}, 2)
@when(lambda c: c.object is not None)
def create_name_color(layout, context):
    host.name_color(layout, context.object)


@rollout('Creation Method', {'CREATE'}, 3)
@when(keyboard_entry.visible)
def creation_method(layout, context):
    keyboard_entry.draw_method(layout, context)


@rollout('Keyboard Entry', {'CREATE'}, 4, closed=True)
@when(keyboard_entry.visible)
def keyboard_entry_rollout(layout, context):
    keyboard_entry.draw_keyboard(layout, context)


def parameter_visible(context):
    ob = context.object
    if not ob or loft.params_visible(context):
        return False
    return bool(host.active(ob) or (ob.type == 'MESH' and ob.max_prim.kind) or ob.type in {'LIGHT', 'CAMERA', 'FONT'})


@rollout('Parameters', {'CREATE', 'MODIFY'}, 5)
@when(parameter_visible)
def parameters(layout, context):
    ob = context.object
    mod = host.active(ob) if context.window_manager.max_cmd_tab == 'MODIFY' else None
    if mod:
        if symmetry.is_symmetry(mod):
            symmetry.draw(layout, ob, mod)
        else:
            modifier_ui.draw_parameters(layout, context, mod)
    elif ob.type == 'MESH' and ob.max_prim.kind:
        if ob.max_prim.kind == 'PLANEPLUS':
            plane_plus.draw(layout, ob)
        else:
            prims.draw(layout, ob)
    elif ob.type == 'CAMERA':
        vray.draw_camera(layout, context)
    elif ob.type == 'LIGHT':
        w.spinner(layout, ob.data, 'energy', 'Multiplier')
        layout.prop(ob.data, 'color', text='Color')
    elif ob.type == 'FONT':
        layout.prop(ob.data, 'body', text='Text')
        w.spinner(layout, ob.data, 'size', 'Size')


for callback, label, order, predicate, closed in (
    (line_tool.draw_rendering, 'Rendering', 3, line_tool.spline_poll, True),
    (line_tool.draw_interpolation, 'Interpolation', 4, line_tool.spline_poll, True),
    (line_tool.draw_method, 'Creation Method', 5, line_tool.line_poll, False),
    (line_tool.draw_keyboard, 'Keyboard Entry', 6, line_tool.line_poll, True),
):
    rollout(label, {'CREATE', 'MODIFY'} if 'render' in callback.__name__ or 'interpolation' in callback.__name__ else {'CREATE'},
            order, closed)(when(predicate)(callback))

for name, label, callback, predicate, order in (
    ('loft_creation', 'Creation Method', loft.draw_creation, loft.creation_visible, 3),
    ('loft_skin', 'Skin Parameters', loft.draw_skin, loft.params_visible, 4),
    ('loft_surface', 'Surface Parameters', loft.draw_surface, loft.params_visible, 5),
    ('loft_path', 'Path Parameters', loft.draw_path, loft.params_visible, 6),
    ('loft_deformations', 'Deformations', loft.draw_deformations, loft.params_visible, 7),
):
    def draw(layout, context, callback=callback):
        callback(layout, context)
    draw.__name__ = name
    rollout(label, {'CREATE', 'MODIFY'}, order, name != 'loft_creation')(when(predicate)(draw))
    globals()[name] = draw


@rollout('Material', {'CREATE', 'MODIFY'}, 11, closed=True)
@when(lambda c: c.object is not None and c.object.active_material is not None)
def material_rollout(layout, context):
    layout.prop(context.object.active_material, 'name', text='')
    layout.operator('max.open_editor', text='Material Editor').editor = 'MATERIAL'


@rollout('Selection', {'MODIFY'}, 4)
@when(is_poly)
def poly_selection(layout, context):
    editable_poly_ui.selection(layout, context)


@rollout('Edit Geometry', {'MODIFY'}, 7)
@when(is_poly)
def poly_edit_geometry(layout, context):
    editable_poly_ui.geometry(layout, context)


editable_poly_ui.install(rollout, when, is_poly)


def pivot_tab(context):
    return context.window_manager.max_hierarchy_tab == 'PIVOT'


@rollout('Adjust Pivot', {'HIERARCHY'}, 1)
@when(pivot_tab)
def hier_pivot(layout, context):
    row = layout.row(align=True)
    row.enabled = context.object is not None
    if context.object:
        host.unavailable(row, 'Affect Pivot Only')
    for text, token in (('Center to Object', 'CENTER_PIVOT'), ('Center Object to Pivot', 'OBJECT_TO_PIVOT')):
        layout.operator('max.object_cmd', text=text).cmd = token
    layout.operator('max.workspace_align_world', text='Align to World')
    host.unavailable(layout, 'Align to Object')
    host.unavailable(layout, 'Reset Pivot')
    row = layout.row(align=True)
    row.operator('max.pivot_bounds', text='Pivot to Bottom').mode = 'BOTTOM'
    row.operator('max.pivot_bounds', text='Pivot to Center').mode = 'CENTER'


@rollout('Adjust Transform', {'HIERARCHY'}, 2, closed=True)
@when(pivot_tab)
def hier_transform(layout, context):
    layout.operator('max.object_cmd', text='Reset XForm').cmd = 'RESET_XFORM'
    host.unavailable(layout, 'Working Pivot')


@rollout('Link Info', {'HIERARCHY'}, 3)
@when(lambda c: c.window_manager.max_hierarchy_tab == 'LINK')
def hier_link(layout, context):
    ob = context.object
    if not ob:
        return
    layout.label(text='Locks')
    for prop, label in (('lock_location', 'Move'), ('lock_rotation', 'Rotate'), ('lock_scale', 'Scale')):
        row = layout.row(align=True)
        row.label(text=label)
        for index, axis in enumerate('XYZ'):
            row.prop(ob, prop, index=index, text=axis, toggle=False,
                     icon='CHECKBOX_HLT' if getattr(ob, prop)[index] else 'CHECKBOX_DEHLT', emboss=False)
    layout.label(text='Inherit')
    host.unavailable(layout, 'Position / Rotation / Scale')
    layout.operator('max.object_cmd', text='Unlink Selection').cmd = 'UNLINK'


@rollout('IK', {'HIERARCHY'}, 1)
@when(lambda c: c.window_manager.max_hierarchy_tab == 'IK')
def hier_ik(layout, context):
    for text in ('IK Chain', 'IK Solver', 'Pick IK Solver', 'Assign Controller'):
        host.unavailable(layout, text)


@rollout('Parameters', {'MOTION'}, 1)
def motion_anim(layout, context):
    ob = context.object
    if not ob:
        return
    host.unavailable(layout, 'Assign Controller')
    layout.label(text='PRS Parameters')
    for prop, label in (('location', 'Position'), ('rotation_euler', 'Rotation'), ('scale', 'Scale')):
        layout.label(text=label)
        for index, axis in enumerate('XYZ'):
            w.spinner(layout, ob, prop, axis, index=index)


@rollout('Key Info', {'MOTION'}, 2, closed=True)
def motion_editors(layout, context):
    layout.operator('max.set_key', text='Set Key')
    layout.operator('max.open_editor', text='Track View - Curve Editor').editor = 'CURVE_EDITOR'
    layout.operator('max.open_editor', text='Track View - Dope Sheet').editor = 'DOPE_SHEET'


@rollout('Trajectories', {'MOTION'}, 3, closed=True)
def motion_traj(layout, context):
    host.unavailable(layout, 'Trajectories')


@rollout('Hide', {'DISPLAY'}, 1)
def disp_hide(layout, context):
    for text, token in (('Hide Selected', 'HIDE_SEL'), ('Hide Unselected', 'HIDE_UNSEL'), ('Unhide All', 'UNHIDE')):
        layout.operator('max.object_cmd', text=text).cmd = token
    layout.operator('max.scene_selection_dialog', text='Hide By Name...').hide = True


@rollout('Hide By Category', {'DISPLAY'}, 0)
def disp_categories(layout, context):
    # Category toggles use the viewport's native visibility filters.
    space = context.space_data
    for prop, text in (('show_object_viewport_mesh', 'Geometry'),
                       ('show_object_viewport_curve', 'Shapes'),
                       ('show_object_viewport_light', 'Lights'),
                       ('show_object_viewport_camera', 'Cameras'),
                       ('show_object_viewport_empty', 'Helpers')):
        row = layout.row(align=True)
        if hasattr(space, prop):
            row.prop(space, prop, text=text, invert_checkbox=True)
        else:
            host.unavailable(row, text)
    for text in ('Space Warps', 'Systems'):
        host.unavailable(layout, text)


@rollout('Freeze', {'DISPLAY'}, 2)
def disp_freeze(layout, context):
    layout.operator('max.object_cmd', text='Freeze Selection').cmd = 'FREEZE'
    host.unavailable(layout, 'Freeze Unselected')
    layout.operator('max.object_cmd', text='Unfreeze All').cmd = 'UNFREEZE'
    layout.operator('max.unfreeze_by_name', text='Unfreeze by Name...')
    layout.operator('max.unfreeze_by_hit', text='Unfreeze by Hit')


@rollout('Freeze By Category', {'DISPLAY'}, 2, closed=True)
def disp_freeze_categories(layout, context):
    host.unavailable(layout, 'Freeze By Category')


@rollout('Display Properties', {'DISPLAY'}, 3)
def disp_props(layout, context):
    ob = context.object
    if ob:
        w.checkbox(layout, ob, 'max_show_frozen_gray', 'Show Frozen in Gray')
        for text, token in (('Display as Box', 'DISPLAY_BOX'), ('See-Through', 'SEE_THROUGH'),
                            ('Show Wireframe', 'EDGES_ONLY')):
            layout.operator('max.object_cmd', text=text).cmd = token
        w.checkbox(layout, ob, 'show_name', 'Object Name')
    host.unavailable(layout, 'Viewport Configuration')


@rollout('Link Display', {'DISPLAY'}, 4, closed=True)
def disp_links(layout, context):
    host.unavailable(layout, 'Display Links')


@rollout('Headlight', {'DISPLAY'}, 5, closed=True)
def disp_headlight(layout, context):
    host.unavailable(layout, 'Headlight')


@rollout('Utilities', {'UTILITIES'}, 1)
def util_main(layout, context):
    for text, token in (('Reset XForm', 'RESET_XFORM'), ('Collapse', 'CONVERT_POLY')):
        layout.operator('max.object_cmd', text=text).cmd = token
    layout.menu('MAX_MT_xview', text='xView')
    host.unavailable(layout, 'Viewport Configuration')
    layout.operator('max.open_editor', text='Scene Explorer').editor = 'SCENE_EXPLORER'
    for text in ('Measure', 'Channel Info', 'Rescale World Units', 'More...'):
        host.unavailable(layout, text)


@rollout('RappaTools3', {'UTILITIES'}, 2, closed=True)
def util_maxxed(layout, context):
    layout.label(text='Selection')
    editable_poly_ui.grid(layout, ('LOOP', 'RING', 'SHRINK', 'GROW'))
    layout.label(text='Modeling')
    editable_poly_ui.grid(layout, ('CHAMFER', 'CONNECT', 'BRIDGE', 'WELD'))


def register_props():
    bpy.types.Object.max_stack_index = IntProperty(get=_stack_get, set=_stack_set, options={'SKIP_SAVE'})
    modifier_ui.register_props()
    host.install()


def unregister_props():
    host.uninstall()
    modifier_ui.unregister_props()
    if hasattr(bpy.types.Object, 'max_stack_index'):
        del bpy.types.Object.max_stack_index


classes = (*modifier_ui.classes, *host.classes, MAX_OT_rollout_toggle, MAX_UL_stack, MAX_MT_create_subcat, MAX_PT_command_panel)
