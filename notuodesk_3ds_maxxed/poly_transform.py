"""Constraint adapters for the existing Rotate and Scale tools.

New Max transform tools keep their own input and gizmos. They use the same
MoveSession.apply_targets hook after computing requested world positions.
"""
import math
import sys

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, BoolVectorProperty
from mathutils import Matrix, Vector


def select(context, kind):
    from . import poly_constraints as pc
    snaps = sys.modules.get(__package__ + '.snaps')
    rotate = sys.modules.get(__package__ + '.max_rotate')
    # The rebuilt tools already call apply_targets. Keep their gizmos, locks and
    # snap behavior when selecting a tool or changing the Constraints radio.
    if snaps and rotate and callable(getattr(rotate, 'constraint_session', None)):
        snaps.select_transform(context, kind)
        return
    if pc.select_transform(context, kind):
        return
    if snaps:
        snaps.select_transform(context, kind)
    else:
        bpy.ops.wm.tool_set_by_id(name='builtin.' + kind.lower())


class MAX_OT_poly_transform_tool(bpy.types.Operator):
    bl_idname = 'max.poly_transform_tool'
    bl_label = 'Select and Transform'
    kind: EnumProperty(items=[('ROTATE', 'Rotate', ''), ('SCALE', 'Scale', '')])

    def execute(self, context):
        select(context, self.kind)
        return {'FINISHED'}


class MAX_OT_poly_transform(bpy.types.Operator):
    """Rotate or scale along the original mesh. Right-click cancels"""
    bl_idname = 'max.poly_transform'
    bl_label = 'Transform'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}
    kind: EnumProperty(items=[('ROTATE', 'Rotate', ''), ('SCALE', 'Scale', '')])
    angle: FloatProperty(subtype='ANGLE')
    axis: FloatVectorProperty(size=3, default=(0,0,1))
    factors: FloatVectorProperty(size=3, default=(1,1,1))
    pivot: FloatVectorProperty(size=3)
    constraint_axis: BoolVectorProperty(size=3, default=(False,False,False), options={'SKIP_SAVE'})
    from_gizmo: BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def _begin(self, context):
        from . import poly_constraints as pc
        self.session = pc.MoveSession(context)
        self.basis = pc.orientation_basis(context)
        if not self.properties.is_property_set('pivot'):
            pivot = self.session.center.copy()
            if context.tool_settings.transform_pivot_point == 'CURSOR':
                pivot = context.scene.cursor.location.copy()
            self.pivot = pivot

    def _apply(self):
        pivot = Vector(self.pivot)
        matrix = (Matrix.Rotation(self.angle, 3, Vector(self.axis)) if self.kind == 'ROTATE'
                  else self.basis @ Matrix.Diagonal(Vector(self.factors)) @ self.basis.inverted_safe())
        for ob, me, inverse, mode, surface, vertices in self.session.meshes:
            self.session.apply_targets({ob: {i: pivot + matrix @ (start-pivot) for i,start,rails,normal in vertices}})

    def execute(self, context):
        self._begin(context)
        try:
            self._apply()
            self.session.finish()
        except Exception:
            self.session.cancel()
            raise
        return {'FINISHED'}

    def invoke(self, context, event):
        from . import poly_constraints as pc
        if not pc.active(context):
            op = bpy.ops.transform.rotate if self.kind == 'ROTATE' else bpy.ops.transform.resize
            op('INVOKE_DEFAULT', release_confirm=True, constraint_axis=self.constraint_axis)
            return {'CANCELLED'}
        self._begin(context)
        self.start_x = event.mouse_region_x
        if event.value == 'CLICK_DRAG':
            self.start_x = event.mouse_prev_press_x-context.region.x
        self.release_confirm = self.from_gizmo or event.value == 'CLICK_DRAG'
        self.number = ''
        self.view_axis = context.region_data.view_rotation @ Vector((0,0,1))
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set(self.kind.title() + ' constrained. X/Y/Z: axis. Right-click or Esc: cancel')
        return {'RUNNING_MODAL'}

    def _update(self, context, event):
        pixels = event.mouse_region_x-self.start_x
        axes = [i for i,v in enumerate(self.constraint_axis) if v]
        typed = self.number not in {'', '-', '.', '-.'}
        if self.kind == 'ROTATE':
            self.axis = self.basis.col[axes[0]] if len(axes) == 1 else self.view_axis
            self.angle = math.radians(float(self.number)) if typed else pixels*.01
        else:
            factor = float(self.number)/100 if typed else 1+pixels/100
            self.factors = tuple(factor if not axes or i in axes else 1 for i in range(3))
        self._apply()
        context.area.tag_redraw()

    def _finish(self, context, cancel=False):
        self.session.cancel() if cancel else self.session.finish()
        context.workspace.status_text_set(None)
        context.area.tag_redraw()
        return {'CANCELLED'} if cancel else {'FINISHED'}

    def modal(self, context, event):
        if self.session.closed or context.mode != 'EDIT_MESH':
            return self._finish(context, True)
        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            return self._finish(context, True)
        try:
            if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
                self._update(context, event)
                return self._finish(context)
            if event.type == 'LEFTMOUSE' and event.value == ('RELEASE' if self.release_confirm else 'PRESS'):
                self._update(context, event)
                return self._finish(context)
            if event.value == 'PRESS':
                if event.type in {'X', 'Y', 'Z'}:
                    index = 'XYZ'.index(event.type)
                    self.constraint_axis = tuple(i != index if event.shift else i == index for i in range(3))
                elif event.type == 'BACK_SPACE':
                    self.number = self.number[:-1]
                elif event.ascii and event.ascii in '0123456789.-':
                    candidate = self.number + event.ascii
                    try:
                        if candidate not in {'-', '.', '-.'}:
                            float(candidate)
                        self.number = candidate
                    except ValueError:
                        pass
            if event.type == 'MOUSEMOVE' or event.value == 'PRESS':
                self._update(context, event)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return self._finish(context, True)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if hasattr(self, 'session'):
            self._finish(context, True)


class MAX_WST_poly_rotate(bpy.types.WorkSpaceTool):
    bl_idname = 'max.poly_rotate'
    bl_label = 'Select and Rotate'
    bl_description = 'Rotate with Editable Poly Constraints'
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_icon = 'ops.transform.rotate'
    bl_widget = 'MAX_GGT_poly_transform'
    bl_keymap = (('max.poly_transform', {'type':'LEFTMOUSE', 'value':'CLICK_DRAG'}, {'properties':[('kind','ROTATE')]}),
                 ('view3d.select', {'type':'LEFTMOUSE', 'value':'CLICK'}, {'properties':[('deselect_all',True)]}))


class MAX_WST_poly_scale(bpy.types.WorkSpaceTool):
    bl_idname = 'max.poly_scale'
    bl_label = 'Select and Scale'
    bl_description = 'Scale with Editable Poly Constraints'
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_icon = 'ops.transform.resize'
    bl_widget = 'MAX_GGT_poly_transform'
    bl_keymap = (('max.poly_transform', {'type':'LEFTMOUSE', 'value':'CLICK_DRAG'}, {'properties':[('kind','SCALE')]}),
                 ('view3d.select', {'type':'LEFTMOUSE', 'value':'CLICK'}, {'properties':[('deselect_all',True)]}))


class MAX_GGT_poly_transform(bpy.types.GizmoGroup):
    bl_idname = 'MAX_GGT_poly_transform'
    bl_label = 'Constrained transform'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls, context):
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        return bool(tool and context.mode == 'EDIT_MESH' and tool.idname in {'max.poly_rotate','max.poly_scale'})

    def setup(self, context):
        self.handles = []
        for i,color in enumerate(((1,.15,.15),(.3,1,.2),(.2,.5,1))):
            for kind in ('ROTATE','SCALE'):
                gizmo = self.gizmos.new('GIZMO_GT_dial_3d' if kind == 'ROTATE' else 'GIZMO_GT_arrow_3d')
                gizmo.color, gizmo.alpha = color,.8
                gizmo.color_highlight, gizmo.alpha_highlight = (1,1,.2),1
                if kind == 'SCALE':
                    gizmo.draw_style = 'BOX'
                props = gizmo.target_set_operator('max.poly_transform')
                props.kind, props.from_gizmo = kind,True
                props.constraint_axis = tuple(j == i for j in range(3))
                self.handles.append((gizmo,i,kind))

    def draw_prepare(self, context):
        import bmesh
        from . import poly_constraints as pc
        bm = bmesh.from_edit_mesh(context.object.data)
        points = [context.object.matrix_world @ v.co for v in bm.verts if v.select and not v.hide]
        center = sum(points,Vector())/max(1,len(points))
        basis = pc.orientation_basis(context)
        tool = context.workspace.tools.from_space_view3d_mode(context.mode).idname
        for gizmo,i,kind in self.handles:
            gizmo.hide = not points or tool != 'max.poly_'+kind.lower()
            matrix = basis.col[i].normalized().to_track_quat('Z','Y').to_matrix().to_4x4()
            matrix.translation = center
            gizmo.matrix_basis = matrix


def register_tools():
    from . import poly_constraints as pc
    for tool in (MAX_WST_poly_rotate,MAX_WST_poly_scale):
        pc.register_tool(tool)


def unregister_tools():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                with bpy.context.temp_override(window=window,area=area):
                    tool = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode,create=False)
                    if tool and tool.idname in {'max.poly_rotate','max.poly_scale'}:
                        bpy.ops.wm.tool_set_by_id(name='builtin.'+tool.idname.split('_')[-1])
    for tool in (MAX_WST_poly_scale,MAX_WST_poly_rotate):
        bpy.utils.unregister_tool(tool)


classes = (MAX_OT_poly_transform_tool,MAX_OT_poly_transform,MAX_GGT_poly_transform)
