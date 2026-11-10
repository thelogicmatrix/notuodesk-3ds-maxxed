"""Workspace commands and compatibility routes for the Maxxed interface."""
import math
from contextlib import nullcontext

import bpy
import bmesh
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty
from mathutils import Matrix, Quaternion, Vector


WS_NAME = '3ds Max'
MTL_EDITOR_WIDTH = 640
LEVEL_NAMES = {0: 'Object', 1: 'Vertex', 2: 'Edge', 3: 'Border', 4: 'Polygon', 5: 'Element'}
VIEW_ROTATIONS = {
    'TOP': Quaternion((1, 0, 0, 0)),
    'BOTTOM': Quaternion((0, 1, 0, 0)),
    'FRONT': Quaternion((math.sqrt(.5), math.sqrt(.5), 0, 0)),
    'BACK': Quaternion((0, 0, math.sqrt(.5), math.sqrt(.5))),
    'LEFT': Quaternion((.5, .5, -.5, -.5)),
    'RIGHT': Quaternion((.5, .5, .5, .5)),
}


def _catalogue(pairs):
    return [(key, label, '') for key, label in pairs]


EDIT_POLY_OPS = _catalogue([
    ('EXTRUDE', 'Extrude'), ('CHAMFER', 'Chamfer'), ('CONNECT', 'Connect'),
    ('REMOVE', 'Remove'), ('REMOVE_WITH_VERTS', 'Remove (with vertices)'),
    ('LOOP', 'Loop'), ('RING', 'Ring'), ('WELD', 'Weld'),
    ('TARGET_WELD', 'Target Weld'), ('BRIDGE', 'Bridge'), ('INSET', 'Inset'),
    ('OUTLINE', 'Outline'), ('CAP', 'Cap'), ('FLIP', 'Flip'), ('DETACH', 'Detach'),
    ('BREAK', 'Break'), ('COLLAPSE', 'Collapse'), ('RELAX', 'Relax'),
    ('MSMOOTH', 'MSmooth'), ('TESSELLATE', 'Tessellate'), ('MAKE_PLANAR', 'Make Planar'),
    ('SLICE_PLANE', 'Slice Plane'), ('CUT', 'Cut'), ('HIDE_SEL', 'Hide Selected'),
    ('HIDE_UNSEL', 'Hide Unselected'), ('UNHIDE', 'Unhide All'),
    ('OPEN_EDGES', 'Select Open Edges'), ('GROW', 'Grow'), ('SHRINK', 'Shrink'),
    ('SWIFT_LOOP', 'SwiftLoop'), ('BEVEL', 'Bevel'),
])
from . import editable_poly
EDIT_POLY_OPS += list(editable_poly.EXTRA_OPS)

OBJECT_CMDS = [
    ('CONVERT_POLY', 'Convert to Editable Poly', 'Collapse the modifier stack into an editable mesh'),
    ('CONVERT_SPLINE', 'Convert to Editable Spline', 'Convert to a curve object'),
    ('RESET_XFORM', 'Reset XForm', 'Bake rotation and scale into the object (Apply Rotation & Scale)'),
    ('CENTER_PIVOT', 'Center to Object', 'Move the pivot to the center of the object'),
    ('PIVOT_TO_WORLD', 'Pivot to World Origin', 'Move the pivot to the world origin'),
    ('OBJECT_TO_PIVOT', 'Center Object to Pivot', 'Move the object so its center is at the pivot'),
    ('HIDE_SEL', 'Hide Selection', ''), ('HIDE_UNSEL', 'Hide Unselected', ''),
    ('UNHIDE', 'Unhide All', ''),
    ('FREEZE', 'Freeze Selection', 'Lock selection and snapping, respecting Show Frozen in Gray'),
    ('UNFREEZE', 'Unfreeze All', ''), ('DISPLAY_BOX', 'Display as Box', 'Toggle bounding box display'),
    ('SEE_THROUGH', 'See-Through', 'Toggle drawing the selection in front'),
    ('EDGES_ONLY', 'Show Wireframe on Object', 'Toggle wireframe over shaded'),
    ('LINK', 'Select and Link', 'Parent selection to the active object'),
    ('UNLINK', 'Unlink Selection', 'Clear parent, keep transform'),
    ('ATTACH', 'Attach', 'Join selected objects into the active one'),
    ('MIRROR', 'Mirror', 'Mirror the selection'), ('ALIGN', 'Align', 'Align objects'),
    ('ISOLATE', 'Isolate Selection', 'Local view (Alt+Q)'),
]
EDITORS = {
    'MATERIAL': ('ShaderNodeTree', None, 'Material Editor'),
    'RENDER_SETUP': ('PROPERTIES', 'RENDER', 'Render Setup'),
    'ENVIRONMENT': ('PROPERTIES', 'WORLD', 'Environment and Effects'),
    'CURVE_EDITOR': ('FCURVES', None, 'Curve Editor'),
    'DOPE_SHEET': ('DOPESHEET', None, 'Dope Sheet'),
    'SCENE_EXPLORER': ('OUTLINER', None, 'Scene Explorer'),
    'SCHEMATIC': ('GeometryNodeTree', None, 'Schematic View'),
    'SCRIPT_EDITOR': ('TEXT_EDITOR', None, 'Script Editor'),
    'LISTENER': ('CONSOLE', None, 'Python Listener'),
}
_level_write = False
_layout_snapshot = {}
_layout_jobs = {}
_material_windows = {}
_scene_item_cache = []


def max_name(base):
    number = 1
    while f'{base}{number:03d}' in bpy.data.objects:
        number += 1
    return f'{base}{number:03d}'


def find_view3d(context):
    screen = context.window.screen if context.window else getattr(context, 'screen', None)
    areas = [a for a in screen.areas if a.type == 'VIEW_3D'] if screen else []
    # The chrome time host is a viewport for drawing, never a modeling target.
    from . import max_chrome, max_editor_windows
    areas = [a for a in areas if not max_chrome.timeline_area(a)
             and a.as_pointer() not in max_editor_windows._docked]
    area = context.area if context.area in areas else max(areas, key=lambda a: a.width * a.height, default=None)
    if area is None:
        return None, None
    regions = [r for r in area.regions if r.type == 'WINDOW']
    region = context.region if context.region in regions else next(iter(reversed(regions)), None)
    return area, region


def viewport_override(context):
    area, region = find_view3d(context)
    return {'window': context.window, 'area': area, 'region': region} if area else None


def has_view3d(context):
    return find_view3d(context)[0] is not None


def _viewport(context):
    override = viewport_override(context)
    return context.temp_override(**override) if override else nullcontext()


def _active_tool(context):
    from . import mode_feedback
    with _viewport(context):
        return mode_feedback.active_tool(bpy.context)


def mesh_select_mode(context):
    flags = context.tool_settings.mesh_select_mode
    return 'VERT' if flags[0] else 'EDGE' if flags[1] else 'FACE'


def _compatible(level, mode):
    return level in {'VERT': (1,), 'EDGE': (2, 3), 'FACE': (4, 5)}[mode]


def stored_mesh_level(obj):
    if obj is None or obj.type != 'MESH':
        return 0
    if obj.data.is_editmode:
        try:
            layers = bmesh.from_edit_mesh(obj.data).verts.layers.int
            return next((level for level in range(1, 6) if layers.get(f'.max_sublevel_{level}')), 0)
        except (ValueError, RuntimeError):
            pass
    return next((level for level in range(1, 6) if obj.data.attributes.get(f'.max_sublevel_{level}')), 0)


def _store_level(obj, level):
    if obj.data.is_editmode:
        layers = bmesh.from_edit_mesh(obj.data).verts.layers.int
        for old in range(1, 6):
            layer = layers.get(f'.max_sublevel_{old}')
            if layer and old != level:
                layers.remove(layer)
        if level and layers.get(f'.max_sublevel_{level}') is None:
            layers.new(f'.max_sublevel_{level}')
    else:
        attributes = obj.data.attributes
        for old in range(1, 6):
            layer = attributes.get(f'.max_sublevel_{old}')
            if layer and old != level:
                attributes.remove(layer)
        if level and attributes.get(f'.max_sublevel_{level}') is None:
            attributes.new(f'.max_sublevel_{level}', 'INT', 'POINT')


def current_level(context):
    if context.mode == 'OBJECT':
        return 0
    if context.mode != 'EDIT_MESH':
        return getattr(context.window_manager, 'max_sublevel', 0)
    mode = mesh_select_mode(context)
    level = stored_mesh_level(context.active_object)
    return level if _compatible(level, mode) else {'VERT': 1, 'EDGE': 2, 'FACE': 4}[mode]


def sublevel_changed(wm, context):
    if _level_write or context.mode != 'EDIT_MESH':
        return
    level = wm.max_sublevel
    if level and _compatible(level, mesh_select_mode(context)):
        seen = set()
        for obj in context.objects_in_mode_unique_data:
            if obj.type == 'MESH' and obj.data not in seen:
                _store_level(obj, level)
                seen.add(obj.data)


def sync_sublevel(context):
    global _level_write
    if _level_write:
        return
    level = current_level(context)
    if context.mode == 'EDIT_MESH':
        for obj in context.objects_in_mode_unique_data:
            if obj.type == 'MESH' and stored_mesh_level(obj) != level:
                _store_level(obj, level)
    _level_write = True
    try:
        context.window_manager.max_sublevel = level
    finally:
        _level_write = False


def _description(identifier, properties, fallback):
    from . import max_icons
    return max_icons.tooltip(bpy.context, fallback, identifier, **properties)


def _notice(text):
    from . import max_status
    max_status.notify(text)


def _object_mode(context):
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def _owner(context):
    from . import symmetry
    obj = symmetry.owner(context)
    symmetry.leave(context)
    return obj or context.active_object


class MAX_OT_subobject(bpy.types.Operator):
    bl_idname = 'max.subobject'
    bl_label = 'Sub-Object Level'
    bl_description = 'Choose a component level. Choose it again to return to Object'
    bl_options = {'REGISTER', 'UNDO'}
    level: IntProperty(min=0, max=5)

    @classmethod
    def description(cls, context, properties):
        label = LEVEL_NAMES[properties.level]
        return _description(cls.bl_idname, {'level': properties.level}, label + '. Choose again to return to Object')

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        from . import mode_feedback
        kind = _active_tool(context)
        obj = _owner(context)
        level = 0 if self.level == current_level(context) else self.level
        cage_owner = obj.get('max_ffd_owner')
        if cage_owner and level == 0:
            from . import ffd
            _object_mode(context)
            owner = ffd.resolve_owner(obj)
            if owner:
                obj.select_set(False)
                owner.select_set(True)
                context.view_layer.objects.active = owner
            with _viewport(context):
                if kind == 'LINK':
                    bpy.ops.wm.tool_set_by_id(name='max.select_link')
                else:
                    mode_feedback.restore_tool(bpy.context, kind)
            sync_sublevel(context)
            return {'FINISHED'}
        with _viewport(context):
            if level == 0:
                _object_mode(bpy.context)
            elif obj.type == 'MESH':
                context.window_manager.max_cmd_tab = 'MODIFY'
                obj.max_stack_index = -1
                obj.max_feedback_expanded = True
                if context.mode != 'EDIT_MESH':
                    bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_mode(type='VERT' if level == 1 else 'EDGE' if level < 4 else 'FACE')
                context.window_manager.max_sublevel = level
                sublevel_changed(context.window_manager, bpy.context)
            elif obj.type in {'CURVE', 'SURFACE', 'FONT', 'LATTICE'}:
                context.window_manager.max_cmd_tab = 'MODIFY'
                if obj.mode != 'EDIT':
                    bpy.ops.object.mode_set(mode='EDIT')
                context.window_manager.max_sublevel = level
            else:
                self.report({'WARNING'}, 'This object has no editable component level')
                return {'CANCELLED'}
            if kind == 'LINK':
                bpy.ops.wm.tool_set_by_id(name='max.select_link')
            else:
                mode_feedback.restore_tool(bpy.context, kind)
        sync_sublevel(context)
        return {'FINISHED'}


class MAX_OT_set_view(bpy.types.Operator):
    bl_idname = 'max.set_view'
    bl_label = 'Set View'
    bl_description = 'Change the active viewport direction or projection'
    view: EnumProperty(items=_catalogue([(v, v.title()) for v in ('TOP', 'BOTTOM', 'FRONT', 'BACK', 'LEFT', 'RIGHT', 'PERSP', 'ORTHO', 'CAMERA')]))

    @classmethod
    def poll(cls, context):
        return has_view3d(context)

    def execute(self, context):
        with _viewport(context):
            if self.view in VIEW_ROTATIONS:
                bpy.ops.view3d.view_axis(type=self.view)
            elif self.view == 'CAMERA':
                if context.scene.camera is None:
                    self.report({'WARNING'}, 'Create or assign a camera before switching to Camera view')
                    return {'CANCELLED'}
                bpy.ops.view3d.view_camera()
            else:
                area, _ = find_view3d(bpy.context)
                area.spaces.active.region_3d.view_perspective = 'PERSP' if self.view == 'PERSP' else 'ORTHO'
        return {'FINISHED'}


class MAX_OT_zoom_extents(bpy.types.Operator):
    bl_idname = 'max.zoom_extents'
    bl_label = 'Zoom Extents Selected'
    bl_description = 'Frame the selection, or frame the scene when nothing is selected'

    @classmethod
    def poll(cls, context):
        return has_view3d(context)

    def execute(self, context):
        with _viewport(context):
            if context.selected_objects:
                bpy.ops.view3d.view_selected(use_all_regions=False)
            else:
                bpy.ops.view3d.view_all(center=False)
        return {'FINISHED'}


class MAX_OT_toggle(bpy.types.Operator):
    bl_idname = 'max.toggle'
    bl_label = 'Toggle'
    bl_description = 'Switch the requested viewport, snap or keying option'
    what: EnumProperty(items=_catalogue([(v, v.replace('_', ' ').title()) for v in (
        'WIREFRAME', 'EDGED_FACES', 'SEE_THROUGH', 'GRID', 'GIZMO', 'STATS',
        'SNAP', 'ANGLE_SNAP', 'PERCENT_SNAP', 'AUTOKEY', 'BACKFACE')]))

    @classmethod
    def description(cls, context, properties):
        return _description(cls.bl_idname, {'what': properties.what}, cls.bl_description)

    def execute(self, context):
        if self.what in {'SNAP', 'ANGLE_SNAP', 'PERCENT_SNAP'}:
            from . import snaps
            snaps.toggle(context, self.what)
        elif self.what == 'AUTOKEY':
            context.tool_settings.use_keyframe_insert_auto = not context.tool_settings.use_keyframe_insert_auto
        elif self.what == 'SEE_THROUGH':
            for obj in context.selected_objects:
                obj.show_in_front = not obj.show_in_front
        else:
            area, _ = find_view3d(context)
            if area is None:
                return {'CANCELLED'}
            space = area.spaces.active
            if self.what == 'WIREFRAME':
                space.shading.type = 'SOLID' if space.shading.type == 'WIREFRAME' else 'WIREFRAME'
            elif self.what == 'GIZMO':
                space.show_gizmo = not space.show_gizmo
            elif self.what == 'BACKFACE':
                space.shading.show_backface_culling = not space.shading.show_backface_culling
            else:
                field = {'GRID': 'show_floor', 'STATS': 'show_stats', 'EDGED_FACES': 'show_wireframes'}[self.what]
                setattr(space.overlay, field, not getattr(space.overlay, field))
            area.tag_redraw()
        return {'FINISHED'}


class MAX_OT_expert_mode(bpy.types.Operator):
    bl_idname = 'max.expert_mode'
    bl_label = 'Expert Mode'
    bl_description = 'Maximize the modeling viewport or restore its surrounding controls'

    def execute(self, context):
        with _viewport(context):
            bpy.ops.screen.screen_full_area(use_hide_panels=True)
        return {'FINISHED'}


class MAX_OT_select_all(bpy.types.Operator):
    bl_idname = 'max.select_all'
    bl_label = 'Select'
    bl_description = 'Select all, clear the selection or invert it at the current level'
    action: EnumProperty(items=_catalogue([(v, v.title()) for v in ('SELECT', 'DESELECT', 'INVERT')]))

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            bpy.ops.mesh.select_all(action=self.action)
        elif context.mode in {'EDIT_CURVE', 'EDIT_SURFACE'}:
            bpy.ops.curve.select_all(action=self.action)
        else:
            bpy.ops.object.select_all(action=self.action)
        return {'FINISHED'}


class MAX_OT_delete(bpy.types.Operator):
    bl_idname = 'max.delete'
    bl_label = 'Delete'
    bl_description = 'Delete selected objects or components using the Delete Isolated Vertices setting'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None or bool(context.selected_objects)

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            obj = context.active_object
            level = current_level(context)
            isolated = obj.max_poly.delete_isolated
            mode = mesh_select_mode(context)
            kind = 'VERT' if mode == 'VERT' else ('EDGE' if isolated else 'EDGE_FACE') if mode == 'EDGE' else ('FACE' if isolated else 'ONLY_FACE')
            bpy.ops.mesh.delete(type=kind)
            editable_poly.cleanup_isolated(context)
            context.window_manager.max_sublevel = level
        elif context.mode in {'EDIT_CURVE', 'EDIT_SURFACE'}:
            bpy.ops.curve.delete(type='VERT')
        else:
            bpy.ops.object.delete(use_global=False)
        return {'FINISHED'}


def _scene_items(self, context):
    _scene_item_cache[:] = [(o.name, o.name, '') for o in context.scene.objects] if context else []
    return _scene_item_cache


class MAX_OT_select_by_name(bpy.types.Operator):
    bl_idname = 'max.select_by_name'
    bl_label = 'Select From Scene'
    bl_description = 'Search the scene hierarchy and choose objects to select'
    obj: EnumProperty(items=_scene_items)

    def invoke(self, context, event):
        return bpy.ops.max.scene_selection_dialog('INVOKE_DEFAULT')

    def execute(self, context):
        from . import scene_explorer
        obj = context.scene.objects.get(self.obj)
        if obj is None:
            return {'CANCELLED'}
        scene_explorer.select_objects(context, [obj])
        return {'FINISHED'}


class MAX_OT_clone(bpy.types.Operator):
    bl_idname = 'max.clone'
    bl_label = 'Clone Options'
    bl_description = 'Clone through the shared Copy and Instance transaction'
    bl_options = {'REGISTER', 'UNDO'}
    mode: EnumProperty(items=_catalogue([('COPY', 'Copy'), ('INSTANCE', 'Instance')]))

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(context.selected_objects)

    def invoke(self, context, event):
        return bpy.ops.max.clone_dialog('INVOKE_DEFAULT', mode=self.mode)

    def execute(self, context):
        from . import max_dialogs
        max_dialogs.clone(context, mode=self.mode)
        return {'FINISHED'}


class MAX_OT_edit_poly(bpy.types.Operator):
    bl_idname = 'max.edit_poly'
    bl_label = 'Edit Poly'
    bl_description = 'Apply the chosen Editable Poly operation at the current level'
    bl_options = {'REGISTER', 'UNDO'}
    op: EnumProperty(items=EDIT_POLY_OPS)

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    @classmethod
    def description(cls, context, properties):
        return _description(cls.bl_idname, {'op': properties.op}, cls.bl_description)

    def invoke(self, context, event):
        from . import poly_caddies
        if event.shift and not getattr(event, 'ctrl', False) and not getattr(event, 'alt', False) and self.op in poly_caddies.SHIFT_ACTIONS:
            return bpy.ops.max.poly_settings('INVOKE_DEFAULT', action=self.op)
        return self.run(context, 'INVOKE_DEFAULT')

    def execute(self, context):
        return self.run(context, 'EXEC_DEFAULT')

    def run(self, context, how):
        result = editable_poly.run(self, context, how)
        if result is not None:
            return result
        if context.mode != 'EDIT_MESH':
            return {'CANCELLED'}
        ops = bpy.ops.mesh
        action = self.op
        if action in {'LOOP', 'RING'}:
            ops.loop_multi_select(ring=action == 'RING')
        elif action == 'SWIFT_LOOP':
            with _viewport(context):
                return bpy.ops.max.swift_loop('INVOKE_DEFAULT')
        elif action in {'REMOVE', 'REMOVE_WITH_VERTS'}:
            mode = mesh_select_mode(context)
            if mode == 'VERT':
                ops.dissolve_verts(use_face_split=False, use_boundary_tear=False)
            elif mode == 'EDGE':
                ops.dissolve_edges(use_verts=action == 'REMOVE_WITH_VERTS')
            else:
                ops.dissolve_faces(use_verts=action == 'REMOVE_WITH_VERTS')
            editable_poly.cleanup_isolated(context)
        elif action == 'CAP':
            ops.edge_face_add()
        elif action == 'FLIP':
            ops.flip_normals()
        elif action == 'BREAK':
            ops.split()
        elif action == 'COLLAPSE':
            ops.merge(type='COLLAPSE')
        elif action == 'DETACH':
            ops.separate(type='SELECTED')
        elif action in {'HIDE_SEL', 'HIDE_UNSEL'}:
            ops.hide(unselected=action == 'HIDE_UNSEL')
        elif action == 'UNHIDE':
            ops.reveal()
        elif action in {'GROW', 'SHRINK'}:
            (ops.select_more if action == 'GROW' else ops.select_less)()
        elif action == 'OPEN_EDGES':
            ops.select_all(action='DESELECT')
            ops.select_non_manifold(extend=False, use_wire=False, use_boundary=True,
                                   use_multi_face=False, use_non_contiguous=False, use_verts=False)
        else:
            self.report({'WARNING'}, f'{dict((a, b) for a, b, _ in EDIT_POLY_OPS).get(action, action)} has no supported route at this level')
            return {'CANCELLED'}
        return {'FINISHED'}


def _pivot_world(obj):
    from . import poly_tools, loft
    if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT'}:
        return False
    delta = obj.matrix_world.inverted_safe() @ Vector((0, 0, 0))
    # Editable Text retains its local text plane. The compensation supports its XY origin.
    if obj.type == 'FONT':
        delta.z = 0
    children = {child: child.matrix_world.copy() for child in obj.children}
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    if getattr(obj, 'max_loft', None) and obj.max_loft.enabled:
        loft.offset_origin(obj, delta)
    elif obj.type == 'FONT':
        poly_tools._offset_font_geometry(obj, delta)
    else:
        obj.data.transform(Matrix.Translation(-delta), shape_keys=True)
    obj.matrix_world = obj.matrix_world @ Matrix.Translation(delta)
    if obj.type == 'MESH' and obj.max_prim.kind:
        obj['max_pivot_offset'] = list(Vector(obj.get('max_pivot_offset', (0, 0, 0))) - delta)
    for child, world in children.items():
        child.matrix_world = world
    obj.data.update_tag()
    return True


class MAX_OT_object_cmd(bpy.types.Operator):
    bl_idname = 'max.object_cmd'
    bl_label = 'Object Command'
    bl_description = 'Apply the chosen object operation to the selection'
    bl_options = {'REGISTER', 'UNDO'}
    cmd: EnumProperty(items=OBJECT_CMDS)

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects) or cls._global(context)

    @staticmethod
    def _global(context):
        return bool(context.scene.objects)

    @classmethod
    def description(cls, context, properties):
        return _description(cls.bl_idname, {'cmd': properties.cmd}, cls.bl_description)

    def invoke(self, context, event):
        if self.cmd in {'MIRROR', 'ALIGN'}:
            return getattr(bpy.ops.max, self.cmd.lower() + '_dialog')('INVOKE_DEFAULT')
        return self.execute(context)

    def execute(self, context):
        from . import freezing, poly_tools, scene_explorer, symmetry
        _owner(context)
        token = self.cmd
        if token == 'LINK':
            with _viewport(context):
                bpy.ops.wm.tool_set_by_id(name='max.select_link')
            return {'FINISHED'}
        if token in {'UNHIDE', 'UNFREEZE'}:
            targets = list(context.scene.objects)
        elif token == 'HIDE_UNSEL':
            targets = [o for o in context.scene.objects if not o.select_get()]
        else:
            targets = list(context.selected_objects)
        if not targets:
            self.report({'WARNING'}, 'Select an object first')
            return {'CANCELLED'}
        _object_mode(context)
        if token.startswith('CONVERT_'):
            bpy.ops.object.convert(target='MESH' if token == 'CONVERT_POLY' else 'CURVE')
            for converted in context.selected_objects:
                converted.max_prim.kind = ''
                converted.display_type = 'TEXTURED'
            poly_tools.bake_converted_text_pivots(context.selected_objects)
            symmetry.reconcile()
        elif token == 'RESET_XFORM':
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        elif token == 'CENTER_PIVOT':
            for target in targets:
                poly_tools.move_pivot(target, 'CENTER')
        elif token == 'PIVOT_TO_WORLD':
            for target in targets:
                _pivot_world(target)
        elif token == 'OBJECT_TO_PIVOT':
            for target in targets:
                center = sum((Vector(v) for v in target.bound_box), Vector()) / 8
                if target.data and hasattr(target.data, 'transform'):
                    if target.data.users > 1:
                        target.data = target.data.copy()
                    target.data.transform(Matrix.Translation(-center), shape_keys=True)
        elif token in {'HIDE_SEL', 'HIDE_UNSEL', 'UNHIDE'}:
            scene_explorer.set_hidden(context, targets, token != 'UNHIDE')
        elif token in {'FREEZE', 'UNFREEZE'}:
            for target in targets:
                (freezing.freeze if token == 'FREEZE' else freezing.unfreeze)(target, context.scene)
        elif token in {'DISPLAY_BOX', 'SEE_THROUGH', 'EDGES_ONLY'}:
            for target in targets:
                if token == 'DISPLAY_BOX':
                    target.display_type = 'TEXTURED' if target.display_type == 'BOUNDS' else 'BOUNDS'
                elif token == 'SEE_THROUGH':
                    target.show_in_front = not target.show_in_front
                else:
                    target.show_wire = not target.show_wire
        elif token == 'UNLINK':
            scene_explorer.reparent(context, targets)
        elif token == 'ATTACH':
            bpy.ops.object.join()
        elif token in {'MIRROR', 'ALIGN'}:
            return getattr(bpy.ops.max, token.lower() + '_dialog')('INVOKE_DEFAULT')
        elif token == 'ISOLATE':
            with _viewport(context):
                bpy.ops.view3d.localview(frame_selected=True)
        return {'FINISHED'}


class MAX_OT_camera_from_view(bpy.types.Operator):
    bl_idname = 'max.camera_from_view'
    bl_label = 'Create Camera From View'
    bl_description = 'Create a camera with the active viewport position and lens'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return has_view3d(context)

    def execute(self, context):
        area, _ = find_view3d(context)
        space = area.spaces.active
        camera = bpy.data.cameras.new(max_name('Camera'))
        obj = bpy.data.objects.new(camera.name, camera)
        context.collection.objects.link(obj)
        obj.matrix_world = space.region_3d.view_matrix.inverted_safe()
        camera.lens = space.lens
        context.scene.camera = obj
        with _viewport(context):
            bpy.ops.view3d.view_camera()
        return {'FINISHED'}


class MAX_OT_open_editor(bpy.types.Operator):
    bl_idname = 'max.open_editor'
    bl_label = 'Open Editor'
    bl_description = 'Open the named editor in its own window'
    editor: EnumProperty(items=_catalogue([(key, value[2]) for key, value in EDITORS.items()]))

    @classmethod
    def description(cls, context, properties):
        return _description(cls.bl_idname, {'editor': properties.editor}, cls.bl_description)

    def execute(self, context):
        from . import max_editor_windows
        if self.editor == 'MATERIAL':
            return {'FINISHED'} if open_material_compat(context) else {'CANCELLED'}
        window = max_editor_windows.open_editor(context, self.editor)
        if window is None:
            self.report({'WARNING'}, 'This editor needs an interactive window')
            return {'CANCELLED'}
        return {'FINISHED'}


class MAX_OT_transform_typein(bpy.types.Operator):
    bl_idname = 'max.transform_typein'
    bl_label = 'Transform Type-In'
    bl_description = 'Enter absolute or offset coordinates for the current transform'
    bl_options = {'REGISTER', 'UNDO'}
    absolute_move: FloatVectorProperty(name='Absolute: World', size=3, subtype='TRANSLATION', unit='LENGTH')
    offset_move: FloatVectorProperty(name='Offset: World', size=3, subtype='TRANSLATION', unit='LENGTH')
    absolute_scale: FloatVectorProperty(name='Absolute (%)', size=3, default=(100, 100, 100))
    offset_scale: FloatVectorProperty(name='Offset (%)', size=3, default=(100, 100, 100))
    offset: BoolProperty(name='Offset', default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        from . import max_rotate
        live = {window.as_pointer() for window in context.window_manager.windows}
        return bool(context.active_object or max_rotate._typein_windows.intersection(live))

    def invoke(self, context, event):
        from . import max_rotate
        live = {window.as_pointer() for window in context.window_manager.windows}
        if _active_tool(context) == 'ROTATE' or max_rotate._typein_windows.intersection(live):
            return bpy.ops.max.rotate_typein('INVOKE_DEFAULT')
        return bpy.ops.max.typein_dialog('INVOKE_DEFAULT', group='OFFSET' if self.offset else 'ABSOLUTE')

    def draw(self, context):
        from . import max_widgets, max_rotate
        kind, absolute, _ = read_transform(context, False)
        max_rotate.draw_managers(self.layout, context)
        row = self.layout.row()
        for use_offset, label in ((False, 'Absolute'), (True, 'Offset')):
            col = row.column(align=True)
            col.enabled = use_offset or absolute is not None
            col.label(text=label)
            prop = ('offset_' if use_offset else 'absolute_') + ('scale' if kind == 'SCALE' else 'move')
            for index, axis in enumerate('XYZ'):
                max_widgets.spinner(col, self, prop, axis, index=index)
        self.layout.prop(self, 'offset', text='Apply Offset values')

    def execute(self, context):
        if _active_tool(context) == 'ROTATE':
            return bpy.ops.max.rotate_typein('INVOKE_DEFAULT')
        field = ('offset_' if self.offset else 'absolute_') + ('scale' if _active_tool(context) == 'SCALE' else 'move')
        return {'FINISHED'} if write_transform(context, getattr(self, field), self.offset) else {'CANCELLED'}


class MAX_OT_add_modifier(bpy.types.Operator):
    bl_idname = 'max.add_modifier'
    bl_label = 'Add Modifier'
    bl_description = 'Add the selected supported modifier to the active object'
    bl_options = {'REGISTER', 'UNDO'}
    kind: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        from . import gn_mods, poly_tools, symmetry
        obj = _owner(context)
        _object_mode(context)
        token, _, display_name = self.kind.partition('|')
        kind, _, variant = token.partition(':')
        if kind == 'SYMMETRY':
            if obj.type != 'MESH':
                self.report({'WARNING'}, 'Symmetry requires a mesh')
                return {'CANCELLED'}
            mod = symmetry.add(obj)
        elif kind == 'EDIT_POLY':
            return bpy.ops.max.subobject(level=4)
        elif kind == 'GN':
            mod = gn_mods.add(obj, variant.title())
        elif kind in {'TURBOSMOOTH', 'LATTICE', 'UNWRAP', 'EXTRUDE_SHAPE', 'SWEEP'}:
            if kind == 'TURBOSMOOTH':
                from . import turbosmooth
                mod = turbosmooth.add(obj)
            elif kind == 'LATTICE':
                from . import ffd
                mod = ffd.add(obj, points=int(variant or 4))
            elif kind == 'UNWRAP':
                self.report({'WARNING'}, 'Unwrap UVW requires the UV editing workflow, which is not installed')
                return {'CANCELLED'}
            if kind == 'EXTRUDE_SHAPE' and obj.type == 'CURVE':
                obj.data.extrude = .1
                return {'FINISHED'}
            if kind == 'SWEEP' and obj.type == 'CURVE':
                obj.data.bevel_depth = .1
                return {'FINISHED'}
            elif kind not in {'TURBOSMOOTH', 'LATTICE'}:
                self.report({'WARNING'}, 'This modifier requires a spline')
                return {'CANCELLED'}
        else:
            label = display_name or _modifier_label(token)
            try:
                mod = obj.modifiers.new(label, kind)
            except (RuntimeError, TypeError) as exc:
                self.report({'WARNING'}, str(exc))
                return {'CANCELLED'}
            if kind == 'SIMPLE_DEFORM':
                mod.deform_method = variant or 'BEND'
            elif kind == 'SUBSURF' and variant == 'SIMPLE':
                mod.subdivision_type = 'SIMPLE'
            elif kind == 'DECIMATE' and variant == 'PLANAR':
                mod.decimate_type = 'DISSOLVE'
            elif kind == 'REMESH' and variant == 'QUAD':
                mod.mode = 'SHARP'
            elif kind == 'SHRINKWRAP' and variant == 'PROJECT':
                mod.wrap_method = 'PROJECT'
            elif kind == 'WAVE' and variant == 'RIPPLE':
                mod.use_cyclic = True
        if mod is None:
            self.report({'WARNING'}, 'This modifier is unavailable for the selected object')
            return {'CANCELLED'}
        if display_name:
            mod.name = display_name
        obj.modifiers.active = mod
        for internal in obj.modifiers:
            if poly_tools.is_font_pivot(internal):
                poly_tools._protect_font_pivot(obj, internal)
        context.window_manager.max_cmd_tab = 'MODIFY'
        return {'FINISHED'}


def _modifier_label(kind):
    from . import ui_menus
    return next((label for _, entries in ui_menus.MODIFIER_LIST for token, label in entries if token == kind), kind.title())


def _effective_points(context):
    if context.mode == 'EDIT_MESH':
        return [obj.matrix_world @ vert.co for obj in context.objects_in_mode_unique_data
                if obj.type == 'MESH' for vert in bmesh.from_edit_mesh(obj.data).verts
                if vert.select and not vert.hide]
    return [obj.matrix_world.translation.copy() for obj in context.selected_objects]


def read_transform(context, offset=False):
    """Read supported coordinates from the same basis used by the shared tools."""
    from . import max_rotate, max_status
    kind = _active_tool(context)
    kind = kind if kind in {'MOVE', 'ROTATE', 'SCALE'} else 'MOVE'
    unit = {'MOVE': 'LENGTH', 'ROTATE': 'ROTATION', 'SCALE': 'PERCENT'}[kind]
    points = _effective_points(context)
    if not points or context.active_object is None:
        return kind, None, unit
    if offset:
        actual = _live_transform(context, kind)
        if actual is not None:
            return kind, actual, unit
        live = max_status._live.get(context.window.as_pointer() if context.window else 0)
        return kind, live[1] if live and live[0] == kind else None, unit
    if kind == 'MOVE':
        point = sum(points, Vector()) / len(points)
        basis = max_rotate.reference_basis(context, operation='MOVE')
        origin = max_rotate._coordinate_center(context, context.active_object, 'MOVE')
        return kind, tuple(basis.inverted_safe() @ (point - origin)), unit
    if context.mode != 'OBJECT' or len(context.selected_objects) != 1:
        return kind, None, unit
    if kind == 'ROTATE':
        return kind, tuple(max_rotate.typein_values(context)), unit
    basis = max_rotate.reference_basis(context, operation='SCALE')
    matrix = basis.inverted_safe() @ context.active_object.matrix_world.to_3x3()
    # A rotated/sheared stretch has no three independent absolute scale fields
    # in this frame. Offset scaling still uses the chosen reference axes.
    if any(abs(matrix[row][column]) > 1e-6 for row in range(3) for column in range(3) if row != column):
        return kind, None, unit
    return kind, tuple(matrix[i][i] * 100 for i in range(3)), unit


def _live_transform(context, kind):
    """Observe the existing gizmo owner. No timer or second transform is started."""
    from . import max_gizmos, max_rotate
    for operation in tuple(max_gizmos._active.values()):
        owner = getattr(operation, '_owner_context', None)
        if not owner or owner[0] != context.window or operation.operation != kind:
            continue
        if kind == 'ROTATE':
            return tuple(operation.angle_data)
        if kind == 'SCALE':
            applied = operation.orientation.inverted_safe() @ getattr(operation, 'display_basis', operation.orientation)
            return tuple(applied[i][i] * 100 for i in range(3))
        differences = []
        for obj, matrix in getattr(operation, 'matrices', ()):
            differences.append(obj.matrix_world.translation - matrix.translation)
        for obj, saved in getattr(operation, 'meshes', ()):
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            differences.extend(obj.matrix_world.to_3x3() @ (bm.verts[index].co - point) for index, point in saved)
        if differences:
            delta = sum(differences, Vector()) / len(differences)
            return tuple(max_rotate.reference_basis(context, operation='MOVE').inverted_safe() @ delta)
    return None


def write_transform(context, values, offset=False):
    """Numerical entry shares constraint projection and transform centres."""
    from . import max_rotate, poly_constraints
    kind, absolute, _ = read_transform(context, False)
    if not _effective_points(context) or (not offset and absolute is None):
        return False
    if kind == 'ROTATE':
        session = max_rotate.typein_apply(context, values, absolute=not offset)
        session.finish()
        return True
    basis = max_rotate.reference_basis(context, operation=kind)
    if kind == 'MOVE':
        delta = basis @ (Vector(values) if offset else Vector(values) - Vector(absolute))
        if context.mode == 'EDIT_MESH':
            session = poly_constraints.MoveSession(context)
            session.apply(delta)
            session.finish()
        else:
            matrices = {obj: obj.matrix_world.copy() for obj in context.selected_objects}
            for obj, matrix in matrices.items():
                matrix.translation += delta
            _write_world(context, matrices)
        return True
    factors = Vector(values) / 100 if offset else Vector(
        values[i] / absolute[i] if abs(absolute[i]) > 1e-9 else 1 for i in range(3))
    stretch = basis @ Matrix.Diagonal(factors) @ basis.inverted_safe()
    pivots = _scale_pivots(context)
    if context.mode == 'EDIT_MESH':
        session = poly_constraints.MoveSession(context)
        targets = {}
        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'MESH':
                continue
            bm = bmesh.from_edit_mesh(obj.data)
            bm.verts.index_update()
            pivot = pivots.get(obj, max_rotate.transform_center(context, 'SCALE'))
            targets[obj] = {v.index: pivot + stretch @ (obj.matrix_world @ v.co - pivot)
                            for v in bm.verts if v.select and not v.hide}
        session.apply_targets(targets)
        session.finish()
    else:
        matrices = {}
        for obj in context.selected_objects:
            pivot = pivots.get(obj, max_rotate.transform_center(context, 'SCALE'))
            matrices[obj] = Matrix.Translation(pivot) @ stretch.to_4x4() @ Matrix.Translation(-pivot) @ obj.matrix_world
        _write_world(context, matrices)
    return True


def _write_world(context, matrices):
    def depth(obj):
        count = 0
        while obj.parent:
            obj = obj.parent
            count += 1
        return count
    for obj in sorted(matrices, key=depth):
        obj.matrix_world = matrices[obj]
        context.view_layer.update()


def _scale_pivots(context):
    from . import max_rotate
    mode = max_rotate.center_mode(context, 'SCALE')
    local = max_rotate.reference_name(context, 'SCALE') == 'LOCAL'
    objects = context.objects_in_mode_unique_data if context.mode == 'EDIT_MESH' else context.selected_objects
    result = {}
    for obj in objects:
        if mode == 'COORDINATE' and not local:
            pivot = max_rotate._coordinate_center(context, obj, 'SCALE')
        elif mode == 'PIVOT' or local:
            if context.mode == 'EDIT_MESH' and obj.type == 'MESH':
                points = [obj.matrix_world @ v.co for v in bmesh.from_edit_mesh(obj.data).verts if v.select and not v.hide]
                pivot = sum(points, Vector()) / len(points) if points else obj.matrix_world.translation.copy()
            else:
                pivot = obj.matrix_world.translation.copy()
        else:
            pivot = max_rotate.transform_center(context, 'SCALE')
        result[obj] = pivot
    return result


def open_material_compat(context):
    """Temporary Compact sidebar host. W2.E replaces only this adapter."""
    from . import mtl_editor
    if bpy.app.background or context.window is None:
        return None
    live = {w.as_pointer(): w for w in context.window_manager.windows}
    for key in list(_material_windows):
        if key in live:
            return live[key]
        _material_windows.pop(key)
    mtl_editor.ensure_slots(context.scene)
    state = mtl_editor.state(context)
    slot = state.slots[state.active]
    if slot.material is None:
        slot.material = (context.active_object.active_material if context.active_object else None) or mtl_editor.new_default_material(state.active)
    source = context.area or find_view3d(context)[0]
    if source is None:
        return None
    with context.temp_override(area=source):
        result = bpy.ops.screen.area_dupli('INVOKE_DEFAULT')
    added = [w for w in context.window_manager.windows if w.as_pointer() not in live]
    if result != {'FINISHED'} or len(added) != 1:
        return None
    window = added[0]
    area = max(window.screen.areas, key=lambda a: a.width * a.height)
    with context.temp_override(window=window, area=area):
        area.ui_type = 'ShaderNodeTree'
        area.spaces.active.show_region_ui = True
        area.spaces.active.show_region_toolbar = False
    _material_windows[window.as_pointer()] = window
    return window


def close_material_compat(*_):
    live = {w.as_pointer(): w for w in bpy.context.window_manager.windows}
    for key in list(_material_windows):
        window = live.get(key)
        if window:
            with bpy.context.temp_override(window=window):
                bpy.ops.wm.window_close()
    _material_windows.clear()


def _melt(context):
    from . import gn_mods
    obj = context.active_object
    return next((m for m in obj.modifiers if gn_mods.is_melt(m)), None) if obj else None


class MAX_OT_melt_preset(bpy.types.Operator):
    bl_idname = 'max.melt_preset'
    bl_label = 'Solidity Preset'
    bl_description = 'Set solidity on the active Melt modifier'
    bl_options = {'REGISTER', 'UNDO'}
    value: FloatProperty()

    def execute(self, context):
        from . import gn_mods
        mod = _melt(context)
        return {'FINISHED'} if mod and gn_mods.set_input(mod, 'Solidity', self.value) else {'CANCELLED'}


class MAX_OT_animate_melt(bpy.types.Operator):
    bl_idname = 'max.animate_melt'
    bl_label = 'Animate Melt'
    bl_description = 'Add start and end Amount keys to Melt, an optional Maxxed utility'
    bl_options = {'REGISTER', 'UNDO'}
    start: IntProperty(default=1)
    end: IntProperty(default=100)
    amount_from: FloatProperty(default=0, min=0, max=1, subtype='FACTOR')
    amount_to: FloatProperty(default=1, min=0, max=1, subtype='FACTOR')
    play: BoolProperty(default=True)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        from . import gn_mods
        mod = _melt(context)
        if mod is None or self.end <= self.start:
            self.report({'WARNING'}, 'Choose a Melt modifier and an end frame after the start')
            return {'CANCELLED'}
        for frame, value in ((self.start, self.amount_from), (self.end, self.amount_to)):
            gn_mods.set_input(mod, 'Amount', value)
            gn_mods.keyframe_input(mod, 'Amount', frame)
        if self.play and not bpy.app.background:
            bpy.ops.screen.animation_play()
        return {'FINISHED'}


class MAX_OT_key_melt(bpy.types.Operator):
    bl_idname = 'max.key_melt'
    bl_label = 'Key Melt Amount'
    bl_description = 'Insert a Melt Amount key at the current frame'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import gn_mods
        mod = _melt(context)
        if mod is None:
            return {'CANCELLED'}
        gn_mods.keyframe_input(mod, 'Amount', context.scene.frame_current)
        return {'FINISHED'}


class MAX_OT_modifier_set_active(bpy.types.Operator):
    bl_idname = 'max.modifier_set_active'
    bl_label = 'Select Modifier'
    bl_description = 'Leave component editing and select this entry in the modifier stack'
    name: StringProperty()

    def execute(self, context):
        from . import poly_tools
        obj = _owner(context)
        if obj is None:
            return {'CANCELLED'}
        mod = obj.modifiers.get(self.name)
        if mod and poly_tools.is_font_pivot(mod):
            self.report({'WARNING'}, 'Text origin compensation is internal')
            return {'CANCELLED'}
        _object_mode(context)
        if mod and not poly_tools.is_font_pivot(mod):
            obj.modifiers.active = mod
        elif not self.name:
            obj.modifiers.active = None
        context.window_manager.max_cmd_tab = 'MODIFY'
        sync_sublevel(context)
        return {'FINISHED'}


def quadview_op():
    return bpy.ops.screen.region_quadview


def unlock_region(region):
    for name in ('lock_rotation', 'show_sync_view', 'use_box_clip', 'use_box_quadview'):
        if hasattr(region, name):
            setattr(region, name, False)


def unlock_max_workspace_quads():
    workspace = bpy.data.workspaces.get(WS_NAME)
    if workspace:
        for screen in workspace.screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    for view in area.spaces.active.region_quadviews:
                        unlock_region(view)


def setup_quad_views(context, window, area):
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return
    with context.temp_override(window=window, area=area, region=region):
        if not area.spaces.active.region_quadviews:
            quadview_op()()
    from mathutils import Euler
    rotations = ('TOP', 'FRONT', 'LEFT')
    regions = sorted((r for r in area.regions if r.type == 'WINDOW'), key=lambda r: (-r.y, r.x))
    for index, region in enumerate(regions):
        view = region.data
        unlock_region(view)
        if index < 3:
            view.view_rotation = VIEW_ROTATIONS[rotations[index]]
            view.view_perspective = 'ORTHO'
        else:
            view.view_rotation = Euler((math.radians(65), 0, math.radians(-45))).to_quaternion()
            view.view_perspective = 'PERSP'


class MAX_OT_toggle_quad(bpy.types.Operator):
    bl_idname = 'max.toggle_quad'
    bl_label = 'Maximize Viewport Toggle'
    bl_description = 'Switch the modeling viewport between single and four-view layouts'

    def execute(self, context):
        area, _ = find_view3d(context)
        if area is None:
            return {'CANCELLED'}
        if area.spaces.active.region_quadviews:
            with _viewport(context):
                quadview_op()()
        else:
            setup_quad_views(context, context.window, area)
        return {'FINISHED'}


class MAX_OT_adaptive_degradation(bpy.types.Operator):
    bl_idname = 'max.adaptive_degradation'
    bl_label = 'Adaptive Degradation'
    bl_description = 'Toggle bounding-box display for the selection. Automatic Nitrous degradation is unavailable'

    def execute(self, context):
        _notice('Adaptive Degradation uses manual bounding-box display for the selection')
        return bpy.ops.max.object_cmd(cmd='DISPLAY_BOX')


class MAX_OT_set_key(bpy.types.Operator):
    bl_idname = 'max.set_key'
    bl_label = 'Set Key'
    bl_description = 'Insert position, rotation and scale keys for the selection at the current frame'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.selected_objects:
            return {'CANCELLED'}
        for obj in context.selected_objects:
            rotation = 'rotation_quaternion' if obj.rotation_mode == 'QUATERNION' else 'rotation_axis_angle' if obj.rotation_mode == 'AXIS_ANGLE' else 'rotation_euler'
            for path in ('location', rotation, 'scale'):
                obj.keyframe_insert(data_path=path, frame=context.scene.frame_current)
        return {'FINISHED'}


class MAX_OT_group(bpy.types.Operator):
    bl_idname = 'max.group'
    bl_label = 'Group'
    bl_description = 'Group objects under a group head, or dissolve the selected group without moving members'
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=_catalogue([('GROUP', 'Group'), ('UNGROUP', 'Ungroup')]))

    def execute(self, context):
        from . import scene_explorer
        targets = list(context.selected_objects)
        if not targets:
            return {'CANCELLED'}
        _object_mode(context)
        if self.action == 'GROUP':
            head = bpy.data.objects.new(max_name('Group'), None)
            context.collection.objects.link(head)
            head.empty_display_type = 'PLAIN_AXES'
            head['max_group_head'] = True
            head.location = sum((o.matrix_world.translation for o in targets), Vector()) / len(targets)
            context.view_layer.update()
            scene_explorer.reparent(context, targets, head)
            head.select_set(True)
            context.view_layer.objects.active = head
        else:
            groups = {o if o.get('max_group_head') else o.parent for o in targets}
            for head in groups:
                if head and head.get('max_group_head'):
                    scene_explorer.reparent(context, list(head.children), head.parent)
                    bpy.data.objects.remove(head, do_unlink=True)
        return {'FINISHED'}


class MAX_OT_set_workspace(bpy.types.Operator):
    bl_idname = 'max.set_workspace'
    bl_label = 'Workspace'
    bl_description = 'Activate the requested existing workspace'
    name: StringProperty()

    def execute(self, context):
        workspace = bpy.data.workspaces.get(self.name)
        if workspace is None or context.window is None:
            return {'CANCELLED'}
        context.window.workspace = workspace
        return {'FINISHED'}


def _explorer_layout(context):
    from . import max_editor_windows
    viewport, _ = find_view3d(context)
    if viewport is None:
        return
    # Dock ownership is transient. Loaded files do not acquire a second schema.
    for area in context.screen.areas:
        host = max_editor_windows._docked.get(area.as_pointer())
        if host:
            max_editor_windows._configure(host)
        elif area.type == 'OUTLINER' and area.x < viewport.x:
            max_editor_windows.attach_explorer(context, area)


def apply_layout(context, quad=False):
    if context.window is None:
        return
    window, scene = context.window, context.scene
    key = window.as_pointer()
    if key not in _layout_snapshot:
        _layout_snapshot[key] = (window, context.workspace, context.workspace.name)
    workspace = window.workspace
    if window.workspace.name != WS_NAME:
        workspace = bpy.data.workspaces.get(WS_NAME)
        if workspace is None:
            before = set(bpy.data.workspaces)
            bpy.ops.workspace.duplicate()
            workspace = next((w for w in bpy.data.workspaces if w not in before), None)
            if workspace is None:
                raise RuntimeError('Could not create the Maxxed workspace')
            workspace.name = WS_NAME
        window.workspace = workspace
    cancel_layout(window)
    phase = 0

    def construct():
        nonlocal phase
        from . import ui_menus, max_chrome, cursor_policy
        try:
            live = any(w.as_pointer() == key for w in bpy.context.window_manager.windows)
            if not ui_menus._installed or not live or window.workspace != workspace or window.scene != scene:
                _layout_jobs.pop(key, None)
                return None
            with bpy.context.temp_override(window=window):
                if phase == 0:
                    if _arrange_workspace(bpy.context):
                        phase = 1
                    return .1
                if phase == 1:
                    max_chrome.apply_layout(bpy.context, quad=quad)
                    phase = 2
                    return .1
                if quad:
                    area, _ = find_view3d(bpy.context)
                    if area:
                        setup_quad_views(bpy.context, window, area)
                cursor_policy.reset_scene(scene)
                cursor_policy.enforce()
                phase = 3
        except Exception:
            _layout_jobs.pop(key, None)
            raise
        finally:
            if phase == 3:
                _layout_jobs.pop(key, None)
        return None

    _layout_jobs[key] = construct
    bpy.app.timers.register(construct, first_interval=.1)


def cancel_layout(window=None):
    keys = [window.as_pointer()] if window else list(_layout_jobs)
    for key in keys:
        callback = _layout_jobs.pop(key, None)
        if callback and bpy.app.timers.is_registered(callback):
            bpy.app.timers.unregister(callback)


def _arrange_workspace(context):
    from . import max_editor_windows, max_chrome
    if bpy.app.background:
        return True
    window = context.window
    area, region = find_view3d(context)
    if area is None:
        return True
    if any(a.type == 'OUTLINER' and a.x < area.x for a in context.screen.areas):
        return True
    if any(a.as_pointer() in max_editor_windows._docked for a in context.screen.areas):
        return True
    # Close the factory right-hand editor column in the duplicated workspace.
    for other in tuple(window.screen.areas):
        if other.type in {'OUTLINER', 'PROPERTIES'}:
            with context.temp_override(window=window, area=other):
                bpy.ops.screen.area_close()
            # Closing an area invalidates the active screen context until redraw.
            return False
    viewports = [a for a in window.screen.areas if a.type == 'VIEW_3D' and not max_chrome.timeline_area(a)]
    if len(viewports) > 1:
        min(viewports, key=lambda a: a.x).type = 'OUTLINER'
        return True
    if region is None:
        return True
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.screen.area_split(direction='VERTICAL', factor=.18)
    return False


def restore_layout(context):
    from . import max_editor_windows
    cancel_layout()
    for window, workspace, name in list(_layout_snapshot.values()):
        try:
            workspace.name = name
            window.workspace = workspace
        except (ReferenceError, RuntimeError):
            continue
    _layout_snapshot.clear()
    for screen in bpy.data.screens:
        for area in screen.areas:
            max_editor_windows.detach_explorer(area)


class MAX_OT_apply(bpy.types.Operator):
    bl_idname = 'max.apply'
    bl_label = 'Apply 3ds Max Look'
    bl_description = 'Apply Maxxed appearance and a single Perspective workspace without changing scene units or timing'
    theme: BoolProperty(default=True)
    layout_: BoolProperty(default=True)
    quad: BoolProperty(default=False)

    def execute(self, context):
        from . import theme
        if self.theme:
            theme.apply(context)
        if self.layout_:
            apply_layout(context, quad=self.quad)
        return {'FINISHED'}


class MAX_OT_restore(bpy.types.Operator):
    bl_idname = 'max.restore'
    bl_label = 'Restore Blender Look'
    bl_description = 'Restore the workspace and appearance captured by Apply'

    def execute(self, context):
        from . import theme
        restore_layout(context)
        theme.restore(context)
        return {'FINISHED'}


class MAX_OT_block_cursor(bpy.types.Operator):
    bl_idname = 'max.block_cursor'
    bl_label = 'Block 3D Cursor'
    bl_description = 'Keep the protected snap gesture from placing the backend cursor'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.workspace is not None and context.workspace.name == WS_NAME

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)


classes = (
    MAX_OT_subobject, MAX_OT_set_view, MAX_OT_zoom_extents, MAX_OT_toggle,
    MAX_OT_expert_mode, MAX_OT_select_all, MAX_OT_delete, MAX_OT_select_by_name,
    MAX_OT_clone, MAX_OT_edit_poly, MAX_OT_object_cmd, MAX_OT_camera_from_view,
    MAX_OT_open_editor, MAX_OT_transform_typein, MAX_OT_add_modifier,
    MAX_OT_melt_preset, MAX_OT_animate_melt, MAX_OT_key_melt,
    MAX_OT_modifier_set_active, MAX_OT_toggle_quad, MAX_OT_adaptive_degradation,
    MAX_OT_set_key, MAX_OT_group, MAX_OT_set_workspace, MAX_OT_apply,
    MAX_OT_restore, MAX_OT_block_cursor,
)
