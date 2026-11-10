"""Live Max mode cues. UI hooks use the real Blender mode and workspace tool."""
import bpy
import bmesh
import gpu
from bpy.props import BoolProperty, CollectionProperty, IntProperty
from bpy.types import Operator, PropertyGroup, UIList, WorkSpaceTool
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from . import max_icons

LEVELS = ('Vertex', 'Edge', 'Border', 'Polygon', 'Element')
LEVEL_ICONS = ('VERTEXSEL', 'EDGESEL', 'MOD_EDGESPLIT', 'FACESEL', 'MESH_CUBE')
YELLOW = (1.0, .85, .0, 1.0)
_handle = None
_cursor_handle = None
_last_state = None
_batches = {}
_selection_summaries = {}
_pointers = {}
_active_views = {}
_link_drags = {}
_running = False
PASSIVE_MODALS = {'MAX_OT_feedback_pointer', 'MAX_OT_snap_button_listener',
                  'MAX_OT_chrome_pointer'}
COMMAND_MODALS = {'MAX_OT_cut': 'CUT', 'MAX_OT_swift_loop': 'SWIFT_LOOP',
                  'MAX_OT_poly_quick_slice': 'QUICK_SLICE', 'MAX_OT_target_weld': 'TARGET_WELD',
                  'MAX_OT_create': 'CREATE', 'MAX_OT_line': 'LINE'}

def pointer_state(key):
    pointer = _pointers.get(key)
    if pointer is not None:
        try:
            pointer.window
        except ReferenceError:
            _pointers.pop(key,None)
            return None
        try:
            if pointer.hit is not None:
                pointer.hit.name
        except ReferenceError:
            pointer.hit = None
    return pointer

def level(context):
    from .operators import current_level
    return current_level(context)

def tool_kind(idname):
    if idname in {'builtin.select', 'builtin.select_box', 'builtin.select_circle', 'builtin.select_lasso'}:
        return 'SELECT'
    for kind in ('MOVE', 'ROTATE', 'SCALE'):
        if idname in {'builtin.'+kind.lower(), 'max.snap_'+kind.lower(), 'max.'+kind.lower(), 'max.poly_'+kind.lower()}:
            return kind
    return 'LINK' if idname == 'max.select_link' else idname

def active_tool(context):
    from . import poly_caddies
    caddy = poly_caddies._active.get(context.window.as_pointer()) if context.window else None
    if caddy is not None and not caddy.session.closed:
        return caddy.session.action
    for op in getattr(context.window, 'modal_operators', ()):
        if op and op.bl_idname in COMMAND_MODALS:
            return COMMAND_MODALS[op.bl_idname]
    workspace = context.workspace
    if workspace:
        tool = workspace.tools.from_space_view3d_mode(context.mode, create=False)
        if tool:
            return tool_kind(tool.idname)
    return 'SELECT'

def tool_pressed(context, kind):
    return active_tool(context) == kind

def restore_tool(context, kind):
    from .operators import viewport_override
    override = viewport_override(context)
    if not override:
        return
    with context.temp_override(**override):
        if kind in {'MOVE', 'ROTATE', 'SCALE'}:
            from .snaps import select_transform
            select_transform(bpy.context, kind)
        elif kind == 'SELECT':
            bpy.ops.wm.tool_set_by_id(name='builtin.select_box')

def selection_text(context):
    from . import symmetry
    if symmetry.editing(context):
        return 'Mirror Selected'
    if context.mode == 'OBJECT':
        n = len(context.selected_objects)
        return 'None Selected' if not n else f"{n} Object{'s' if n != 1 else ''} Selected"
    if context.mode == 'EDIT_MESH':
        lev = level(context)
        count, _ = _selection_summary(context, lev)
        noun = {1: ('Vertex', 'Vertices'), 2: ('Edge', 'Edges'), 3: ('Edge', 'Edges'),
                4: ('Polygon', 'Polygons'), 5: ('Polygon', 'Polygons')}[lev]
        return f'{count} {noun[count != 1]} Selected'
    return 'Sub-Object Selected'

def rollout_selection_text(context):
    """Max's rollout identifies one component by its one-based ID."""
    if context.mode != 'EDIT_MESH':
        return 'Whole Object Selected'
    lev = level(context)
    count, single_id = _selection_summary(context, lev)
    if count == 1 and len(context.objects_in_mode_unique_data) == 1:
        noun = 'Vertex' if lev == 1 else 'Edge' if lev in (2, 3) else 'Polygon'
        return f'{noun} {single_id} Selected'
    return selection_text(context)

def _selection_summary(context, lev):
    """Share a scan between status and rollout until selection/geometry changes."""
    count, single_id = 0, None
    for ob in context.objects_in_mode_unique_data:
        mesh = ob.data
        key = mesh.as_pointer()
        # Native counters catch changes even before depsgraph callbacks run.
        state = (lev, mesh.total_vert_sel, mesh.total_edge_sel, mesh.total_face_sel)
        cached = _selection_summaries.get(key)
        if cached is None or cached[0] != state:
            bm = bmesh.from_edit_mesh(mesh)
            seq = bm.verts if lev == 1 else bm.edges if lev in (2, 3) else bm.faces
            selected = [i+1 for i, item in enumerate(seq) if item.select and not item.hide]
            cached = (state, len(selected), selected[0] if len(selected) == 1 else None)
            _selection_summaries[key] = cached
        count += cached[1]
        if cached[1]:
            single_id = cached[2]
    return count, single_id

def prompt_text(context):
    kind = active_tool(context)
    command_prompts = {
        'CUT': 'Cut: click a start point, then the next cut point. Right-click to finish.',
        'SWIFT_LOOP': 'SwiftLoop: point at an edge, then click to insert a loop. Right-click to finish.',
        'QUICK_SLICE': 'QuickSlice: click start, then endpoint. Right-click to finish.',
        'TARGET_WELD': 'Target Weld: pick source, then target. Right-click to finish.',
        'CREATE': 'Click and drag to create. Right-click to stop creating.',
        'LINE': 'Line: click to add a vertex. Right-click to finish.',
    }
    if kind in command_prompts:
        return command_prompts[kind]
    from . import symmetry, poly_caddies
    if kind in poly_caddies.ACTIONS:
        return f'{kind.title()}: adjust the caddy, then accept or cancel.'
    noun = 'Mirror' if symmetry.editing(context) else 'objects' if not level(context) else LEVELS[level(context)-1].lower()
    noun = {'vertex': 'vertices', 'edge': 'edges', 'border': 'borders',
            'polygon': 'polygons', 'element': 'elements'}.get(noun, noun)
    if kind == 'LINK':
        return 'Drag from a child object to its parent. Right-click to finish.'
    verb = {'MOVE': ' and move', 'ROTATE': ' and rotate', 'SCALE': ' and scale'}.get(kind, '')
    return f'Click and drag to select{verb} {noun}'

def draw_status(self, context, original, max_draw):
    if not context.workspace or context.workspace.name != '3ds Max':
        return original(self, context)
    # Native modal instructions still take priority over idle tool prompts.
    if any(op and op.bl_idname not in PASSIVE_MODALS for op in getattr(context.window, 'modal_operators', ())):
        return original(self, context)
    if active_tool(context) not in {'SELECT', 'MOVE', 'ROTATE', 'SCALE', 'LINK'}:
        return original(self, context)
    self.layout.label(text=prompt_text(context))
    self.layout.separator_spacer()
    max_draw(self, context)

def draw_sublevel_menu(layout, context, order=(0, 1, 2, 3, 4, 5)):
    current = level(context)
    for lev in order:
        name = 'Top-level' if lev == 0 else LEVELS[lev-1]
        layout.operator('max.subobject', text=name,
                        icon='CHECKMARK' if current == lev else 'NONE').level = lev

class MAX_PG_feedback_level(PropertyGroup):
    pass

class MAX_UL_feedback_levels(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.separator(factor=1.1)
        row.label(text=LEVELS[index])
        if level(context) == index+1:
            row.label(text='', **max_icons.ui(LEVELS[index].lower(), LEVEL_ICONS[index]))

def draw_stack_levels(layout, context, ob, base_label, base_icon):
    """Keep this call when merging other stack implementations."""
    lev = level(context)
    from . import symmetry
    mirror = symmetry.editing(context)
    editable = ob.type == 'MESH' and not ob.max_prim.kind
    row = layout.row(align=True)
    if editable:
        row.prop(ob, 'max_feedback_expanded', text='', emboss=False,
                 icon='TRIA_DOWN' if ob.max_feedback_expanded else 'TRIA_RIGHT')
    from .ui_panel import _stack_get
    row.operator('max.modifier_set_active', text=base_label,
                 depress=_stack_get(ob) < 0 and lev == 0 and not mirror, **base_icon).name = ''
    if lev and editable:
        row.label(text='', **max_icons.ui(LEVELS[lev-1].lower(), LEVEL_ICONS[lev-1]))
    if editable and ob.max_feedback_expanded and not mirror:
        wm = context.window_manager
        if len(wm.max_feedback_levels) != 5:
            # Collection initialisation belongs in register/load, never draw.
            return
        layout.template_list('MAX_UL_feedback_levels', '', wm, 'max_feedback_levels',
                             wm, 'max_feedback_index', rows=5, maxrows=5, sort_lock=True)

def _index_get(wm):
    return level(bpy.context)-1

def _index_set(wm, value):
    if 0 <= value < 5:
        from .operators import viewport_override
        override = viewport_override(bpy.context)
        if override:
            with bpy.context.temp_override(**override):
                bpy.ops.max.subobject(level=value+1)

def command_tab_changed(wm, context):
    from . import symmetry
    if wm.max_cmd_tab != 'MODIFY' and symmetry.editing(context):
        symmetry.leave(context)
    if wm.max_cmd_tab != 'MODIFY' and context.object and context.object.mode == 'EDIT':
        from .operators import viewport_override
        override = viewport_override(context)
        if override:
            with context.temp_override(**override):
                bpy.ops.max.subobject(level=0)

class MAX_OT_selection_brackets(Operator):
    bl_idname = 'max.selection_brackets'
    bl_label = 'Selection Brackets'
    bl_description = 'Show white brackets around selected objects in shaded viewports (J)'
    def execute(self, context):
        context.scene.max_selection_brackets = not context.scene.max_selection_brackets
        for area in context.screen.areas:
            area.tag_redraw()
        return {'FINISHED'}

def bracket_segments(corners):
    """Three short strokes meet at each of the eight object bounds corners."""
    points = [Vector(c) for c in corners]
    out = []
    for i, p in enumerate(points):
        neighbors = sorted((q for j, q in enumerate(points) if i != j and
                            sum(abs(p[k]-q[k]) > 1e-6 for k in range(3)) == 1),
                           key=lambda q: (q-p).length)
        for q in neighbors:
            out.extend((p, p+(q-p)*.18))
    return out

def _mesh_batch(ob):
    key = ob.as_pointer()
    if key not in _batches:
        evaluated = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            coords = [v.co.copy() for v in mesh.vertices]
            indices = [tuple(e.vertices) for e in mesh.edges]
            _batches[key] = batch_for_shader(shader, 'LINES', {'pos': coords}, indices=indices)
        finally:
            evaluated.to_mesh_clear()
    return _batches[key]

def _draw_selection():
    ctx = bpy.context
    if not ctx.workspace or ctx.workspace.name != '3ds Max' or ctx.mode != 'OBJECT':
        return
    space = ctx.space_data
    if not space.overlay.show_overlays:
        return
    wire = space.shading.type == 'WIREFRAME'
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    try:
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(1.5)
        selected = list(ctx.selected_objects)
        pointer = pointer_state(ctx.window.as_pointer())
        hovered = pointer.hit if pointer and pointer.area == ctx.area else None
        if hovered and hovered not in selected and hovered.type == 'MESH':
            selected.append(hovered)
        for ob in selected:
            if not ob.visible_get(viewport=space):
                continue
            with gpu.matrix.push_pop():
                gpu.matrix.multiply_matrix(ob.matrix_world)
                preview = ob == hovered and not ob.select_get()
                if ob.type == 'MESH' and ob.display_type != 'BOUNDS':
                    gpu.state.depth_test_set('NONE' if wire else 'LESS_EQUAL')
                    shader.bind()
                    shader.uniform_float('color', YELLOW if preview else (1, 1, 1, 1))
                    _mesh_batch(ob).draw(shader)
                if not preview and not wire and ctx.scene.max_selection_brackets:
                    coords = bracket_segments(ob.bound_box)
                    if coords:
                        gpu.state.depth_test_set('NONE')
                        shader.bind()
                        shader.uniform_float('color', (1, 1, 1, 1))
                        batch_for_shader(shader, 'LINES', {'pos': coords}).draw(shader)
    finally:
        gpu.state.depth_test_set('NONE')
        gpu.state.line_width_set(1)
        gpu.state.blend_set('NONE')

@persistent
def invalidate(*_):
    _batches.clear()
    _selection_summaries.clear()

@persistent
def on_history(*_):
    from .operators import sync_sublevel
    invalidate()
    sync_sublevel(bpy.context)

def refresh():
    """Tool switches do not always emit depsgraph updates. Watch actual state."""
    global _last_state
    ctx = bpy.context
    # Timers can run during shutdown after selection context has disappeared.
    if (not ctx.window_manager or not hasattr(ctx.window_manager, 'max_sublevel')
            or not hasattr(ctx, 'selected_objects')):
        return .1
    from .operators import sync_sublevel
    sync_sublevel(ctx)
    for wm in bpy.data.window_managers:
        if len(wm.max_feedback_levels) != 5:
            wm.max_feedback_levels.clear()
            for name in LEVELS:
                wm.max_feedback_levels.add().name = name
    for window in ctx.window_manager.windows:
        if window.workspace.name == '3ds Max' and pointer_state(window.as_pointer()) is None:
            area = next((a for a in window.screen.areas if a.type == 'VIEW_3D'), None)
            region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
            if region:
                with ctx.temp_override(window=window, area=area, region=region):
                    bpy.ops.max.feedback_pointer('INVOKE_DEFAULT')
    state = (ctx.mode, level(ctx), tuple(ob.as_pointer() for ob in ctx.selected_objects),
             tuple((w.as_pointer(), w.workspace.as_pointer(),
                    w.workspace.tools.from_space_view3d_mode(ctx.mode, create=False).idname
                    if w.workspace.tools.from_space_view3d_mode(ctx.mode, create=False) else '')
                   for w in ctx.window_manager.windows))
    if state != _last_state:
        _last_state = state
        theme = ctx.preferences.themes[0].view_3d
        # Max shades selected polygons, not selected faces at Vertex/Edge levels.
        alpha = .35 if level(ctx) in (4, 5) else 0
        if ctx.workspace and ctx.workspace.name == '3ds Max':
            for prop in ('face_select', 'face_mode_select', 'editmesh_active'):
                if hasattr(theme, prop):
                    setattr(theme, prop, (1, 0, 0, alpha))
        for window in ctx.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
    return .1

@persistent
def on_load(*_):
    global _last_state
    _last_state = None
    on_history()
    _pointers.clear()
    _active_views.clear()
    for wm in bpy.data.window_managers:
        wm.max_feedback_levels.clear()
        for name in LEVELS:
            wm.max_feedback_levels.add().name = name

def object_under_mouse(context, event):
    from bpy_extras import view3d_utils
    origin = view3d_utils.region_2d_to_origin_3d(context.region, context.region_data,
                                               (event.mouse_region_x, event.mouse_region_y))
    direction = view3d_utils.region_2d_to_vector_3d(context.region, context.region_data,
                                                  (event.mouse_region_x, event.mouse_region_y))
    hit, _, _, _, ob, _ = context.scene.ray_cast(context.evaluated_depsgraph_get(), origin, direction)
    if hit and ob.visible_get(viewport=context.space_data):
        return ob.original
    # Blender's ray cast has no pick surface for helpers and un-bevelled splines.
    # Their projected origins are the closest available add-on pick target.
    candidates = []
    mouse = Vector((event.mouse_region_x,event.mouse_region_y))
    for candidate in context.visible_objects:
        if candidate.type == 'MESH' or candidate.hide_select:
            continue
        p = view3d_utils.location_3d_to_region_2d(context.region,context.region_data,
                                                candidate.matrix_world.translation)
        if p is not None and (p-mouse).length <= 10:
            candidates.append(((p-mouse).length,candidate))
    return min(candidates,key=lambda item:item[0])[1] if candidates else None

def cursor_kind(kind, hit, selected):
    if not hit:
        return 'DEFAULT'
    if kind == 'LINK':
        return 'LINK'
    if not selected or kind == 'SELECT':
        return 'CROSSHAIR'
    return {'MOVE': 'MOVE', 'ROTATE': 'ROTATE', 'SCALE': 'SCALE', 'LINK': 'CROSSHAIR'}.get(kind, 'DEFAULT')

class MAX_OT_feedback_pointer(Operator):
    """Passive pointer observer. Never consumes an input event."""
    bl_idname = 'max.feedback_pointer'
    bl_label = 'Mode Feedback Pointer'
    bl_options = {'INTERNAL'}
    def invoke(self, context, event):
        self.window = context.window
        self.area = context.area
        self.region = context.region
        self.hit = None
        self.xy = (0, 0)
        self.cursor = 'DEFAULT'
        _active_views.setdefault(self.window.as_pointer(), (context.area.as_pointer(), context.region.as_pointer()))
        self.timer = context.window_manager.event_timer_add(.2, window=self.window)
        _pointers[self.window.as_pointer()] = self
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not _running or _pointers.get(self.window.as_pointer()) is not self:
            context.window_manager.event_timer_remove(self.timer)
            self.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        if event.type in {'LEFTMOUSE', 'MIDDLEMOUSE', 'RIGHTMOUSE'} and event.value == 'PRESS':
            for area in self.window.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW' and region.x <= event.mouse_x < region.x+region.width and region.y <= event.mouse_y < region.y+region.height:
                            _active_views[self.window.as_pointer()] = (area.as_pointer(), region.as_pointer())
                            area.tag_redraw()
        if event.type not in {'MOUSEMOVE', 'TIMER'}:
            return {'PASS_THROUGH'}
        self.cursor = 'DEFAULT'
        self.hit = None
        # Other modals, popup menus and native transforms own their cursors.
        others = [op for op in getattr(self.window, 'modal_operators', ())
                  if op and op.bl_idname not in PASSIVE_MODALS]
        if self.window.workspace.name == '3ds Max' and not others:
            area = next((a for a in self.window.screen.areas if a.type == 'VIEW_3D' and
                         a.x <= event.mouse_x < a.x+a.width and a.y <= event.mouse_y < a.y+a.height), None)
            region = next((r for r in area.regions if r.type == 'WINDOW' and
                           r.x <= event.mouse_x < r.x+r.width and r.y <= event.mouse_y < r.y+r.height), None) if area else None
            if region:
                self.area = area
                self.region = region
                self.xy = (event.mouse_x-region.x, event.mouse_y-region.y)
                from types import SimpleNamespace
                pos = SimpleNamespace(mouse_region_x=self.xy[0], mouse_region_y=self.xy[1])
                with context.temp_override(window=self.window, area=area, region=region):
                    kind = active_tool(bpy.context)
                    if kind in {'SELECT', 'MOVE', 'ROTATE', 'SCALE', 'LINK'}:
                        # Object picking adds no component information in Edit Poly.
                        self.hit = (bpy.context.edit_object if bpy.context.mode == 'EDIT_MESH'
                                    else object_under_mouse(bpy.context, pos))
                        self.cursor = cursor_kind(kind, self.hit is not None,
                                                  bool(self.hit and self.hit.select_get()))
                area.tag_redraw()
        # Modal cursors used by Cut/creation remain above this ordinary cursor.
        self.window.cursor_set('NONE' if self.cursor in {'MOVE', 'ROTATE', 'SCALE', 'LINK'} else self.cursor)
        return {'PASS_THROUGH'}

def _draw_cursor():
    ctx = bpy.context
    if not ctx.workspace or ctx.workspace.name != '3ds Max':
        return
    _draw_view_border(ctx)
    link = _link_drags.get(ctx.window.as_pointer())
    if link and link.window == ctx.window and link.area == ctx.area and link.region == ctx.region:
        _draw_link_drag(link)
    pointer = pointer_state(ctx.window.as_pointer()) if ctx.window else None
    if link and link.window == ctx.window and link.area == ctx.area and link.region == ctx.region:
        xy, kind = link.mouse, 'LINK'
    elif (not link and pointer and pointer.window == ctx.window
          and pointer.area == ctx.area and pointer.region == ctx.region):
        xy, kind = pointer.xy, pointer.cursor
    else:
        return
    if kind not in {'MOVE', 'ROTATE', 'SCALE', 'LINK'}:
        return
    x, y = xy
    if kind == 'LINK':
        strokes = [(-7,0),(-2,5),(-2,5),(2,1),(2,1),(-3,-4),(-3,-4),(-7,0),
                   (-1,-2),(4,3),(4,3),(8,-1),(8,-1),(3,-6),(3,-6),(-1,-2)]
    elif kind == 'MOVE':
        strokes = [(-8,0),(8,0),(0,-8),(0,8),(-8,0),(-5,3),(-8,0),(-5,-3),
                   (8,0),(5,3),(8,0),(5,-3),(0,8),(-3,5),(0,8),(3,5),
                   (0,-8),(-3,-5),(0,-8),(3,-5)]
    elif kind == 'SCALE':
        strokes = [(-7,-7),(7,7),(-7,-7),(-7,-1),(-7,-7),(-1,-7),
                   (7,7),(1,7),(7,7),(7,1)]
    else:
        import math
        strokes = []
        for i in range(20):
            for angle in (i*.25, (i+1)*.25):
                strokes.append((7*math.cos(angle),7*math.sin(angle)))
        strokes += [(7,0),(10,4),(7,0),(3,3)]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    try:
        gpu.state.blend_set('ALPHA')
        shader.bind()
        batch = batch_for_shader(shader, 'LINES', {'pos': [(x+a,y+b) for a,b in strokes]})
        for width, color in ((3,(0,0,0,1)),(1,(1,1,1,1))):
            gpu.state.line_width_set(width)
            shader.uniform_float('color', color)
            batch.draw(shader)
    finally:
        gpu.state.line_width_set(1)
        gpu.state.blend_set('NONE')

def _draw_view_border(context):
    if _active_views.get(context.window.as_pointer()) != (context.area.as_pointer(), context.region.as_pointer()):
        return
    region, area, space = context.region, context.area, context.space_data
    right, top, bottom = region.width-1, region.height-1, 1
    for r in area.regions:
        if r.type == 'UI' and space.show_region_ui and r.width > 1 and r.x > region.x:
            right = min(right, r.x-region.x-1)
        if r.type in {'HEADER', 'TOOL_HEADER'} and r.height > 1:
            if r.y > region.y+region.height/2:
                top = min(top, r.y-region.y-1)
            elif r.y+ r.height > region.y:
                bottom = max(bottom,r.y+r.height-region.y)
    coords = [(1,bottom),(right,bottom),(right,bottom),(right,top),
              (right,top),(1,top),(1,top),(1,bottom)]
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('color',YELLOW)
    gpu.state.line_width_set(1)
    batch_for_shader(shader,'LINES',{'pos':coords}).draw(shader)

def _draw_link_drag(link):
    start, end = Vector(link.start), Vector(link.mouse)
    distance = (end-start).length
    if distance < 1:
        return
    direction = (end-start)/distance
    coords = []
    for i in range(0,int(distance),8):
        coords.extend((start+direction*i,start+direction*min(i+4,distance)))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('color',(1,1,1,1))
    batch_for_shader(shader,'LINES',{'pos':coords}).draw(shader)

def link_objects(children, parent):
    for child in children:
        ancestor = parent
        while ancestor is not None and ancestor != child:
            ancestor = ancestor.parent
        if ancestor is not None:
            continue
        matrix = child.matrix_world.copy()
        child.parent = parent
        child.matrix_world = matrix

class MAX_OT_link_pick(Operator):
    bl_idname = 'max.link_pick'
    bl_label = 'Select and Link'
    bl_options = {'UNDO'}
    def invoke(self, context, event):
        self.child = object_under_mouse(context, event)
        if self.child is None:
            return {'CANCELLED'}
        self.children = list(context.selected_objects) if self.child.select_get() else [self.child]
        self.area, self.region = context.area, context.region
        self.start = self.mouse = (event.mouse_region_x,event.mouse_region_y)
        self.window = context.window
        _link_drags[context.window.as_pointer()] = self
        context.window.cursor_modal_set('NONE')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    def finish(self, result):
        if _link_drags.get(self.window.as_pointer()) is self:
            _link_drags.pop(self.window.as_pointer(),None)
            self.window.cursor_modal_restore()
            self.area.tag_redraw()
        return {result}
    def modal(self, context, event):
        if not _running or _link_drags.get(self.window.as_pointer()) is not self:
            return self.finish('CANCELLED')
        self.mouse = (event.mouse_x-self.region.x,event.mouse_y-self.region.y)
        self.area.tag_redraw()
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            return self.finish('CANCELLED')
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            parent = object_under_mouse(context, event)
            if parent:
                link_objects(self.children,parent)
            return self.finish('FINISHED')
        return {'RUNNING_MODAL'}

class MAX_WST_select_link(WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = 'max.select_link'
    bl_label = 'Select and Link'
    bl_description = 'Drag a child onto its parent'
    bl_icon = 'ops.object.parent_set'
    bl_cursor = 'CROSSHAIR'
    bl_keymap = (('max.link_pick', {'type': 'LEFTMOUSE', 'value': 'PRESS'}, {}),
                 ('wm.tool_set_by_id', {'type': 'RIGHTMOUSE', 'value': 'PRESS'},
                  {'properties': [('name', 'builtin.select_box')]}))

classes = (MAX_PG_feedback_level, MAX_UL_feedback_levels, MAX_OT_selection_brackets,
           MAX_OT_feedback_pointer, MAX_OT_link_pick)

def register():
    global _handle, _cursor_handle, _running, _last_state
    _running = True
    _last_state = None
    bpy.types.Scene.max_selection_brackets = BoolProperty(name='Selection Brackets', default=False)
    bpy.types.Object.max_feedback_expanded = BoolProperty(name='Sub-object Levels', default=True)
    bpy.types.WindowManager.max_feedback_levels = CollectionProperty(type=MAX_PG_feedback_level)
    bpy.types.WindowManager.max_feedback_index = IntProperty(get=_index_get, set=_index_set)
    bpy.app.handlers.depsgraph_update_post.append(invalidate)
    bpy.app.handlers.undo_post.append(on_history)
    bpy.app.handlers.redo_post.append(on_history)
    bpy.app.handlers.load_post.append(on_load)
    if not bpy.app.background:
        _handle = bpy.types.SpaceView3D.draw_handler_add(_draw_selection, (), 'WINDOW', 'POST_VIEW')
        _cursor_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_cursor, (), 'WINDOW', 'POST_PIXEL')
        bpy.utils.register_tool(MAX_WST_select_link, after={'builtin.select_box'})
        bpy.app.timers.register(refresh, first_interval=.1, persistent=True)

def unregister():
    global _handle, _cursor_handle, _running
    _running = False
    if bpy.app.timers.is_registered(refresh):
        bpy.app.timers.unregister(refresh)
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    if _cursor_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_cursor_handle, 'WINDOW')
        _cursor_handle = None
    if not bpy.app.background:
        for window in bpy.context.window_manager.windows:
            if window.workspace.name == '3ds Max':
                window.cursor_set('DEFAULT')
        bpy.utils.unregister_tool(MAX_WST_select_link)
    _pointers.clear()
    _active_views.clear()
    for link in list(_link_drags.values()):
        link.finish('CANCELLED')
    for handlers, fn in ((bpy.app.handlers.depsgraph_update_post, invalidate),
                         (bpy.app.handlers.undo_post, on_history),
                         (bpy.app.handlers.redo_post, on_history),
                         (bpy.app.handlers.load_post, on_load)):
        if fn in handlers:
            handlers.remove(fn)
    _batches.clear()
    _selection_summaries.clear()
    for cls, name in ((bpy.types.Scene, 'max_selection_brackets'),
                      (bpy.types.Object, 'max_feedback_expanded'),
                      (bpy.types.WindowManager, 'max_feedback_levels'),
                      (bpy.types.WindowManager, 'max_feedback_index')):
        delattr(cls, name)
