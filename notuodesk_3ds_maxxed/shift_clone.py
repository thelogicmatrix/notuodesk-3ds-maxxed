"""Shift-transform cloning, with Max's release-to-confirm dialogs."""

import math
import re

import bmesh
import bpy
from bpy_extras import view3d_utils
from bpy.props import EnumProperty, IntProperty, StringProperty
from bpy.types import Operator
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_point_line

from .operators import current_level, max_name


_pending = {}
_watchers = set()
_last = dict(mode='COPY', controller='COPY', copies=1, destination='ELEMENT')
_TOOLS = {'builtin.move': 'translate', 'builtin.rotate': 'rotate', 'builtin.scale': 'resize'}


def clone_name(name):
    return max_name(re.sub(r'\d+$', '', name.split('.')[0]) or 'Object')


def _named(name):
    return name if name and name not in bpy.data.objects else clone_name(name or 'Object')


def _copy_action(ob):
    if ob.animation_data and ob.animation_data.action:
        ob.animation_data.action = ob.animation_data.action.copy()


def _instance_controller(ob, source):
    """Blender has no controller objects, so link child channels with drivers."""
    for path in ('location', 'rotation_euler', 'rotation_quaternion', 'scale'):
        for i in range(len(getattr(ob, path))):
            ob.driver_remove(path, i)
            driver = ob.driver_add(path, i).driver
            var = driver.variables.new()
            var.name = 'source'
            var.type = 'SINGLE_PROP'
            var.targets[0].id = source
            var.targets[0].data_path = f'{path}[{i}]'
            driver.expression = 'source'


class ObjectClone:
    """Keep originals intact while a linked preview follows Blender's gizmo."""

    def __init__(self, context):
        self.context = context
        self.originals = list(context.selected_objects)
        self.active = context.view_layer.objects.active
        self.matrices = [o.matrix_world.copy() for o in self.originals]
        self.preview = self._batch()
        self.has_hierarchy = any(o.parent in self.originals for o in self.originals)
        self.closed = False

    def _batch(self):
        copies = []
        for src in self.originals:
            ob = src.copy()
            _copy_action(ob)
            ob.name = clone_name(src.name)
            for collection in src.users_collection:
                collection.objects.link(ob)
            copies.append(ob)
        mapping = dict(zip(self.originals, copies))
        for src, ob in zip(self.originals, copies):
            if src.parent in mapping:
                ob.parent = mapping[src.parent]
        for src in self.context.selected_objects:
            src.select_set(False)
        for ob, matrix in zip(copies, self.matrices):
            ob.matrix_world = matrix
            ob.select_set(True)
        self.context.view_layer.objects.active = mapping.get(self.active, copies[0])
        self.context.view_layer.update()
        return copies

    def changed(self):
        return any(any(abs(a - b) > 1e-6 for row1, row2 in zip(ob.matrix_world, matrix)
                       for a, b in zip(row1, row2))
                   for ob, matrix in zip(self.preview, self.matrices))

    def finish(self, mode, count, name, controller):
        self.context.view_layer.update()
        delta = [o.matrix_world @ m.inverted_safe() for o, m in zip(self.preview, self.matrices)]
        all_copies = []
        previous = self.matrices
        for i in range(count):
            next_name = clone_name(name) if i and name else ''
            batch = self.preview if i == 0 else self._batch()
            # Rename the active object's first clone. Other objects keep their bases.
            if i == 0 and name:
                ob = batch[self.originals.index(self.active)] if self.active in self.originals else batch[0]
                if ob.name != name:
                    ob.name = _named(name)
            elif i and name:
                ob = batch[self.originals.index(self.active)] if self.active in self.originals else batch[0]
                ob.name = next_name
            for src, ob in zip(self.originals, batch):
                # Apply in world space after parenting, in parent-first order below.
                if mode == 'COPY' and src.data:
                    ob.data = src.data.copy()
                    _copy_action(ob.data)
            previous = [step @ matrix for matrix, step in zip(previous, delta)]
            targets = dict(zip(batch, previous))
            def depth(ob):
                result = 0
                while ob.parent:
                    result += 1
                    ob = ob.parent
                return result
            for ob in sorted(batch, key=depth):
                self.context.view_layer.update()
                ob.matrix_world = targets[ob]
            for src, ob in zip(self.originals, batch):
                if controller == 'INSTANCE' and src.parent in self.originals:
                    _instance_controller(ob, src)
            all_copies.extend(batch)
        self.context.view_layer.update()
        self.closed = True
        return all_copies

    def cancel(self):
        if self.closed:
            return
        for ob in self.preview:
            bpy.data.objects.remove(ob, do_unlink=True)
        for ob in self.originals:
            ob.select_set(True)
        self.context.view_layer.objects.active = self.active
        self.closed = True


class MeshClone:
    """Duplicate vertices/faces or extend open edges, without moving the source."""

    def __init__(self, context, level, obj=None):
        self.obj = obj or context.edit_object
        self.bm = bmesh.from_edit_mesh(self.obj.data)
        self.level = level
        self.closed = False
        self.selected = [[e for e in seq if e.select] for seq in
                         (self.bm.verts, self.bm.edges, self.bm.faces)]
        self.history = list(self.bm.select_history)
        if level in {2, 3}:
            edges = [e for e in self.selected[1] if e.is_boundary or e.is_wire]
            geom = bmesh.ops.extrude_edge_only(self.bm, edges=edges)['geom'] if edges else []
        elif level in {4, 5}:
            faces = self.selected[2]
            geom = bmesh.ops.duplicate(self.bm, geom=faces)['geom'] if faces else []
        else:
            verts = self.selected[0]
            geom = bmesh.ops.duplicate(self.bm, geom=verts)['geom'] if verts else []
        self.new_verts = [e for e in geom if isinstance(e, bmesh.types.BMVert)]
        self.new_faces = [e for e in geom if isinstance(e, bmesh.types.BMFace)]
        for seq in (self.bm.faces, self.bm.edges, self.bm.verts):
            for elem in seq:
                elem.select_set(False)
        if level in {2, 3}:
            verts = set(self.new_verts)
            for e in self.bm.edges:
                if all(v in verts for v in e.verts):
                    e.select_set(True)
        elif level in {4, 5}:
            for f in self.new_faces:
                f.select_set(True)
        else:
            for v in self.new_verts:
                v.select_set(True)
        self.start = [v.co.copy() for v in self.new_verts]
        self.update()

    def update(self):
        self.bm.normal_update()
        bmesh.update_edit_mesh(self.obj.data, loop_triangles=True, destructive=True)

    def changed(self):
        return any((v.co - start).length > 1e-6 for v, start in zip(self.new_verts, self.start))

    def finish(self, destination, name):
        if destination == 'OBJECT':
            self.bm.verts.index_update()
            keep = {v.index for v in self.new_verts}
            part = self.bm.copy()
            bmesh.ops.delete(part, geom=[v for v in part.verts if v.index not in keep], context='VERTS')
            mesh = bpy.data.meshes.new(name or 'Object')
            part.to_mesh(mesh)
            part.free()
            for mat in self.obj.data.materials:
                mesh.materials.append(mat)
            ob = bpy.data.objects.new(_named(name), mesh)
            ob.matrix_world = self.obj.matrix_world.copy()
            for collection in self.obj.users_collection:
                collection.objects.link(ob)
            self._remove()
        self.closed = True
        self.update()

    def _remove(self):
        bmesh.ops.delete(self.bm, geom=self.new_verts, context='VERTS')
        for seq in (self.bm.faces, self.bm.edges, self.bm.verts):
            for elem in seq:
                elem.select_set(False)
        for selection in self.selected:
            for elem in selection:
                elem.select_set(True)
        self.bm.select_history.clear()
        for elem in self.history:
            self.bm.select_history.add(elem)

    def cancel(self):
        if not self.closed:
            self._remove()
            self.update()
            self.closed = True


class MeshClones:
    def __init__(self, context):
        self.level = current_level(context)
        self.parts = [MeshClone(context, self.level, ob) for ob in context.objects_in_mode_unique_data]
        self.originals = [p.obj for p in self.parts]
        self.active = context.edit_object

    def changed(self):
        return any(p.changed() for p in self.parts)

    def cancel(self):
        for p in self.parts:
            p.cancel()

    def finish(self, destination, name):
        for i, p in enumerate(self.parts):
            p.finish(destination, name if i == 0 else clone_name(name))


def _radio(layout, data, prop, value, text):
    row = layout.row(align=True)
    row.emboss = 'NONE'
    row.alignment = 'LEFT'
    row.prop_enum(data, prop, value, text=text, icon=(
        'RADIOBUT_ON' if getattr(data, prop) == value else 'RADIOBUT_OFF'))


def _over_selection(context, event, tx):
    """A background drag must keep its usual selection behavior."""
    point = Vector((event.mouse_region_x, event.mouse_region_y))
    region, rv = context.region, context.region_data
    origin = view3d_utils.region_2d_to_origin_3d(region, rv, point)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv, point)
    if isinstance(tx, ObjectClone):
        hit, _, _, _, ob, _ = context.scene.ray_cast(context.evaluated_depsgraph_get(), origin, direction)
        return hit and ob.original in tx.originals + tx.preview
    for part in tx.parts:
        inv = part.obj.matrix_world.inverted_safe()
        if part.level in {4, 5}:
            part.bm.faces.ensure_lookup_table()
            _, _, index, _ = BVHTree.FromBMesh(part.bm).ray_cast(inv @ origin, inv.to_3x3() @ direction)
            if index is not None and part.bm.faces[index] in part.new_faces:
                return True
        else:
            def screen(v):
                return view3d_utils.location_3d_to_region_2d(region, rv, part.obj.matrix_world @ v.co)
            if part.level == 1:
                if any((p - point).length <= 12 for p in map(screen, part.new_verts) if p is not None):
                    return True
            else:
                for edge in part.selected[1]:
                    a, b = (screen(v) for v in edge.verts)
                    if a is None or b is None or (b - a).length < 1e-6:
                        continue
                    near, factor = intersect_point_line(point, a, b)
                    if 0 <= factor <= 1 and (point - near).length <= 12:
                        return True
    return False


def _gizmo_hit(context, event, tx, tool):
    """Pick the displayed handle without Blender's Shift-axis inversion."""
    if not context.space_data.show_gizmo or not context.space_data.show_gizmo_tool:
        return None
    if isinstance(tx, ObjectClone):
        points = [m.translation for m in tx.matrices]
    else:
        points = [p.obj.matrix_world @ co for p in tx.parts for co in p.start]
    if not points:
        return None
    pivot = context.scene.tool_settings.transform_pivot_point
    center = sum(points, Vector()) / len(points)
    if pivot == 'CURSOR':
        center = context.scene.cursor.location.copy()
    elif pivot == 'ACTIVE_ELEMENT':
        center = tx.active.matrix_world.translation.copy()
        if isinstance(tx, MeshClones):
            active = bmesh.from_edit_mesh(tx.active.data).select_history.active
            if active:
                co = active.co if isinstance(active, bmesh.types.BMVert) else (
                    active.calc_center_median() if isinstance(active, bmesh.types.BMFace) else
                    sum((v.co for v in active.verts), Vector()) / 2)
                center = tx.active.matrix_world @ co
    elif pivot == 'BOUNDING_BOX_CENTER':
        center = Vector([(min(p[i] for p in points) + max(p[i] for p in points)) / 2 for i in range(3)])
    region, rv = context.region, context.region_data
    project = lambda p: view3d_utils.location_3d_to_region_2d(region, rv, p)
    screen = project(center)
    if screen is None:
        return None
    point = Vector((event.mouse_region_x, event.mouse_region_y))
    radius = context.preferences.view.gizmo_size * context.preferences.system.ui_scale
    if (point - screen).length < 12:
        return (False, False, False)
    orientation = context.scene.transform_orientation_slots[0]
    if orientation.type == 'CUSTOM' and orientation.custom_orientation:
        matrix = orientation.custom_orientation.matrix.copy()
    elif orientation.type in {'LOCAL', 'GIMBAL', 'NORMAL'}:
        matrix = tx.active.matrix_world.to_3x3().normalized()
        if orientation.type == 'NORMAL' and isinstance(tx, MeshClones):
            normals = [f.normal for p in tx.parts for f in p.new_faces]
            if normals:
                normal = matrix @ sum(normals, Vector()).normalized()
                matrix = normal.to_track_quat('Z', 'Y').to_matrix()
    elif orientation.type == 'VIEW':
        matrix = rv.view_rotation.to_matrix()
    elif orientation.type == 'CURSOR':
        matrix = context.scene.cursor.matrix.to_3x3()
    else:
        matrix = Matrix.Identity(3)
    at = view3d_utils.region_2d_to_location_3d(region, rv, screen + Vector((radius, 0)), center)
    size = (at - center).length
    axes = [matrix.col[i].normalized() for i in range(3)]
    if tool == 'builtin.rotate':
        candidates = []
        for i in range(3):
            a, b = axes[(i + 1) % 3], axes[(i + 2) % 3]
            pa, pb = project(center + a * size), project(center + b * size)
            if pa is None or pb is None or abs((pa-screen).cross(pb-screen)) < radius * radius * .1:
                continue
            distance = min((point - p).length for p in (
                project(center + size * (a * math.cos(t * math.tau / 96) + b * math.sin(t * math.tau / 96)))
                for t in range(96)) if p is not None)
            candidates.append((distance, tuple(j == i for j in range(3))))
        if candidates:
            distance, axis = min(candidates)
            if distance <= 14:
                return axis
        return None
    ends = [project(center + axis * size) for axis in axes]
    # Plane squares lie between their two axis shafts.
    for i, j in ((0, 1), (0, 2), (1, 2)):
        if ends[i] is None or ends[j] is None:
            continue
        a, b = ends[i] - screen, ends[j] - screen
        det = a.cross(b)
        if abs(det) < radius * radius * .05:
            continue
        offset = point - screen
        u, v = offset.cross(b) / det, a.cross(offset) / det
        if .12 <= u <= .45 and .12 <= v <= .45:
            return tuple(k in {i, j} for k in range(3))
    candidates = []
    for i, end in enumerate(ends):
        if end is None or (end - screen).length < 10:
            continue
        near, factor = intersect_point_line(point, screen, end)
        if .15 <= factor <= 1.3:
            candidates.append(((near - point).length, tuple(j == i for j in range(3))))
    if candidates:
        distance, axis = min(candidates)
        if distance <= 12:
            return axis
    return None


class MAX_OT_shift_clone_options(Operator):
    """Choose how to clone the transformed objects"""
    bl_idname = 'max.shift_clone_options'
    bl_label = 'Clone Options'
    bl_options = {'UNDO', 'INTERNAL'}

    token: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    mode: EnumProperty(name='Object', items=[('COPY', 'Copy', ''), ('INSTANCE', 'Instance', ''),
                                           ('REFERENCE', 'Reference', '')])
    controller: EnumProperty(name='Controller', items=[('COPY', 'Copy', ''), ('INSTANCE', 'Instance', '')])
    copies: IntProperty(name='Number of Copies', default=1, min=1, max=10000)
    name: StringProperty(name='Name')

    def invoke(self, context, event):
        tx = _pending.get(self.token)
        if tx is None:
            return {'CANCELLED'}
        self.mode, self.controller, self.copies = _last['mode'], _last['controller'], _last['copies']
        ob = tx.preview[tx.originals.index(tx.active)] if tx.active in tx.originals else tx.preview[0]
        self.name = ob.name
        return context.window_manager.invoke_props_dialog(self, width=260)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = False
        row = layout.row()
        col = row.box().column(align=True)
        col.label(text='Object')
        for mode, label in (('COPY', 'Copy'), ('INSTANCE', 'Instance'), ('REFERENCE', 'Reference')):
            _radio(col, self, 'mode', mode, label)
        col = row.box().column(align=True)
        col.label(text='Controller')
        tx = _pending.get(self.token)
        col.enabled = bool(tx and tx.has_hierarchy)
        _radio(col, self, 'controller', 'COPY', 'Copy')
        _radio(col, self, 'controller', 'INSTANCE', 'Instance')
        row = layout.row(align=True)
        row.label(text='Number of Copies:')
        row.prop(self, 'copies', text='')
        layout.label(text='Name')
        layout.prop(self, 'name', text='')

    def execute(self, context):
        tx = _pending.pop(self.token, None)
        if tx is None:
            return {'CANCELLED'}
        tx.finish(self.mode, self.copies, self.name, self.controller)
        _last.update(mode=self.mode, controller=self.controller, copies=self.copies)
        return {'FINISHED'}

    def cancel(self, context):
        tx = _pending.pop(self.token, None)
        if tx:
            tx.cancel()


class MAX_OT_clone_part(Operator):
    """Clone the selection as a separate object or as part of this mesh"""
    bl_idname = 'max.clone_part'
    bl_label = 'Clone Part of Mesh'
    bl_options = {'UNDO', 'INTERNAL'}

    token: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    destination: EnumProperty(items=[('OBJECT', 'Clone To Object', ''), ('ELEMENT', 'Clone To Element', '')])
    name: StringProperty(name='Name')

    def invoke(self, context, event):
        tx = _pending.get(self.token)
        if tx is None:
            return {'CANCELLED'}
        self.destination = _last['destination']
        self.name = clone_name(tx.active.name)
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        row = self.layout.row(align=True)
        _radio(row, self, 'destination', 'OBJECT', 'Clone To Object')
        field = row.row(align=True)
        field.enabled = self.destination == 'OBJECT'
        field.prop(self, 'name', text='')
        _radio(self.layout, self, 'destination', 'ELEMENT', 'Clone To Element')

    def execute(self, context):
        tx = _pending.pop(self.token, None)
        if tx is None:
            return {'CANCELLED'}
        tx.finish(self.destination, self.name)
        _last['destination'] = self.destination
        return {'FINISHED'}

    def cancel(self, context):
        tx = _pending.pop(self.token, None)
        if tx:
            tx.cancel()


class MAX_OT_extend_edges(Operator):
    """Finish Shift-transforming open edges"""
    bl_idname = 'max.extend_edges'
    bl_label = 'Extend Edges'
    bl_options = {'UNDO', 'INTERNAL'}
    token: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        tx = _pending.pop(self.token, None)
        if tx is None:
            return {'CANCELLED'}
        tx.finish('ELEMENT', '')
        return {'FINISHED'}


class MAX_OT_shift_clone(Operator):
    """Hold Shift and drag a transform gizmo or the selected geometry to clone"""
    bl_idname = 'max.shift_drag_clone'
    bl_label = 'Shift Clone'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        if context.area is None or context.area.type != 'VIEW_3D' or context.region.type != 'WINDOW':
            return False
        if context.mode not in {'OBJECT', 'EDIT_MESH'} or context.active_object is None:
            return False
        if context.mode == 'OBJECT' and not context.selected_objects:
            return False
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        return tool and tool.idname in _TOOLS

    def invoke(self, context, event):
        key = context.window.as_pointer()
        if key in _watchers:
            return {'PASS_THROUGH'}
        # 4.2 supports this RNA collection too. Never inspect private operator memory.
        if not hasattr(context.window, 'modal_operators'):
            self.report({'WARNING'}, 'Shift cloning needs Blender modal operator tracking')
            return {'PASS_THROUGH'}
        self.key = key
        self.tx = None
        self.timer = None
        self.tool = context.workspace.tools.from_space_view3d_mode(context.mode).idname
        _watchers.add(key)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL', 'PASS_THROUGH'}

    def _stop(self, context):
        _watchers.discard(self.key)
        if self.timer:
            context.window_manager.event_timer_remove(self.timer)
            self.timer = None

    def modal(self, context, event):
        try:
            return self._modal(context, event)
        except Exception as exc:
            self.cancel(context)
            self.report({'ERROR'}, f'Shift Clone: {exc}')
            return {'CANCELLED'}

    def _modal(self, context, event):
        if self.tx is None:
            if event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'} and event.value == 'RELEASE':
                self._stop(context)
                return {'FINISHED'}
            if event.type in {'ESC', 'RIGHTMOUSE'} or not self.poll(context):
                self._stop(context)
                return {'FINISHED', 'PASS_THROUGH'}
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS' and event.shift:
                if event.ctrl or event.alt:
                    return {'PASS_THROUGH'}
                # Start at the press so the transform's mouse origin matches the handle.
                self.tx = ObjectClone(context) if context.mode == 'OBJECT' else MeshClones(context)
                axis = _gizmo_hit(context, event, self.tx, self.tool)
                if axis is None and not _over_selection(context, event, self.tx):
                    self.tx.cancel()
                    self._stop(context)
                    return {'CANCELLED', 'PASS_THROUGH'}
                self.timer = context.window_manager.event_timer_add(0.04, window=context.window)
                transform = _TOOLS[self.tool]
                result = getattr(bpy.ops.max, f'shift_clone_{transform}')(
                    'INVOKE_DEFAULT', **{
                        'TRANSFORM_OT_' + transform: dict(release_confirm=True,
                            constraint_axis=axis or (False, False, False),
                            orient_type=context.scene.transform_orientation_slots[0].type)})
                if 'RUNNING_MODAL' not in result:
                    self.tx.cancel()
                    self._stop(context)
                    return {'CANCELLED'}
                return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'}
        if event.type == 'TIMER':
            running = any(op.bl_idname.startswith(('TRANSFORM_OT_', 'MAX_OT_shift_clone_'))
                          for op in context.window.modal_operators)
            if not running:
                self._stop(context)
                if not self.tx.changed():
                    self.tx.cancel()
                    return {'CANCELLED'}
                token = str(self.as_pointer())
                _pending[token] = self.tx
                if isinstance(self.tx, ObjectClone):
                    bpy.ops.max.shift_clone_options('INVOKE_DEFAULT', token=token)
                elif self.tx.level in {2, 3}:
                    bpy.ops.max.extend_edges(token=token)
                    # This branch finishes inside a modal callback, without a
                    # dialog's own UI event to push the completed mesh state.
                    bpy.ops.ed.undo_push(message='Extend Edges')
                else:
                    bpy.ops.max.clone_part('INVOKE_DEFAULT', token=token)
                return {'FINISHED'}
        return {'PASS_THROUGH'}

    def cancel(self, context):
        self._stop(context)
        if self.tx:
            self.tx.cancel()


def unregister():
    for tx in _pending.values():
        tx.cancel()
    _pending.clear()
    _watchers.clear()


# Macro children do not push their own undo states. The final dialog pushes once,
# after all copies are committed. Keep popups outside the native modal macro.
_macros = tuple(type(f'MAX_OT_shift_clone_{transform}', (bpy.types.Macro,), {
    '__module__': __name__, 'bl_idname': f'max.shift_clone_{transform}',
    'bl_label': 'Shift Clone', 'bl_options': {'INTERNAL'},
}) for transform in _TOOLS.values())


def register_macros():
    for cls in _macros:
        transform = cls.bl_idname.removeprefix('max.shift_clone_')
        cls.define('TRANSFORM_OT_' + transform)


classes = (MAX_OT_shift_clone_options, MAX_OT_clone_part, MAX_OT_extend_edges, MAX_OT_shift_clone) + _macros
