"""Curated command menus and the single workspace-chrome installation."""
import bpy
from bpy.app.handlers import persistent
from bpy.props import EnumProperty
from . import max_chrome, max_icons, max_status, max_toolbar, mode_feedback
from .operators import WS_NAME


# Catalogue values are frozen public interface data from the Wave 2 addendum.
MODIFIER_LIST = [('MESH EDITING',
  [('EDIT_POLY', 'Edit Poly'),
   ('SYMMETRY', 'Symmetry'),
   ('MIRROR', 'Mirror'),
   ('WELD', 'Vertex Weld'),
   ('DECIMATE', 'ProOptimizer'),
   ('DECIMATE:PLANAR', 'Optimize'),
   ('DECIMATE', 'MultiRes'),
   ('TRIANGULATE', 'Turn to Mesh'),
   ('MASK', 'Delete Mesh'),
   ('EDGE_SPLIT', 'Smooth'),
   ('NORMAL_EDIT', 'Edit Normals'),
   ('WEIGHTED_NORMAL', 'Weighted Normals'),
   ('REMESH', 'Retopology'),
   ('REMESH:QUAD', 'Quadify Mesh')]),
 ('SUBDIVISION',
  [('TURBOSMOOTH', 'TurboSmooth'),
   ('SUBSURF', 'MeshSmooth'),
   ('SUBSURF', 'OpenSubdiv'),
   ('SUBSURF:SIMPLE', 'Tessellate'),
   ('SUBSURF:SIMPLE', 'Subdivide'),
   ('MULTIRES', 'HSDS')]),
 ('GEOMETRY',
  [('SOLIDIFY', 'Shell'),
   ('BEVEL', 'Chamfer'),
   ('ARRAY', 'Array'),
   ('BOOLEAN', 'Boolean'),
   ('BOOLEAN', 'ProBoolean'),
   ('WIREFRAME', 'Lattice'),
   ('SKIN', 'Skin'),
   ('GN:SLICE', 'Slice'),
   ('DISPLACE', 'Displace')]),
 ('PARAMETRIC DEFORMERS',
  [('SIMPLE_DEFORM:BEND', 'Bend'),
   ('SIMPLE_DEFORM:TWIST', 'Twist'),
   ('SIMPLE_DEFORM:TAPER', 'Taper'),
   ('SIMPLE_DEFORM:STRETCH', 'Stretch'),
   ('GN:SKEW', 'Skew'),
   ('GN:SQUEEZE', 'Squeeze'),
   ('GN:MELT', 'Melt'),
   ('GN:NOISE', 'Noise'),
   ('GN:PUSH', 'Push'),
   ('GN:SPHERIFY', 'Spherify'),
   ('LAPLACIANSMOOTH', 'Relax'),
   ('SMOOTH', 'Smooth Deform'),
   ('WAVE', 'Wave'),
   ('WAVE:RIPPLE', 'Ripple'),
   ('WARP', 'Affect Region')]),
 ('FREE FORM / SURFACE',
  [('LATTICE:2', 'FFD 2x2x2'),
   ('LATTICE:3', 'FFD 3x3x3'),
   ('LATTICE:4', 'FFD 4x4x4'),
   ('LATTICE:5', 'FFD Box'),
   ('SHRINKWRAP', 'Shrink Wrap'),
   ('SHRINKWRAP:PROJECT', 'Conform'),
   ('CURVE', 'Path Deform'),
   ('SURFACE_DEFORM', 'Skin Wrap'),
   ('MESH_DEFORM', 'Skin Morph'),
   ('ARMATURE', 'Skin'),
   ('HOOK', 'Linked XForm')]),
 ('UV / SHAPE / ANIMATION',
  [('UV_PROJECT', 'UVW Map'),
   ('UNWRAP', 'Unwrap UVW'),
   ('UV_WARP', 'UVW XForm'),
   ('EXTRUDE_SHAPE', 'Extrude'),
   ('SCREW', 'Lathe'),
   ('SWEEP', 'Sweep / Renderable'),
   ('CLOTH', 'Cloth'),
   ('SOFT_BODY', 'Flex'),
   ('MESH_CACHE', 'Point Cache'),
   ('PARTICLE_SYSTEM', 'Particle Flow'),
   ('PARTICLE_SYSTEM:HAIR', 'Hair and Fur'),
   ('OCEAN', 'Ocean (Blender)')])]
CATEGORY_MENUS = []
MAX_MENUBAR = [
    ('TOPBAR_MT_file', 'File'), ('MAX_MT_edit', 'Edit'), ('MAX_MT_tools', 'Tools'),
    ('MAX_MT_group', 'Group'), ('MAX_MT_views', 'Views'), ('MAX_MT_create', 'Create'),
    ('MAX_MT_modifier_list', 'Modifiers'), ('MAX_MT_animation', 'Animation'),
    ('MAX_MT_graph_editors', 'Graph Editors'), ('MAX_MT_rendering', 'Rendering'),
    ('MAX_MT_customize', 'Customize'), ('MAX_MT_scripting', 'Scripting'),
    ('TOPBAR_MT_help', 'Help'),
]
_installed = False
_installed_services = []
_drawing_adapters = []


def _item(layout, command, text, *, art=None, enabled=True, pressed=False, **values):
    row = layout.row(align=True)
    row.enabled = enabled
    icons = max_icons.ui(art, 'NONE') if art else {}
    button = row.operator(command, text=text, depress=pressed, **icons)
    for key, value in values.items():
        setattr(button, key, value)
    return button


def _object(layout, token, label, **kwargs):
    kwargs.setdefault('enabled', token in {'UNHIDE', 'UNFREEZE', 'LINK'} or bool(bpy.context.selected_objects))
    return _item(layout, 'max.object_cmd', label, cmd=token, **kwargs)


def _edit(layout, token, label):
    return _item(layout, 'max.edit_poly', label, op=token)


def _editor(layout, token, label):
    return _item(layout, 'max.open_editor', label, editor=token)


def _unavailable(layout, label, reason):
    _item(layout, 'max.chrome_unavailable', label, enabled=False, reason=reason)


def _modifier_items(include_backend=False):
    result = []
    for _, entries in MODIFIER_LIST:
        for token, label in entries:
            if token == 'OCEAN' and not include_backend:
                continue
            result.append((token + '|' + label, label, 'Add ' + label))
    return result


class MAX_OT_modifier_search(bpy.types.Operator):
    bl_idname = 'max.modifier_search'
    bl_label = 'Modifier List'
    bl_description = 'Search supported modifiers by their Max names'
    bl_property = 'search_kind'
    kind: EnumProperty(items=lambda self, context: _modifier_enum)
    search_kind: EnumProperty(items=lambda self, context: _modifier_search_enum, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        value = self.search_kind if self.properties.is_property_set('search_kind') else self.kind
        return bpy.ops.max.add_modifier(kind=value)


class MAX_MT_modifier_list(bpy.types.Menu):
    bl_label = 'Modifier List'

    def draw(self, context):
        _item(self.layout, 'max.modifier_search', 'Search Modifiers...', art='modifier_list')
        self.layout.separator()
        for cls in CATEGORY_MENUS:
            self.layout.menu(cls.__name__)


def _draw_category(self, context):
    for token, label in MODIFIER_LIST[self.category][1]:
        if token == 'OCEAN':
            continue
        _item(self.layout, 'max.add_modifier', label, kind=token + '|' + label,
              enabled=context.active_object is not None)


class MAX_MT_sublevels(bpy.types.Menu):
    bl_label = 'Sub-object'

    def draw(self, context):
        mode_feedback.draw_sublevel_menu(self.layout, context)


class MAX_MT_convert(bpy.types.Menu):
    bl_label = 'Convert To'

    def draw(self, context):
        _object(self.layout, 'CONVERT_POLY', 'Convert to Editable Poly')
        _object(self.layout, 'CONVERT_SPLINE', 'Convert to Editable Spline')


class MAX_MT_quad(bpy.types.Menu):
    bl_label = 'Quad Menu'

    def draw(self, context):
        # W2.D replaces this compatibility menu with the four-quadrant host.
        col = self.layout.column()
        col.label(text='Display')
        for token, label in [('HIDE_SEL', 'Hide Selection'), ('HIDE_UNSEL', 'Hide Unselected'),
                             ('UNHIDE', 'Unhide All'), ('FREEZE', 'Freeze Selection'),
                             ('UNFREEZE', 'Unfreeze All')]:
            _object(col, token, label)
        _item(col, 'max.scene_selection_dialog', 'Hide by Name...', hide=True)
        _item(col, 'max.unfreeze_by_name', 'Unfreeze by Name...')
        col.separator()
        col.label(text='Transform')
        for token, label in [('MOVE', 'Move'), ('ROTATE', 'Rotate'), ('SCALE', 'Scale')]:
            _item(col, 'max.select_transform', label, kind=token,
                  pressed=mode_feedback.tool_pressed(context, token))
        _item(col, 'max.transform_typein', 'Transform Type-In...')
        col.menu('MAX_MT_convert')
        _item(col, 'max.object_properties', 'Object Properties...')


class MAX_MT_quad_modeling(bpy.types.Menu):
    bl_label = 'Modeling'

    def draw(self, context):
        mode_feedback.draw_sublevel_menu(self.layout, context, order=(1, 2, 3, 4, 5, 0))
        self.layout.separator()
        for token, label in [('EXTRUDE', 'Extrude'), ('CHAMFER', 'Chamfer'),
                             ('CONNECT', 'Connect'), ('BRIDGE', 'Bridge'), ('RELAX', 'Relax'),
                             ('LOOP', 'Loop'), ('RING', 'Ring'), ('TARGET_WELD', 'Target Weld')]:
            _edit(self.layout, token, label)
        _item(self.layout, 'max.quad_cap', 'Quad Cap')
        _item(self.layout, 'max.loop_regularize', 'Loop Regularizer')


class MAX_MT_create(bpy.types.Menu):
    bl_label = 'Create'

    def draw(self, context):
        for menu, label in [('MAX_MT_workspace_standard', 'Standard Primitives'),
                            ('MAX_MT_workspace_extended', 'Extended Primitives'),
                            ('MAX_MT_workspace_planeplus', 'JokerMartini'),
                            ('MAX_MT_workspace_shapes', 'Shapes'),
                            ('MAX_MT_workspace_lights', 'Lights'),
                            ('MAX_MT_workspace_cameras', 'Cameras'),
                            ('MAX_MT_workspace_helpers', 'Helpers')]:
            self.layout.menu(menu, text=label)


def _create_family(self, context):
    from . import create, prims
    family = self.family
    if family == 'standard':
        for kind in ('BOX', 'CONE', 'SPHERE', 'GEOSPHERE', 'CYLINDER', 'TUBE', 'TORUS', 'PYRAMID', 'PLANE'):
            label = prims.PRIMITIVES[kind][0]
            _item(self.layout, 'max.create', label, kind=kind)
        _unavailable(self.layout, 'Teapot', 'Teapot is not supplied')
        _unavailable(self.layout, 'TextPlus', 'TextPlus is not supplied')
    elif family == 'extended':
        from . import extended_primitives
        for kind, record in extended_primitives.PRIMITIVES.items():
            _item(self.layout, 'max.create', record[0], kind=kind)
    elif family == 'planeplus':
        _item(self.layout, 'max.plane_plus', 'PlanePlus')
    elif family in {'shapes', 'lights', 'helpers'}:
        catalogue = getattr(create, family.upper())
        route = {'shapes': 'max.create_shape', 'lights': 'max.create_light', 'helpers': 'max.create_helper'}[family]
        for kind, label, *_ in catalogue:
            _item(self.layout, route, label, kind=kind)
    else:
        _item(self.layout, 'max.create_camera', 'Free Camera', target=False)
        _item(self.layout, 'max.create_camera', 'Target Camera', target=True)


class MAX_MT_views(bpy.types.Menu):
    bl_label = 'Views'

    def draw(self, context):
        for token, label in [('PERSP', 'Perspective'), ('ORTHO', 'Orthographic'),
                             ('TOP', 'Top'), ('BOTTOM', 'Bottom'), ('FRONT', 'Front'),
                             ('BACK', 'Back'), ('LEFT', 'Left'), ('RIGHT', 'Right'), ('CAMERA', 'Camera')]:
            _item(self.layout, 'max.set_view', label, view=token)
        self.layout.separator()
        _item(self.layout, 'max.zoom_extents', 'Zoom Extents Selected')
        _item(self.layout, 'max.toggle_quad', 'Maximize Viewport Toggle')
        _item(self.layout, 'max.expert_mode', 'Expert Mode')
        _item(self.layout, 'max.viewcube_configure', 'ViewCube Settings...')
        _item(self.layout, 'max.viewport_configure', 'Viewport Configuration...')
        self.layout.menu('MAX_MT_xview', text='xView')


class MAX_MT_rendering(bpy.types.Menu):
    bl_label = 'Rendering'

    def draw(self, context):
        _item(self.layout, 'render.render', 'Render', use_viewport=True)
        _editor(self.layout, 'RENDER_SETUP', 'Render Setup...')
        _editor(self.layout, 'ENVIRONMENT', 'Environment and Effects...')
        _editor(self.layout, 'MATERIAL', 'Material Editor...')
        _item(self.layout, 'render.view_show', 'Rendered Frame Window')


class MAX_MT_edit(bpy.types.Menu):
    bl_label = 'Edit'

    def draw(self, context):
        _item(self.layout, 'ed.undo', 'Undo', art='undo')
        _item(self.layout, 'ed.redo', 'Redo', art='redo')
        self.layout.separator()
        for token, label in [('SELECT', 'Select All'), ('DESELECT', 'Select None'), ('INVERT', 'Select Invert')]:
            _item(self.layout, 'max.select_all', label, action=token)
        _item(self.layout, 'max.select_by_name', 'Select From Scene...', art='select_by_name')
        self.layout.menu('MAX_MT_sublevels')
        self.layout.separator()
        _item(self.layout, 'max.clone', 'Clone...')
        _item(self.layout, 'max.delete', 'Delete')
        _item(self.layout, 'max.object_properties', 'Object Properties...')
        self.layout.menu('MAX_MT_workspace_advanced', text='Advanced')


class MAX_MT_tools(bpy.types.Menu):
    bl_label = 'Tools'

    def draw(self, context):
        _item(self.layout, 'max.transform_typein', 'Transform Type-In...')
        _object(self.layout, 'MIRROR', 'Mirror...')
        _object(self.layout, 'ALIGN', 'Align...')
        _item(self.layout, 'max.workspace_align_world', 'Align to World')
        self.layout.separator()
        _object(self.layout, 'RESET_XFORM', 'Reset XForm')
        _object(self.layout, 'CENTER_PIVOT', 'Center Pivot')
        _object(self.layout, 'PIVOT_TO_WORLD', 'Pivot to World Origin')
        _item(self.layout, 'max.snap_settings', 'Grid and Snap Settings...')
        _item(self.layout, 'max.gizmo_preferences', 'Transform Gizmo Preferences...')
        self.layout.separator()
        self.layout.menu('MAX_MT_workspace_utilities', text='Maxxed Utilities')


class MAX_MT_group(bpy.types.Menu):
    bl_label = 'Group'

    def draw(self, context):
        _item(self.layout, 'max.group', 'Group', action='GROUP')
        _item(self.layout, 'max.group', 'Ungroup', action='UNGROUP')
        self.layout.separator()
        _item(self.layout, 'max.layer_dialog', 'Move to Layer...')
        _item(self.layout, 'max.workspace_layer_explorer', 'Layer Explorer...')


class MAX_MT_animation(bpy.types.Menu):
    bl_label = 'Animation'

    def draw(self, context):
        _item(self.layout, 'max.toggle', 'Auto Key', what='AUTOKEY', pressed=context.tool_settings.use_keyframe_insert_auto)
        _item(self.layout, 'max.set_key', 'Set Key')
        _item(self.layout, 'max.chrome_time_config', 'Time Configuration...')
        self.layout.separator()
        _editor(self.layout, 'CURVE_EDITOR', 'Curve Editor...')
        _editor(self.layout, 'DOPE_SHEET', 'Dope Sheet...')


class MAX_MT_graph_editors(bpy.types.Menu):
    bl_label = 'Graph Editors'

    def draw(self, context):
        for token, label in [('CURVE_EDITOR', 'Track View - Curve Editor...'),
                             ('DOPE_SHEET', 'Track View - Dope Sheet...'),
                             ('SCHEMATIC', 'Schematic View...'), ('SCENE_EXPLORER', 'Scene Explorer...')]:
            _editor(self.layout, token, label)


class MAX_MT_customize(bpy.types.Menu):
    bl_label = 'Customize'

    def draw(self, context):
        _item(self.layout, 'max.preferences_dialog', 'Preference Settings...')
        _item(self.layout, 'max.import_hsx', 'Import 3ds Max Hotkeys...')
        _item(self.layout, 'max.clear_hsx_hotkeys', 'Clear Imported Hotkeys')
        self.layout.menu('MAX_MT_workspaces')
        self.layout.separator()
        _item(self.layout, 'max.apply', 'Apply Maxxed Appearance and Layout')
        _item(self.layout, 'max.restore', 'Restore Previous Appearance and Layout')
        self.layout.menu('MAX_MT_workspace_advanced', text='Advanced')


class MAX_MT_scripting(bpy.types.Menu):
    bl_label = 'Scripting'

    def draw(self, context):
        _editor(self.layout, 'SCRIPT_EDITOR', 'Python Script Editor...')
        _editor(self.layout, 'LISTENER', 'Python Listener...')


class MAX_MT_workspaces(bpy.types.Menu):
    bl_label = 'Workspaces'

    def draw(self, context):
        _item(self.layout, 'max.chrome_layout', 'Single Perspective', quad=False)
        _item(self.layout, 'max.chrome_layout', 'Four Viewports', quad=True)


class MAX_MT_workspace_file(bpy.types.Menu):
    bl_label = 'File'

    def draw(self, context):
        for token, label in [('NEW', 'New Scene...'), ('OPEN', 'Open Scene (.blend)...'),
                             ('SAVE', 'Save Scene (.blend)'), ('SAVE_AS', 'Save Scene As (.blend)...')]:
            _item(self.layout, 'max.scene_file_dialog', label, action=token)
        _item(self.layout, 'max.scene_file_dialog', 'Reset Scene...', action='NEW')
        self.layout.separator()
        _item(self.layout, 'max.open_max', 'Open 3ds Max (.max)...')
        _item(self.layout, 'max.merge_max', 'Merge 3ds Max (.max)...')
        _item(self.layout, 'max.import_max_fbx', 'Import FBX...')
        _item(self.layout, 'max.export_max_fbx', 'Export FBX...')
        self.layout.separator()
        _item(self.layout, 'wm.quit_blender', 'Exit')


class MAX_MT_workspace_help(bpy.types.Menu):
    bl_label = 'Help'

    def draw(self, context):
        _item(self.layout, 'wm.url_open', '3ds Max 2026 Help', url='https://help.autodesk.com/view/3DSMAX/2026/ENU/')
        _item(self.layout, 'max.preferences_dialog', 'Maxxed Preferences and Hotkeys...')
        _item(self.layout, 'wm.splash_about', 'About Blender / Maxxed Backend')
        self.layout.menu('MAX_MT_workspace_advanced', text='Advanced')


class MAX_MT_workspace_advanced(bpy.types.Menu):
    bl_label = 'Advanced'

    def draw(self, context):
        _item(self.layout, 'screen.userpref_show', 'Blender Preferences...')
        _editor(self.layout, 'LISTENER', 'Python Listener...')
        _item(self.layout, 'wm.sysinfo', 'Save Blender System Information...')


class MAX_MT_workspace_utilities(bpy.types.Menu):
    bl_label = 'Maxxed Utilities'

    def draw(self, context):
        _item(self.layout, 'max.animate_melt', 'Animate Melt...')
        _item(self.layout, 'max.key_melt', 'Key Melt Amount')
        _item(self.layout, 'max.quad_cap', 'Quad Cap')
        _item(self.layout, 'max.loop_regularize', 'Loop Regularizer')


class MAX_OT_workspace_align_world(bpy.types.Operator):
    bl_idname = 'max.workspace_align_world'
    bl_label = 'Align to World'
    bl_description = 'Align selected object axes to World without moving their pivots'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def execute(self, context):
        from mathutils import Matrix, Quaternion
        from .operators import _write_world
        snapshots = {o: o.matrix_world.copy() for o in context.selected_objects}
        children = {c: c.matrix_world.copy() for o in snapshots for c in o.children if c not in snapshots}
        aligned = {}
        for obj, matrix in snapshots.items():
            position, _, scale = matrix.decompose()
            aligned[obj] = Matrix.LocRotScale(position, Quaternion(), scale)
        _write_world(context, {**aligned, **children})
        return {'FINISHED'}


class MAX_OT_workspace_layer_explorer(bpy.types.Operator):
    bl_idname = 'max.workspace_layer_explorer'
    bl_label = 'Layer Explorer'
    bl_description = 'Open the shared Scene Explorer and its layer controls'

    def execute(self, context):
        return bpy.ops.max.open_editor(editor='SCENE_EXPLORER')


def _menus(layout, context):
    layout.scale_x = .92
    for route, label in MAX_MENUBAR:
        route = {'TOPBAR_MT_file': 'MAX_MT_workspace_file', 'TOPBAR_MT_help': 'MAX_MT_workspace_help'}.get(route, route)
        layout.menu(route, text=label)
        if label in {'Rendering', 'Scripting'}:
            unavailable = layout.row(align=True)
            unavailable.enabled = False
            unavailable.label(text='Civil View' if label == 'Rendering' else 'Content')


def topbar_draw_left(self, context):
    _menus(self.layout, context)


def topbar_draw_right(self, context):
    self.layout.menu('MAX_MT_workspaces', text=WS_NAME)


def view3d_header_draw(self, context):
    draw_main_toolbar(self, context)


def draw_main_toolbar(self, context):
    max_toolbar.draw(self.layout, context)


def _active_tool(context):
    return mode_feedback.active_tool(context)


def _workspace_toolbar(layout, context):
    """Use the W1.4 controls with the accepted operation-specific managers."""
    from . import max_rotate, snaps
    row = layout.row(align=True)
    button = max_toolbar.button
    optional = max_toolbar.optional
    button(row, 'ed.undo', 'undo', 'LOOP_BACK')
    button(row, 'ed.redo', 'redo', 'LOOP_FORWARDS')
    row.separator()
    button(row, 'wm.tool_set_by_id', 'link', 'LINKED', name='max.select_link',
           pressed=mode_feedback.tool_pressed(context, 'LINK'))
    button(row, 'max.object_cmd', 'unlink', 'UNLINKED', cmd='UNLINK')
    button(row, 'max.chrome_unavailable', 'bind_space_warp', reason='Space Warp binding is not supported')
    row.separator()
    max_toolbar.filter_control(row, context)
    button(row, 'wm.tool_set_by_id', 'select_object', 'RESTRICT_SELECT_OFF',
           name='builtin.select_box', pressed=mode_feedback.tool_pressed(context, 'SELECT'))
    optional(row, 'select_by_name', 'select_by_name', 'Select From Scene')
    row.menu('MAX_MT_chrome_region', text='', **max_icons.ui('region_rect', 'SELECT_SET'))
    crossing = row.row(align=True)
    crossing.enabled = context.mode == 'OBJECT'
    crossing.prop(context.window_manager, 'max_chrome_crossing', text='', toggle=True,
                  **max_icons.ui('window_crossing', 'SELECT_INTERSECT'))
    row.separator()
    for kind, key in [('MOVE', 'move'), ('ROTATE', 'rotate'), ('SCALE', 'scale')]:
        button(row, 'max.select_transform', key, 'ORIENTATION_GLOBAL', kind=kind,
               pressed=mode_feedback.tool_pressed(context, kind))
        if kind == 'SCALE':
            row.menu('MAX_MT_scale_flyout', text='', icon='DOWNARROW_HLT')
    optional(row, 'select_place', 'select_place', 'Select and Place')
    row.separator()
    max_rotate.draw_managers(row, context)
    row.separator()
    optional(row, 'shortcut_override', 'shortcut_override', 'Keyboard Shortcut Override')
    snaps.draw_toolbar(row, context)
    row.separator()
    max_toolbar.sets_control(row, context)
    row.separator()
    optional(row, 'mirror', 'mirror', 'Mirror')
    row.menu('MAX_MT_chrome_align', text='', **max_icons.ui('align', 'ALIGN_CENTER'))
    row.separator()
    for name, art, label in [('scene_explorer', 'scene_explorer', 'Scene Explorer'),
                              ('layer_explorer', 'layer_explorer', 'Layer Explorer'),
                              ('ribbon', 'ribbon', 'Toggle Ribbon'),
                              ('track_view', 'track_view', 'Track View'),
                              ('schematic_view', 'schematic_view', 'Schematic View')]:
        optional(row, name, art, label)


def _workspace_status(layout, context):
    # Native transform instructions retain precedence over idle tool prompts.
    native = next((old for owner, name, old, _ in _drawing_adapters if owner is bpy.types.STATUSBAR_HT_header), None)
    passive = mode_feedback.PASSIVE_MODALS | {'MAX_OT_editor_interact'}
    if any(op and op.bl_idname not in passive
           for op in getattr(context.window, 'modal_operators', ())):
        if native:
            return native(type('StatusHost', (), {'layout': layout})(), context)
    _status_draw(layout, context)


def _workspace_prompt(context):
    # The time host draws the separate prompt line for the modeling viewport.
    from . import operators
    with operators._viewport(context):
        return _provider_function(max_status, 'prompt_text')(bpy.context)


def _auxiliary_area(context):
    from . import max_editor_windows
    area = getattr(context, 'area', None)
    if area is None or not hasattr(area, 'as_pointer'):
        return False
    window = getattr(context, 'window', None)
    host = max_editor_windows._hosts.get(window.as_pointer()) if window else None
    return (max_chrome.timeline_area(area)
            or area.as_pointer() in max_editor_windows._docked
            or bool(host and host.area == area))


def _provider_function(owner, name):
    return next(old for target, attribute, old, _ in _drawing_adapters if target is owner and attribute == name)


def _workspace_labels(context):
    from . import overlay
    return not _auxiliary_area(context) and _provider_function(overlay, '_visible')(context)


def _workspace_tool(context):
    return '' if _auxiliary_area(context) else _provider_function(mode_feedback, 'active_tool')(context)


def _workspace_border(context):
    if not _auxiliary_area(context):
        _provider_function(mode_feedback, '_draw_view_border')(context)


def _workspace_cube(context):
    from . import viewcube
    return not _auxiliary_area(context) and _provider_function(viewcube, 'visible')(context)


@persistent
def _order_saved_editors(*_):
    from . import max_editor_windows
    # Opening a native auxiliary window changes Blender's screen context until
    # the next event-loop turn. Restore the main window's docks before that.
    max_editor_windows._saved_hosts.sort(key=lambda item: item[0] != 'DOCK')


def _adapt(owner, name, callback):
    _drawing_adapters.append((owner, name, getattr(owner, name), callback))
    setattr(owner, name, callback)


def draw_statusbar(self, context):
    max_status.draw(self.layout, context)


def max_statusbar_draw(self, context):
    draw_statusbar(self, context)


def register_draw():
    global _installed
    if _installed:
        return
    from . import max_layers, scene_explorer, max_dialogs, max_preferences, max_editor_windows
    from . import operators, overlay, viewcube
    for service in (max_layers, scene_explorer, max_dialogs, max_preferences, max_editor_windows):
        service.install()
        _installed_services.append(service)
    # Adapt provider drawing once. max_chrome still owns all native callbacks.
    _drawing_adapters.append((bpy.types.STATUSBAR_HT_header, 'draw', bpy.types.STATUSBAR_HT_header.draw, None))
    _adapt(max_toolbar, 'draw', _workspace_toolbar)
    _adapt(max_status, 'draw', _workspace_status)
    _adapt(max_status, 'prompt_text', _workspace_prompt)
    _adapt(overlay, '_visible', _workspace_labels)
    _adapt(mode_feedback, 'active_tool', _workspace_tool)
    _adapt(mode_feedback, 'PASSIVE_MODALS', mode_feedback.PASSIVE_MODALS | {'MAX_OT_editor_interact'})
    _adapt(mode_feedback, '_draw_view_border', _workspace_border)
    _adapt(viewcube, 'visible', _workspace_cube)
    max_chrome.install(feedback=mode_feedback, draw_menus=_menus,
                       apply_explorer=operators._explorer_layout,
                       read_transform=operators.read_transform, write_transform=operators.write_transform,
                       commands={
                           'select_by_name': 'max.select_by_name', 'mirror': 'max.workspace_mirror',
                           'align': 'max.workspace_align', 'scene_explorer': 'max.workspace_scene_explorer',
                           'layer_explorer': 'max.workspace_layer_explorer',
                           'track_view': 'max.workspace_track_view', 'schematic_view': 'max.workspace_schematic',
                       })
    max_dialogs.configure_transform(reader=operators.read_transform, writer=operators.write_transform)
    bpy.app.handlers.load_pre.append(_before_file_load)
    bpy.app.handlers.load_post.append(_after_file_load)
    bpy.app.handlers.save_pre.append(_order_saved_editors)
    _installed = True


def unregister_draw():
    global _installed
    if not _installed:
        return
    from . import operators
    max_chrome.uninstall()
    operators.close_material_compat()
    operators.restore_layout(bpy.context)
    if _before_file_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_before_file_load)
    if _after_file_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_after_file_load)
    if _order_saved_editors in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_order_saved_editors)
    for owner, name, old, ours in reversed(_drawing_adapters):
        if ours is not None and getattr(owner, name) is ours:
            setattr(owner, name, old)
    _drawing_adapters.clear()
    for service in reversed(_installed_services):
        service.uninstall()
    _installed_services.clear()
    _installed = False


def _status_draw(layout, context):
    original = next(old for owner, name, old, _ in _drawing_adapters if owner is max_status)
    original(layout, context)


@persistent
def _before_file_load(*_):
    from . import operators
    operators.cancel_layout()
    operators.close_material_compat()
    operators._layout_snapshot.clear()


@persistent
def _after_file_load(*_):
    if not _installed or bpy.app.background:
        return
    from . import operators
    for window in bpy.context.window_manager.windows:
        if window.workspace.name == WS_NAME:
            with bpy.context.temp_override(window=window):
                operators._explorer_layout(bpy.context)


def _toolbar_route(self, context):
    if self.action in {'MIRROR', 'ALIGN'}:
        return bpy.ops.max.object_cmd('INVOKE_DEFAULT', cmd=self.action)
    return bpy.ops.max.open_editor(editor=self.action)


def _finish_catalogues():
    global _modifier_enum, _modifier_search_enum
    _modifier_enum = _modifier_items(include_backend=True)
    _modifier_search_enum = _modifier_items()
    for index, (label, _) in enumerate(MODIFIER_LIST):
        CATEGORY_MENUS.append(type(f'MAX_MT_modlist_{index}', (bpy.types.Menu,), {
            '__module__': __name__, 'bl_label': label.title(), 'category': index, 'draw': _draw_category,
        }))


_create_menus = [type('MAX_MT_workspace_' + family, (bpy.types.Menu,), {
    '__module__': __name__, 'bl_label': family.title(), 'family': family, 'draw': _create_family,
}) for family in ('standard', 'extended', 'planeplus', 'shapes', 'lights', 'cameras', 'helpers')]

_toolbar_routes = [type('MAX_OT_workspace_' + suffix, (bpy.types.Operator,), {
    '__module__': __name__,
    'bl_idname': 'max.workspace_' + suffix, 'bl_label': label,
    'bl_description': description, 'action': action, 'execute': _toolbar_route,
}) for suffix, action, label, description in (
    ('mirror', 'MIRROR', 'Mirror', 'Open Mirror options for the selection'),
    ('align', 'ALIGN', 'Align', 'Open Align options for the selection'),
    ('scene_explorer', 'SCENE_EXPLORER', 'Scene Explorer', 'Open the shared scene hierarchy'),
    ('track_view', 'CURVE_EDITOR', 'Track View', 'Open the animation Curve Editor'),
    ('schematic', 'SCHEMATIC', 'Schematic View', 'Open object relationship links'),
)]

# The catalogue initializer runs after the frozen data block below.

_finish_catalogues()
classes = (MAX_OT_modifier_search, *CATEGORY_MENUS, MAX_MT_modifier_list,
           MAX_MT_quad, MAX_MT_quad_modeling, MAX_MT_sublevels, MAX_MT_convert,
           MAX_MT_create, *_create_menus, MAX_MT_views, MAX_MT_rendering, MAX_MT_edit,
           MAX_MT_tools, MAX_MT_group, MAX_MT_animation, MAX_MT_graph_editors,
           MAX_MT_customize, MAX_MT_scripting, MAX_MT_workspaces,
           MAX_MT_workspace_file, MAX_MT_workspace_help, MAX_MT_workspace_advanced,
           MAX_MT_workspace_utilities, MAX_OT_workspace_align_world,
           MAX_OT_workspace_layer_explorer, *_toolbar_routes)
