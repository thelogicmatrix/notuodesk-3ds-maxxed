"""Confirmed quad catalogues and context queries. No input handlers live here."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Command:
    operator: str
    values: tuple = ()


@dataclass(frozen=True)
class Entry:
    key: str
    label: str
    command: Command = None
    settings: Command = None
    children: tuple = ()
    enabled: bool = True
    checked: bool = False
    reason: str = ''
    settings_enabled: bool = True


@dataclass(frozen=True)
class Quadrant:
    title: str
    entries: tuple
    padding: tuple = (0, 0)
    width: int = 179


@dataclass(frozen=True)
class QuadContext:
    object_class: str = ''
    level: int = 0
    selected: bool = False
    objects_selected: bool = False
    modifier: str = ''
    symmetry: bool = False
    mirror_edit: bool = False
    panel: str = ''
    tool: str = ''
    nurms: bool = False
    ignore_backfacing: bool = False
    isolated: bool = False
    object_count: int = 0
    reference: str = 'WORLD'


SEPARATOR = Entry('', '')
LEVELS = ('Top-level', 'Vertex', 'Edge', 'Border', 'Polygon', 'Element')
SET_NAMES = ('DEFAULT', 'MODELING', 'NATHAN', 'ANIMATION', 'LIGHTING', 'UNASSIGNED')


def command(identifier, **values):
    return Command(identifier, tuple(values.items()))


def unavailable(label, reason='This action is not supplied', settings=None):
    return Entry(label, label, settings=settings, enabled=False, reason=reason)


def action(label, identifier, *, key=None, enabled=True, settings=None, checked=False, **values):
    return Entry(key or label, label, command(identifier, **values), settings,
                 enabled=enabled, checked=checked)


def poly(label, token, ctx, *, settings=False, levels=(1, 2, 3, 4, 5)):
    enabled = ctx.object_class == 'MESH' and not ctx.modifier and not ctx.symmetry and ctx.level in levels and ctx.selected
    row = action(label, 'max.edit_poly', key=token, op=token, enabled=enabled,
                 settings=command('max.poly_settings', action=token) if settings else None)
    reason = 'Select components for this command' if not ctx.selected else 'Unavailable at the current sub-object level'
    return replace(row, reason='' if enabled else reason)


def capture(context):
    from . import operators, mode_feedback, symmetry, max_rotate, modifier_ui
    import bmesh
    obj = symmetry.owner(context)
    helper = symmetry.editing(context)
    if obj:
        with context.temp_override(object=obj, active_object=obj):
            mod = modifier_ui.active_modifier(context)
    else:
        mod = None
    if helper and obj:
        mod = next((candidate for candidate in obj.modifiers if symmetry.is_symmetry(candidate)
                    and symmetry.settings(candidate).mirror_object == context.active_object), mod)
    is_symmetry = symmetry.is_symmetry(mod) or helper
    lev = operators.current_level(context) if obj else 0
    selected = bool(context.selected_objects)
    if context.mode == 'EDIT_MESH' and context.active_object:
        lev = operators.current_level(context)
        domain = 'verts' if lev == 1 else 'edges' if lev in (2, 3) else 'faces'
        selected = any(any(item.select and not item.hide for item in getattr(bmesh.from_edit_mesh(ob.data), domain))
                       for ob in context.objects_in_mode_unique_data if ob.type == 'MESH')
    return QuadContext(obj.type if obj else '', lev, selected, bool(context.selected_objects),
                       mod.name if mod else '', is_symmetry, helper,
                       getattr(context.window_manager, 'max_cmd_tab', ''), mode_feedback.active_tool(context),
                       bool(obj and obj.type == 'MESH' and obj.max_poly.nurms),
                       bool(obj and obj.type == 'MESH' and obj.max_poly.ignore_backfacing),
                       bool(context.space_data and context.space_data.type == 'VIEW_3D' and context.space_data.local_view),
                       len(context.selected_objects),
                       max_rotate.reference_name(context, mode_feedback.active_tool(context)
                                                 if mode_feedback.active_tool(context) in {'MOVE','ROTATE','SCALE'} else 'MOVE'))


def choose_set(*, ctrl=False, alt=False, shift=False):
    if shift and not ctrl and not alt:
        return 'SNAP'
    if shift:
        return 'UNASSIGNED'
    return 'LIGHTING' if ctrl and alt else 'MODELING' if ctrl else 'ANIMATION' if alt else 'DEFAULT'


def _object(label, token, ctx, global_action=False):
    return action(label, 'max.object_cmd', cmd=token, enabled=global_action or ctx.objects_selected)


def _sublevels(ctx):
    return tuple(action(LEVELS[n], 'max.subobject', key='level'+str(n), level=n,
                        enabled=ctx.object_class == 'MESH', checked=ctx.level == n)
                 for n in (5, 4, 3, 2, 1, 0))


def _convert(ctx):
    return (unavailable('Editable Mesh'),
            action('Editable Spline', 'max.object_cmd', cmd='CONVERT_SPLINE', enabled=ctx.objects_selected),
            unavailable('Editable Patch'),
            action('Editable Poly', 'max.object_cmd', cmd='CONVERT_POLY', enabled=ctx.objects_selected),
            unavailable('NURBS Surface'))


def _display(ctx):
    return (
        Entry('lighting', 'Viewport Lighting and Shadows', children=tuple(unavailable(t) for t in
              ('Unlock Selected Lights', 'Lock Selected Lights', 'Auto Display Selected Lights'))),
        SEPARATOR,
        replace(_object('Isolate Selection', 'ISOLATE', ctx), enabled=ctx.objects_selected and not ctx.isolated),
        replace(_object('End Isolate', 'ISOLATE', ctx, True), enabled=ctx.isolated), SEPARATOR,
        _object('Unfreeze All', 'UNFREEZE', ctx, True), _object('Freeze Selection', 'FREEZE', ctx), SEPARATOR,
        action('Unhide by Name', 'max.scene_selection_dialog', hide=False),
        _object('Unhide All', 'UNHIDE', ctx, True), _object('Hide Unselected', 'HIDE_UNSEL', ctx),
        _object('Hide Selection', 'HIDE_SEL', ctx), SEPARATOR,
        Entry('states', 'State Sets', children=tuple(unavailable(t) for t in
              ('Objects', 'States', 'Record Active State Set', 'Create New State Set'))),
        unavailable('Manage State Sets...'), SEPARATOR, unavailable('Show Motion Paths'))


def _transform(ctx):
    rows = [action(label, 'max.select_transform', key=kind, kind=kind,
                   settings=command('max.quad_typein', kind=kind))
            for kind, label in (('MOVE', 'Move'), ('ROTATE', 'Rotate'), ('SCALE', 'Scale'))]
    rows += [unavailable('Placement'), action('Select', 'wm.tool_set_by_id', name='builtin.select_box'),
             unavailable('Select Similar'), SEPARATOR, unavailable('Place Pivot Surface'), SEPARATOR,
             action('Clone', 'max.clone', enabled=ctx.objects_selected), SEPARATOR,
             action('Object Properties...', 'max.object_properties', enabled=ctx.objects_selected), SEPARATOR,
             action('Curve Editor...', 'max.open_editor', editor='CURVE_EDITOR'),
             action('Dope Sheet...', 'max.open_editor', editor='DOPE_SHEET'),
             unavailable('Wire Parameters...'), SEPARATOR,
             Entry('convert', 'Convert To:', children=_convert(ctx))]
    return tuple(rows)


# Autodesk documents these level-specific operations. It does not prove a full
# ordering for each level. Keep the documented order rather than invent entries.
POLY_ROWS = {
    1: (('Remove', 'REMOVE'), ('Break', 'BREAK'), ('Extrude', 'EXTRUDE'), ('Weld', 'WELD'),
        ('Chamfer', 'CHAMFER'), ('Target Weld', 'TARGET_WELD'), ('Connect', 'CONNECT'),
        ('Remove Isolated Vertices', 'DELETE_ISOLATED'), ('Remove Unused Map Verts', None)),
    2: (('Insert Vertex', 'INSERT_VERTEX'), ('Remove', 'REMOVE'), ('Split', 'SPLIT'),
        ('Extrude', 'EXTRUDE'), ('Weld', 'WELD'), ('Chamfer', 'CHAMFER'), ('Target Weld', 'TARGET_WELD'),
        ('Bridge', 'BRIDGE'), ('Connect', 'CONNECT'), ('Create Shape', 'CREATE_SHAPE'),
        ('Edit Triangulation', None), ('Turn', 'TURN')),
    3: (('Extrude', 'EXTRUDE'), ('Insert Vertex', 'INSERT_VERTEX'), ('Chamfer', 'CHAMFER'),
        ('Cap', 'CAP'), ('Bridge', 'BRIDGE'), ('Connect', 'CONNECT'), ('Create Shape', 'CREATE_SHAPE'),
        ('Edit Triangulation', None), ('Turn', 'TURN')),
    4: (('Insert Vertex', 'INSERT_VERTEX'), ('Extrude', 'EXTRUDE'), ('Outline', 'OUTLINE'),
        ('Bevel', 'BEVEL'), ('Inset', 'INSET'), ('Bridge', 'BRIDGE'), ('Flip Normals', 'FLIP'),
        ('Hinge From Edge', None), ('Extrude Along Spline', None), ('Edit Triangulation', None),
        ('Retriangulate', 'RETRIANGULATE'), ('Turn', 'TURN')),
}
POLY_ROWS[5] = POLY_ROWS[4]
SETTING_TOKENS = frozenset(('EXTRUDE', 'WELD', 'CHAMFER', 'BRIDGE', 'CONNECT', 'CREATE_SHAPE',
                            'OUTLINE', 'BEVEL', 'INSET', 'RELAX'))


def _tools(ctx):
    if not ctx.objects_selected:
        return (), ()
    if ctx.object_class == 'LIGHT':
        rows = tuple(unavailable(label) for label in ('Ambient Only', 'Affect Specular', 'Affect Diffuse',
                                                      'Cast Shadows', 'Light On'))
        return (rows, ()) if ctx.object_count == 1 else ((), ())
    if ctx.symmetry:
        return ((action('Mirror', 'max.symmetry_action', action='MIRROR', name=ctx.modifier,
                        checked=ctx.mirror_edit),), ())
    if ctx.modifier:
        return (), ()
    if ctx.object_class != 'MESH':
        return (), ()
    upper = (action('NURMS Toggle', 'max.quad_toggle', flag='nurms', enabled=ctx.objects_selected,
                    checked=ctx.nurms),
             action('Ignore Backfacing', 'max.quad_toggle', flag='ignore_backfacing', enabled=ctx.objects_selected,
                    checked=ctx.ignore_backfacing),
             SEPARATOR, poly('Hide Unselected', 'HIDE_UNSEL', ctx),
             poly('Collapse', 'COLLAPSE', ctx),
             replace(poly('Attach', 'ATTACH', ctx, levels=(0, 1, 2, 3, 4, 5)),
                     settings=command('max.poly_attach_list')), SEPARATOR,
             poly('Cut', 'CUT', ctx, levels=(0, 1, 2, 3, 4, 5)),
             poly('Quickslice', 'QUICK_SLICE', ctx, levels=(0, 1, 2, 3, 4, 5)), SEPARATOR,
             unavailable('Repeat'), SEPARATOR, unavailable('Convert to Edge'), unavailable('Convert to Vertex'),
             SEPARATOR) + _sublevels(ctx)
    lower = tuple(poly(label, token, ctx, settings=token in SETTING_TOKENS) if token
                  else unavailable(label) for label, token in POLY_ROWS.get(ctx.level, ()))
    if ctx.level == 4:
        # The photographed Polygon quadrant overrides the text-only list.
        lower = (poly('Create', 'CREATE', ctx), SEPARATOR, poly('Insert Vertex', 'INSERT_VERTEX', ctx), SEPARATOR,
                 poly('Extrude', 'EXTRUDE', ctx, settings=True), poly('Bevel', 'BEVEL', ctx, settings=True),
                 poly('Outline', 'OUTLINE', ctx, settings=True), poly('Inset', 'INSET', ctx, settings=True), SEPARATOR,
                 unavailable('Hinge from Edge', settings=command('max.poly_settings', action='HINGE')),
                 unavailable('Extrude along Spline', settings=command('max.poly_settings', action='SPLINE_EXTRUDE')), SEPARATOR,
                 unavailable('Edit Triangulation'), poly('Flip Normals', 'FLIP', ctx))
    return upper, lower


# Nathan's confirmed quad captions and separators. None of the held RappaTools
# expansion is included. Unavailable plug-in operations remain visible and inert.
NATHAN_LABELS = (
    ('Selection', ('Loop', 'Ring', '', 'Shrink Selection', 'Grow Selection', '', 'Grow Loop', 'Grow Ring', '',
                   'Shrink Loop', 'Shrink Ring', '', 'Saved Selection', '', 'Similar', 'Adjacent', '',
                   'Fill', 'Select Half', '', 'Remove Loop', 'Remove Ring')),
    ('Misc', ('Make Poly', 'XForm', '', 'World', 'Center Pivot', 'One Node', '', 'Union', 'Replace', '',
              'Mirror X', 'Mirror Y', 'Mirror Z', '', 'Black Material', '', 'Make MultiMat', 'GetPutMaterial')),
    ('Modeling', ('Ring Connect', 'Flow Connect', '', 'Slide', 'Push', '', 'Bridge', 'Smart Quads', '',
                  'Relax', 'Geo Poly', 'Loop Tools', '', 'Spin Edge', 'Dissolve', '', 'Move 2 Grid',
                  'Move To Point', '', 'Align Tools', 'Verts Tools')),
    ('RappaTools3', ('RappaTools3', '', 'Working Pivot', '', 'ChamferOp', 'Save Scene', '', 'Auto SGs',
                    'Clear All SGs', '', 'Multi Hide', '', 'Active Grid UI', 'Quick Topo UI', 'Random Fly', '',
                    'Isolation Mode', 'Expert Mode')),
)


def _animation(ctx):
    coordinates = tuple(action(label, 'max.quad_reference', reference=token)
                        for token, label in (('WORLD','World'),('WORKING','Working'),('VIEW','View'),
                                             ('SCREEN','Screen'),('PARENT','Parent'),
                                             ('LOCAL_ALIGNED','Local Aligned'),('LOCAL','Local')))
    transform = (unavailable('Freeze Transform'), unavailable('Freeze Rotation'), SEPARATOR,
                 unavailable('Transform To Zero'), unavailable('Rotation To Zero'))
    pose = (unavailable('Set Pref Angles'), unavailable('Assume Pref Angles'), SEPARATOR,
            unavailable('Set as Skin Pose'), unavailable('Assume Skin Pose'))
    keyset = (action('Set Keyframe', 'max.set_key', enabled=ctx.objects_selected), SEPARATOR,
              unavailable('Show Trajectories Toggle'), SEPARATOR, unavailable('Delete Selected Animation'), SEPARATOR,
              unavailable('Reaction Manager...'), action('Dope Sheet...', 'max.open_editor', editor='DOPE_SHEET'),
              action('Curve Editor...', 'max.open_editor', editor='CURVE_EDITOR'))
    return (Quadrant('transform', transform, (1, 0), 155), Quadrant('coordinates', coordinates, (3, 0), 155),
            Quadrant('pose', pose, (0, 1), 155), Quadrant('set', keyset, (0, 1), 155))


def _nathan(ctx):
    supported = {
        'Loop': poly('Loop', 'LOOP', ctx, levels=(2, 3)),
        'Ring': poly('Ring', 'RING', ctx, levels=(2, 3)),
        'Shrink Selection': poly('Shrink Selection', 'SHRINK', ctx),
        'Grow Selection': poly('Grow Selection', 'GROW', ctx),
        'Make Poly': _object('Make Poly', 'CONVERT_POLY', ctx),
        'Center Pivot': _object('Center Pivot', 'CENTER_PIVOT', ctx),
        'Bridge': poly('Bridge', 'BRIDGE', ctx, settings=True, levels=(2, 3, 4, 5)),
        'Relax': poly('Relax', 'RELAX', ctx, settings=True, levels=(0, 1, 2, 3, 4, 5)),
        'Dissolve': poly('Dissolve', 'REMOVE', ctx, levels=(1, 2)),
        'Save Scene': action('Save Scene', 'wm.save_mainfile'),
        'Isolation Mode': _object('Isolation Mode', 'ISOLATE', ctx),
    }
    return tuple(Quadrant(title, tuple(SEPARATOR if not label else supported.get(label, unavailable(label))
                                      for label in labels)) for title, labels in NATHAN_LABELS)


def build(ctx, quad_set='DEFAULT'):
    """Return TL, TR, BL, BR quadrants. The caller owns input and drawing."""
    if quad_set in {'NATHAN', 'MODELING'}:
        return _nathan(ctx)
    if quad_set == 'ANIMATION':
        return _animation(ctx)
    if quad_set in {'LIGHTING', 'UNASSIGNED'}:
        # No complete item list is proven for these variants. Do not invent one.
        title = {'LIGHTING': 'lighting and rendering', 'UNASSIGNED': 'unassigned'}[quad_set]
        return tuple(Quadrant(title if i == 3 else '', ()) for i in range(4))
    upper, lower = _tools(ctx)
    return (Quadrant('tools 1' if upper else '', upper, (5, 0)), Quadrant('display', _display(ctx), (1, 0)),
            Quadrant('tools 2' if lower else '', lower, (0, 3)), Quadrant('transform', _transform(ctx), (0, 1)))


def resolved(ctx, quad_set='DEFAULT'):
    """Apply live operator polls without substituting a different command."""
    import bpy
    def available(cmd):
        if cmd is None:
            return True
        group, name = cmd.operator.split('.')
        try:
            return getattr(getattr(bpy.ops, group), name).poll()
        except (AttributeError, RuntimeError):
            return False
    def resolve(row):
        return replace(row, enabled=row.enabled and available(row.command),
                       settings_enabled=row.enabled and available(row.settings),
                       children=tuple(resolve(child) for child in row.children))
    return tuple(Quadrant(q.title, tuple(resolve(row) for row in q.entries), q.padding, q.width)
                 for q in build(ctx, quad_set))
