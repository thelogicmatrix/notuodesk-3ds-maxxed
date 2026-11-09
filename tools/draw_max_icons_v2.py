"""Rebuild the original Max-inspired SVG family and placement catalog.

Every path below is an original drawing on a 16-unit grid. Autodesk references
inform the metaphor, never the path coordinates. No reference pixels are read.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'notuodesk_3ds_maxxed' / 'icons' / 'src'
_catalog = OUT / 'catalog.json'
BASELINE_NAMES = ({r['name'] for r in json.loads(_catalog.read_text(encoding='utf-8'))['icons']
                   if r['baseline'] is not None} if _catalog.exists()
                  else {p.stem for p in OUT.glob('*.svg')})
G = '#d2d4d5'
D = '#8d9295'
F = '#656b6e'
C = '#50b9bf'
Y = '#efb83d'
R = '#df6663'
B = '#699edf'
GREEN = '#79b981'
ART = {}
CAT = []
BASE = 'https://help.autodesk.com/cloudhelp/2026/ENU/'

REFS = {
    'toolbar': ('3DSMax-Basics', 'D60DB151-D25D-498D-AF02-410D4237A140', 'references/toolbar-*.png'),
    'tabs': ('3DSMax-Basics', 'E3CB809D-94ED-4C30-892B-1D12B8721EA5', 'references/command-panel-01.png through command-panel-06.png'),
    'categories': ('3DSMax-Basics', '6C4B9CF9-DCD6-42A6-A10C-F0E9C6A728AA', 'references/create-panel-03.png through create-panel-09.png'),
    'stack': ('3DSMax-Basics', '80209C3A-C2E4-4541-8738-D1E5ECE16E9C', 'references/stack-controls-20.png through stack-controls-25.png'),
    'subobjects': ('3DSMax-Modeling', '409D36AC-1D17-4B24-851D-1C49C7E0B79D', 'references/subobjects-03.png through subobjects-08.png'),
    'primitives': ('3DSMax-Modeling', '66152BDE-BA64-423F-8472-C1F0EB409E16', 'max-ui-reference/images/interface-overview.png, Object Type rollout'),
    'extended': ('3DSMax-Modeling', 'BF868DCF-12E3-431C-A73B-C16C0FD67C98', 'Object Type button list in Autodesk topic'),
    'splines': ('3DSMax-Modeling', 'F7E74643-39DD-4531-AB62-6832E2B759E1', 'Object Type button list in Autodesk topic'),
    'poly': ('3DSMax-Modeling', '8DA624B4-32AB-473A-B5B4-77B8934DAE1B', 'max-ui-reference/images/quad-default-2026.png and editable-poly.md'),
    'poly_vertex': ('3DSMax-Modeling', '047B00EC-D4E3-4D05-8FB7-220795D13874', 'max-ui-reference/editable-poly.md, Edit Vertices'),
    'poly_edge': ('3DSMax-Modeling', '2C16FF31-BF20-450F-8163-3362A7037603', 'max-ui-reference/editable-poly.md, Edit Edges'),
    'poly_face': ('3DSMax-Modeling', 'FF7D7633-03AD-4427-821A-65F8AC484CDD', 'max-ui-reference/editable-poly.md, Edit Polygons and Elements'),
    'caddy': ('3DSMax-Modeling', '0F0E1E2D-7F99-4EF5-B37C-7F486379CFD0', 'max-ui-reference/images/caddy-interface-2026.png'),
    'extrude': ('3DSMax-Modeling', '54BDC012-917F-471E-B083-F15D4FE12251', 'max-ui-reference/images/caddy-extrude-polygons-2026.png'),
    'chamfer': ('3DSMax-Modeling', 'FB852041-9E26-4F4A-9E17-154CD4CB504A', 'max-ui-reference/images/caddy-chamfer-2026.png'),
    'connect': ('3DSMax-Modeling', '57E3DDC9-50D2-4467-93E9-B1B103CEA30D', 'max-ui-reference/images/caddy-connect-2026.png'),
    'bridge': ('3DSMax-Modeling', '366DCE9C-FB42-47CB-A1ED-65129C95923E', 'max-ui-reference/images/caddy-bridge-2026.png'),
    'inset': ('3DSMax-Modeling', '03A55F03-35D3-4E15-80C5-9A8923569843', 'max-ui-reference/images/caddy-inset-2026.png'),
    'hinge': ('3DSMax-Modeling', '27325336-A2B6-42D4-BFE0-40491A72D98B', 'max-ui-reference/images/caddy-hinge-2026.png'),
    'smooth': ('3DSMax-Modeling', '44BA6ECC-EA8C-405B-8B52-4ABF9430A11C', 'references/mesh-smooth-caddy-04.png and mesh-smooth-caddy-06.png'),
    'relax': ('3DSMax-Modeling', '7E7FC066-7ED7-44B8-858A-5B9426E8715E', 'references/relax-caddy-04.png through relax-caddy-09.png'),
    'tessellate': ('3DSMax-Modeling', 'EAAAD139-33CD-4809-B03B-237533B6E98C', 'references/tessellate-caddy-04.png through tessellate-caddy-08.png'),
    'material': ('3DSMax-Lighting-Shading', '93E64F78-67A8-4DEA-9BF5-2F9A9098987B', 'references/material-tools-03.png through material-tools-24.png'),
    'time': ('3DSMax-Animation', '818205DD-D58A-495E-BD0C-DC69BDE8DAC2', 'references/time-00.png and time-02.png through time-14.png'),
    'viewport': ('3DSMax-Basics', 'F8326C68-F2F9-47F7-AC1D-BA41D7825C7C', 'max-ui-reference/images/interface-overview.png, bottom-right navigation controls'),
    'labels': ('3DSMax-Basics', 'BE30312F-5765-4BE1-9890-8CD5CAA4EFE5', 'max-ui-reference/images/interface-viewport.png'),
    'symmetry': ('3DSMax-Modifiers', 'EB0B7B9B-117D-4CC3-A966-A3E007E0C68A', 'references/symmetry-02.png through symmetry-04.png'),
}

def path(d, color=G, width=1, fill='none', **attrs):
    other = ''.join(f' {k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{width}"{other}/>'

def poly(points, fill=G, stroke='none', width=1):
    return f'<polygon points="{points}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'

def rect(x, y, w, h, fill='none', stroke=G, width=1, rx=0):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'

def circle(x, y, r, fill='none', stroke=G, width=1):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'

def ellipse(x, y, rx, ry, fill='none', stroke=G, width=1):
    return f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'

def group(body, transform):
    return f'<g transform="{transform}">{body}</g>'

def add(name, body, idea, section='toolbar', ref='toolbar', mode='icon-only', spot=None, note=''):
    if name in ART:
        raise ValueError('Duplicate drawing ' + name)
    ART[name] = body
    CAT.append(dict(name=name, section=section, idea=idea, reference=ref, presentation=mode,
                    spot=spot or section.replace('_', ' '), note=note,
                    baseline=name if name in BASELINE_NAMES else None))

def arrow(direction='right', color=G):
    a = poly('2,6 9,6 9,3 14,8 9,13 9,10 2,10', color)
    return group(a, {'right':'', 'left':'translate(16 0) scale(-1 1)', 'up':'translate(0 16) rotate(-90)', 'down':'translate(16 0) rotate(90)'}[direction])

def cursor(x=7, y=6, color=Y):
    return group(poly('0,0 0,9 2.5,6.5 4,10 6,9 4.5,5.5 8,5.5', color), f'translate({x} {y}) scale(.65)')

def magnet():
    return path('M11 2.5 V5 A2 2 0 0 0 15 5 V2.5', Y, 1.5) + path('M11 2.5 V4 M15 2.5 V4', G, 1.5)

def mesh():
    return path('M2.5 5.5 7.5 2.5 13.5 5.5 V11.5 L8.5 14.5 2.5 11.5 Z M2.5 5.5 8.5 8.5 13.5 5.5 M8.5 8.5 V14.5', D)

def cube(accent=None):
    return (poly('2.5,5 7.5,2 13.5,5.5 8.5,8.5', accent or '#a4a9ac', G) +
            poly('2.5,5 8.5,8.5 8.5,14 2.5,10.5', accent or F, G) +
            poly('8.5,8.5 13.5,5.5 13.5,11 8.5,14', accent or '#858b8e', G))

def plane():
    return poly('2,6.5 10.5,3 14,9.5 5.5,13', F, G) + path('M6 5 9.5 11.5 M3.5 9.5 12 6', D)

def dot(x, y, color=C):
    return rect(x-1, y-1, 2, 2, color, 'none')

def window(body):
    return rect(1.5, 2.5, 13, 11, F) + path('M1.5 5.5 H14.5 M3 4 H4 M5 4 H6 M7 4 H8', G) + body

def teapot():
    return (path('M4 6.5 H11 V9 C11 13.5 4 13.5 4 9 Z', G, 1, '#b6babc') +
            path('M4 7 C-1 5 0 12 5 10 M11 8 14 6 13 10 10.5 10', G, 1.3) +
            path('M5 5 H10 M7.5 3.5 V5', G, 1.2))

def settings_box():
    return rect(3.5, 3.5, 9, 9, F, G) + rect(5.5, 5.5, 5, 5, 'none', '#323638')

def toolbar():
    undo = path('M6 3 1 7 6 11 V8 H9 C13 8 13 12 9 12 H7 V14 H9 C16 14 16 6 9 6 H6 Z', 'none', 0, G)
    add('undo', undo, 'Broad bent arrow pointing left')
    add('redo', group(undo, 'translate(16 0) scale(-1 1)'), 'Broad bent arrow pointing right')
    link = path('M6 6 8 4 C11 1 15 5 12 8 L10 10 M6 6 4 8 C1 11 5 15 8 12 L10 10 M5.5 10.5 10.5 5.5', G, 1.7)
    add('link', link, 'Two interlocking objects linked diagonally')
    add('unlink', path('M7 4 8 3 C12 0 16 5 13 8 L12 9 M4 7 3 8 C0 12 5 16 8 13 L9 12', G, 1.7)+path('M3 2 6 5 M10 9 14 13', C, 1.7), 'Separated diagonal links with cyan break marks')
    waves = ''.join(path(f'M1 {y} Q3 {y+2} 5 {y} T9 {y} T13 {y}', G, 1.3) for y in (5,9,13))
    add('bind_space_warp', waves+group(link, 'translate(5 -1) scale(.65)'), 'Wavy space-warp bands with a binding link')
    add('selection_filter', poly('2,3 14,3 9,9 9,13 7,14 7,9', G), 'Filter list, All is text in Max', mode='text-only', note='Keep the All dropdown text. Candidate funnel is reserved, not a replacement for All.')
    add('select_object', rect(1.5, 1.5, 10, 11, G, 'none')+cursor(8,7), 'Grey selection tile and yellow pointer')
    add('select_by_name', ''.join(rect(1,y,11,2,G,'none') for y in (2,6,10))+cursor(8,7), 'Stacked list rows and yellow pointer')
    for name, outline, idea in [('region_rect',rect(2.5,2.5,10,10,'none',C),'Dotted rectangular selection boundary'),('region_circle',circle(7.5,7.5,5,'none',C),'Dotted circular selection boundary'),('region_fence',path('M2.5 13.5 V3.5 L13.5 5.5 10.5 12.5 7.5 8.5 Z',C),'Angular fence selection boundary')]:
        add(name, '<g stroke-dasharray="1 1">'+outline+'</g>', idea)
    add('window_crossing', '<g stroke-dasharray="2 1">'+rect(1.5,1.5,10,12,'none',G)+'</g>'+rect(7,6,7,7,C,'none'), 'Dashed window crossed by a filled cyan tile')
    cross = poly('8,1 11,4 9,4 9,7 12,7 12,5 15,8 12,11 12,9 9,9 9,12 11,12 8,15 5,12 7,12 7,9 4,9 4,11 1,8 4,5 4,7 7,7 7,4 5,4')
    add('move', cross, 'Solid four-way arrow cross')
    rotate = path('M11 2 V5 H8 L10 3 C3 1 0 10 6 13 C10 15 14 12 14 8', G, 2) + poly('8,1 13,3.5 9,6',G)
    add('rotate', rotate, 'Broad clockwise circular arrow')
    add('scale', rect(2,9,5,5,G,'none')+'<g stroke-dasharray="2 1">'+rect(2.5,2.5,11,11,'none',C)+'</g>'+path('M6 10 12 4',G,1.5)+poly('9,3 14,2 13,7',G), 'Small solid square expanding into dashed square')
    add('select_place', circle(6.5,9,5,G,'none')+ellipse(11,4.5,3,2.5,C,'none')+path('M8 8 11 5',Y,2), 'Object placed onto a target surface')
    add('reference_coords', path('M3.5 1.5 V12.5 H14 M3.5 12.5 10.5 5.5',D)+path('M3.5 9.5 V2',B,1.5)+poly('1,4 3.5,1 6,4',B)+path('M6 12.5 H13',R,1.5)+poly('11,10 15,12.5 11,15',R)+path('M5.5 10.5 10 6',GREEN,1.5), 'Coordinate axes, dropdown itself shows View text', mode='text-only',note='Keep the reference coordinate dropdown as text, no leading axis pictogram.')
    add('pivot', rect(2.5,2.5,3,7,G,'none')+rect(9.5,2.5,3,7,G,'none')+path('M4 9 V14 M2 12 H6 M11 9 V14 M9 12 H13',C), 'Two objects with cyan pivot crosses')
    glyphs = {
        '2': path('M2 4 C2 1 8 1 8 4 C8 6 2 7 2 10 H8', G,1.8),
        '3': path('M2 2 H8 L4.5 5.5 C10 5 10 10 5 10 H2', G,1.8),
    }
    for n,g in [('snap_2d',glyphs['2']),('snap_25d',group(glyphs['2'],'scale(.8) translate(0 2)')+circle(7.7,9,.75,G,'none')+path('M9.5 3 H12.5 V5 H10 V7 C14 6 14 10 10 10',G,1.2)),('snap_3d',glyphs['3'])]:
        add(n,g+magnet(), 'Large '+{'snap_2d':'2','snap_25d':'2.5','snap_3d':'3'}[n]+' with small gold magnet at upper right')
    add('snap_off', group(glyphs['3']+magnet(),'translate(0 0)')+path('M1.5 14.5 14.5 1.5',D,1.4), 'Same 3D snap symbol in disabled state',note='Prefer disabled UI tint of snap_3d in phase 2. This asset is the legacy name.')
    add('angle_snap', path('M2.5 3.5 V13.5 H12.5 M2.5 8 C6 8 8 10 8 13.5',G,1.5)+magnet(), 'Right angle and small gold magnet')
    add('percent_snap',circle(3.5,4,1.7)+circle(9,11.5,1.7)+path('M2 14 10 2',G,1.5)+magnet(), 'Percent sign and small gold magnet')
    add('spinner_snap',poly('1,7 4,2 7,7',G)+poly('1,9 7,9 4,14',G)+magnet(), 'Opposed spinner triangles with gold magnet')
    add('named_selection_sets',path('M5 2 C3 2 4 6 2 7.5 C4 9 3 13 5 13 M10 2 C12 2 11 6 13 7.5 C11 9 12 13 10 13',G,1.5)+path('M8 6 14 0',Y,2), 'Selection braces and editing pencil',note='Edit button icon-only. Adjacent Create Selection Set combo retains text.')
    add('mirror',poly('1.5,3 6,6 6,13 1.5,10',G)+poly('10,6 14.5,3 14.5,10 10,13',C)+path('M8 1 V15',G,1,stroke_dasharray='2 1'), 'Two opposed planes around dotted mirror axis')
    add('align',rect(2,2,4,3,G,'none')+rect(9,9,5,4,C,'none')+path('M1 7.5 H15 M7.5 1 V15',D)+path('M4 6 V10 M11 5 V8',G), 'Offset objects lined up to common axes')
    add('scene_explorer',window(''.join(rect(3,y,2,1.5,G,'none')+rect(7,y,5,1.5,G,'none') for y in (7,10))), 'Scene list in a compact window')
    layers=''.join(poly(f'4,{y} 8,{y-2} 12,{y} 8,{y+2}',G) for y in (7,9,11))
    add('layer_explorer',window(layers), 'Three stacked layers inside a window')
    add('ribbon',window(rect(3,7,4,2,G,'none')+rect(9,7,3,2,G,'none')+rect(3,11,4,1,G,'none')+rect(9,11,3,1,G,'none')), 'Panel blocks inside a ribbon window')
    add('curve_editor',window(path('M3 11 C4 4 7 6 8 10 S12 12 13 7',C,1.6)), 'Cyan animation curve in editor window')
    add('schematic_view',rect(2,2,12,3,G,'none')+arrow('down',C), 'Hierarchy bar and large downward cyan arrow')
    checker=circle(5.5,9.5,3,'none',G)+path('M3.5 7.5 7.5 11.5 M3.5 11.5 7.5 7.5 M2.5 9.5 H8.5 M5.5 6.5 V12.5',G)
    add('material_editor',window(checker+path('M10 7 H13 M10 9 H13 M10 11 H13',G)), 'Checker material sphere and settings rows in window')
    add('render_setup',teapot()+group(path('M8 1 V3 M8 13 V15 M1 8 H3 M13 8 H15 M3 3 4 4 M12 12 13 13 M3 13 4 12 M12 4 13 3',Y,2)+circle(8,8,4,'none',Y,1.5), 'translate(8 7) scale(.5)'), 'Teapot with small gold settings wheel')
    add('rendered_frame',window(group(teapot(),'translate(1 3) scale(.8)')), 'Teapot inside rendered frame window')
    add('render_production',teapot()+path('M12.5 1 V5 M10.5 3 H14.5',C,1.5), 'Teapot with small cyan production sparkle')

def command_panel():
    def a(n,b,i,ref='tabs',mode='icon-only',note=''):
        add(n,b,i,'command_panel',ref,mode,note=note)
    a('create',rect(7,1,2,14,G,'none')+rect(1,7,14,2,G,'none'),'Simple filled plus')
    arch=path('M3 12.5 Q4 3 12.5 3',G,2)+path('M3 2.5 H13.5 V13.5 H2.5 V3',C)
    arch+=''.join(rect(x,y,2,2,F,C) for x,y in ((1.5,1.5),(12.5,1.5),(1.5,12.5),(12.5,12.5)))
    a('modify',arch,'Curved modifier segment within cyan control cage')
    a('hierarchy',rect(5,1,6,3,G,'none')+path('M8 4 V8 M3 8 H13 M3 8 V11 M13 8 V11',C)+rect(1,11,4,3,C,'none')+rect(11,11,4,3,C,'none'),'Parent block branching to two cyan children')
    a('motion',path('M5 3 C0 3 0 13 5 13 M7 3 C2 3 2 13 7 13',C)+circle(10,8,5,G,'none'),'Disc with two cyan motion arcs')
    a('display',rect(1,2,14,9,G,'none')+rect(7,11,2,2,G,'none')+rect(4,13,8,1,G,'none'),'Solid monitor and short stand')
    wrench=path('M10 2 C6 1 5 5 8 7 L2 12 4 14 10 8 C14 10 16 6 14 3 L12 6 10 4 Z','none',0,G)
    a('utilities',wrench,'Open-ended spanner, not a hammer')
    a('geometry',circle(8,8,5.5,G,'none'),'Filled round geometry category','categories')
    a('shapes',rect(7,7,7,7,G,'none')+circle(6,6,4,'none',G,1.5),'Overlapping outlined circle and filled square','categories')
    bulb=path('M5 10 C1 5 4 1.5 8 1.5 C12 1.5 15 5 11 10 L10 12 H6 Z','none',0,G)+path('M6 13.5 H10 M7 15 H9',G)
    a('lights',bulb,'Filled light bulb and two base bars','categories')
    a('cameras',rect(1,4,9,8,G,'none')+poly('11,6 15,3 15,13 11,10',G),'Rectangular camera body and triangular lens','categories')
    a('helpers',poly('2,2 14,14 2,14',G)+poly('4,7 9,12 4,12','#44484a')+path('M2 6 H4 M2 9 H4 M2 12 H4',D),'Triangular set square with ruler marks','categories')
    a('space_warps',''.join(path(f'M1 {y} Q4 {y-3} 8 {y} T15 {y}',G,1.4) for y in (4,8,12)),'Three wavy horizontal bands','categories')
    gear=circle(4.5,4.5,2.5,'none',G,1.5)+circle(11,11,2.5,'none',G,1.5)+path('M4.5 .5 V2 M4.5 7 V8.5 M.5 4.5 H2 M7 4.5 H8.5 M11 7 V8.5 M11 13.5 V15 M7 11 H8.5 M13.5 11 H15',G)
    a('systems',gear,'Two small meshing gear wheels','categories')
    # Same mesh under every level makes the selected component legible.
    a('vertex',mesh()+dot(2.5,5.5)+dot(7.5,2.5)+dot(13.5,5.5)+dot(8.5,14.5),'Mesh corners highlighted as cyan square vertices','subobjects')
    a('edge',mesh()+path('M2.5 5.5 7.5 2.5 13.5 5.5',C,1.7),'Two connected edges highlighted on a small mesh','subobjects')
    a('border',mesh()+path('M2.5 5.5 8.5 8.5 13.5 5.5 7.5 2.5 Z',C,1.5),'Closed open-boundary loop highlighted on mesh','subobjects')
    a('polygon',mesh()+poly('2.5,5.5 8.5,8.5 8.5,14.5 2.5,11.5',C,C),'One polygon highlighted on a small mesh','subobjects')
    a('element',cube(C),'Whole connected mesh element highlighted','subobjects')
    a('editable_poly',mesh()+''.join(rect(x-1,y-1,2,2,F,C) for x,y in [(2.5,5.5),(7.5,2.5),(13.5,5.5),(8.5,14.5)]),'Editable mesh control cage','stack',mode='icon plus text',note='Stack row retains Editable Poly text. Level buttons are icon-only.')
    a('pin_stack',path('M5 4 H11 M6 4 V9 L4 11 H12 L10 9 V4 M8 11 V15',G,1.3),'Pushpin locking the modifier stack','stack')
    a('show_end_result',poly('5,1 11,1 10,6 9,8 10,10 11,15 5,15 6,10 7,8 6,6',G)+path('M6 3 H10 M6 13 H10',F),'Narrow hourglass for result through stack','stack')
    a('make_unique',path('M3 3 6 13 8 9 10 13 13 3',G,1.4)+path('M5 2 V5 M11 2 V5',D),'Forked unique-instance symbol','stack')
    a('remove_modifier',path('M3 4 H13 M5 4 V2 H11 V4 M4 4 V14 H12 V4 M6.5 6 V12 M9.5 6 V12',G,1.2),'Trash can with vertical slats','stack')
    a('configure_modifier_sets',rect(2.5,2.5,10,11,F,G)+path('M4 5 H9 M4 8 H8 M4 11 H7',G)+path('M8 8 14 2',Y,2),'Modifier list with editing pencil','stack')
    a('modifier_list',path('M2 3.5 H12 M2 7.5 H10 M2 11.5 H7',G,1.5)+poly('9,10 15,10 12,14',G),'Modifier list is a labelled dropdown','stack','text-only',note='Keep Modifier List text. Do not append a separate list pictogram to the dropdown.')
    eye=path('M1 8 Q8 1 15 8 Q8 15 1 8 Z',G,1,G)+circle(8,8,2.5,'#44484a','none')
    a('bulb_on',eye,'Visible eye for enabled modifier, not a light bulb','stack')
    a('bulb_off',path('M1 8 Q8 1 15 8 Q8 15 1 8 Z','none',0,F),'Dim eye for disabled modifier','stack')
    a('edit_mode',mesh()+path('M8 10 14 4',Y,2),'Editable cage with pencil, Blender-specific toggle','stack',note='No exact Max control. Keep legacy toggle tooltip explicit.')
    a('settings',settings_box(),'Small inset square settings button','caddy')
    a('up',poly('3,11 8,5 13,11',G),'Small upward triangle','stack')
    a('down',poly('3,5 13,5 8,11',G),'Small downward triangle','stack')
    a('check',path('M3 8 6.5 11.5 13 4',G,1.8),'Check mark for selected menu state','labels')
    a('close',path('M4 4 12 12 M4 12 12 4',G,1.6),'Small diagonal close cross','caddy')

def create_objects():
    def a(n,b,i,ref='primitives',note=''):
        add(n,b,i,'create_objects',ref,'text-only','Create > Object Type',note=note or 'Max uses a named object button here. Drawing is reserved for menus or a future approved icon placement.')
    a('box',cube(),'Simple isometric box')
    sphere=circle(8,8,5.5,F,G)+ellipse(8,8,2.5,5.5,'none',D)+ellipse(8,8,5.5,2,'none',D)
    a('sphere',sphere,'Latitude and longitude sphere')
    a('geosphere',poly('8,1.5 13.5,5 12,12 4,13.5 1.5,6',F,G)+path('M8 1.5 5.5 7 13.5 5 9 10.5 8 1.5 M5.5 7 4 13.5 9 10.5 12 12 M1.5 6 5.5 7',G),'Triangular geodesic sphere')
    cylinder=path('M3 5 V11 C3 15 13 15 13 11 V5',G,1,F)+ellipse(8,5,5,2.5,'#a4a9ac',G)
    a('cylinder',cylinder,'Vertical cylinder with elliptical cap')
    a('tube',cylinder+ellipse(8,5,2.5,1.2,'#44484a',G),'Cylinder with open centre')
    a('cone',path('M2 12 6 2 H10 L14 12 Z',G,1,F)+ellipse(8,12,6,2,'#858b8e',G)+ellipse(8,2.5,2,.8,'#a4a9ac',G),'Frustum cone with separate cap and base')
    torus=ellipse(8,8,6,4,F,G)+ellipse(8,7,3,1.5,'#44484a',G)+path('M2 8 C2 14 14 14 14 8',G)
    a('torus',torus,'Thick ring with clear centre hole')
    a('pyramid',poly('8,1.5 2,12 8,14.5 14,12',F,G)+path('M8 1.5 V14.5 M2 12 8 10 14 12',G),'Square-based pyramid')
    a('plane',plane(),'Subdivided flat construction plane')
    a('planeplus',plane()+poly('11,1 13,1 13,3 15,3 15,5 13,5 13,7 11,7 11,5 9,5 9,3 11,3',C),'Plane plus marker for Nathan\'s custom PlanePlus',note='PlanePlus is Nathan\'s third-party tool, not a stock Max icon. Keep PlanePlus text.')
    a('teapot',teapot(),'Classic teapot primitive')
    a('hedra',poly('8,1 14,5 12,13 4,13 1,6',F,G)+path('M8 1 5 6 14 5 8 10 4 13 M5 6 1 6 M5 6 8 10 12 13',G),'Faceted multi-faced hedron','extended')
    a('torus_knot',path('M5 5 C2 0 11 0 12 5 C15 10 9 16 5 13 C0 13 0 6 5 5 C10 2 16 7 12 11 C9 16 3 11 5 5 Z',G,1.6)+path('M5 7 6 9 M10 4 11 6',F,2),'Interwoven closed torus knot','extended')
    a('chamferbox',poly('5,2 11,2 14,5 14,11 10,14 4,13 2,10 2,5',F,G)+path('M5 2 4 5 10 7 14 5 M4 5 4 11 10 14 M10 7 V12 M4 11 10 12 14 9',G),'Box with visibly bevelled corners','extended')
    a('chamfercyl',path('M3 4 2 6 V11 L4 14 H12 L14 11 V6 L13 4',G,1,F)+ellipse(8,4,5,2,'#a4a9ac',G)+path('M2 6 Q8 10 14 6 M4 12 Q8 14 12 12',G),'Cylinder with sloping bevel bands','extended')
    a('oiltank',path('M3 5 C3 1 13 1 13 5 V11 C13 15 3 15 3 11 Z',G,1,F)+path('M3 5 Q8 8 13 5 M3 11 Q8 14 13 11',G),'Tank with shallow convex end caps','extended')
    a('capsule',rect(3.5,1.5,9,13,F,G,1,4.5)+path('M3.5 6 Q8 8 12.5 6 M3.5 10 Q8 12 12.5 10',D),'Capsule with hemispherical ends','extended')
    a('spindle',poly('8,1 13,5 13,11 8,15 3,11 3,5',F,G)+path('M3 5 Q8 8 13 5 M3 11 Q8 14 13 11',G),'Spindle with pointed end caps','extended')
    a('l_ext',poly('2,3 6,2 6,9 13,9 14,12 10,14 2,11',F,G)+path('M2 3 5 5 V11 L14 12 M5 11 2 11 M5 5 6 2',G),'Extruded L-section','extended')
    a('c_ext',poly('3,2 13,2 13,5 6,5 6,10 13,10 13,13 3,13',F,G)+path('M3 2 1.5 4 V14.5 H11.5 L13 13 M1.5 4 H3 M1.5 14.5 3 13',G),'Extruded C-section','extended')
    a('gengon',poly('5,2 11,2 14,5 14,11 11,14 5,14 2,11 2,5',F,G)+path('M5 2 5 9 11 9 14 5 M2 5 5 9 2 11 M5 9 5 14 M11 9 11 14',G),'Rounded polygonal prism','extended')
    a('prism',poly('2,11 7,2 14,10 10,14',F,G)+path('M7 2 10 14 M2 11 10 14 M7 2 12 1 15 9 14 10',G),'Triangular prism with depth','extended')
    a('ringwave',ellipse(8,9,6,4,'none',G,1.5)+ellipse(8,8,3,2,'none',G)+path('M2 8 Q5 2 8 7 T14 8',C),'Concentric rippled ring','extended')
    a('hose',path('M3 14 C3 3 13 14 13 2',G,4)+path('M2 11 6 10 M4 8 7 9 M7 8 9 12 M10 8 14 9 M11 5 15 6',D),'Corrugated flexible hose','extended')
    a('spring',path('M6 1 C17 1 0 6 6 6 C17 6 0 11 6 11 C17 11 0 15 7 15',G,1.6),'Helical wire spring','extended')
    a('damper',rect(5,5,6,9,F,G)+path('M8 1 V5 M5 1 H11 M5 15 H11',G,1.5),'Piston rod entering damper housing','extended')
    spline_bodies={
        'line':path('M2.5 12.5 5.5 4.5 10.5 10.5 13.5 2.5',G,1.3)+dot(2.5,12.5)+dot(5.5,4.5)+dot(10.5,10.5)+dot(13.5,2.5),
        'rectangle':rect(2.5,4.5,11,7), 'circle':circle(8,8,5.5),
        'ellipse':ellipse(8,8,6,3.5), 'arc':path('M2 12 A6 6 0 0 1 12 3',G,1.4)+dot(2,12)+dot(12,3),
        'ngon':poly('8,1.5 14,6 11.5,13.5 4.5,13.5 2,6','none',G),
        'star':poly('8,1 10,5.5 15,6 11,9.5 12,15 8,12 4,15 5,9.5 1,6 6,5.5','none',G),
        'text':path('M2 3 H14 M8 3 V13 M5 13 H11',G,1.5),
        'helix':path('M3 13 C16 13 16 7 4 8 C-4 8 3 2 13 3 M3 10 C16 10 16 4 4 5',G,1.3),
        'donut':circle(8,8,6)+circle(8,8,3),
        'egg':path('M8 1 C10 1 14 8 14 10 C14 16 2 16 2 10 C2 8 6 1 8 1 Z'),
        'section':plane()+path('M2 10 14 5',C,1.5),
        'freehand':path('M2 11 C0 1 8 1 6 8 S15 15 14 3',G,1.4),
    }
    for n,b in spline_bodies.items():
        a(n,b,{'line':'Angled connected spline with square knots','helix':'Open coiled spline'}.get(n,n.replace('_',' ').capitalize()+' spline outline'),'splines')
    light_bodies={
        'omni':circle(8,8,3,'none',G,1.3)+path('M8 1 V3 M8 13 V15 M1 8 H3 M13 8 H15 M3 3 4.5 4.5 M11.5 11.5 13 13 M3 13 4.5 11.5 M11.5 4.5 13 3',G),
        'free_spot':poly('8,2 2,13 14,13','none',G)+circle(8,2,1.5,G,'none')+path('M8 4 V10',D),
        'free_direct':rect(4.5,2.5,7,3)+path('M5 6 V13 M8 6 V13 M11 6 V13',G)+poly('3,11 5,15 7,11',G)+poly('9,11 11,15 13,11',G),
        'skylight':path('M2 12 A6 6 0 0 1 14 12 Z M8 1 V3 M2 3 4 5 M14 3 12 5',G,1.3),
        'area':poly('3,3 14,5 11,10 1,8','none',G)+path('M4 10 3 14 M8 11 7 15 M12 11 11 15',G),
    }
    for n,b in light_bodies.items():
        a(n,b,{'omni':'Radial omnidirectional light','free_spot':'Untargeted spotlight cone','free_direct':'Parallel directional-light arrows','skylight':'Hemispherical sky dome','area':'Rectangular area emitter'}[n],note='Create light buttons retain their Max names. No pictogram in the Object Type rollout.')
    for n,source in [('target_spot','free_spot'),('target_direct','free_direct')]:
        a(n,light_bodies[source]+path('M8 10 V15 M6 14 H10',C),source.replace('free_','Targeted ')+' with target cross')
    for n,source in [('light_spot','free_spot'),('light_sun','free_direct'),('light_area','area')]:
        a(n,light_bodies[source],source.replace('_',' ')+' alias for Blender light data',note='Legacy Blender light-data name. Max Object Type controls retain text.')
    a('dummy',cube(),'Wire-box dummy helper')
    a('point',path('M8 1 V15 M1 8 H15 M3 3 13 13 M3 13 13 3',G),'Crossed point helper axes')
    a('bone',poly('3,3 6,2 13,11 12,14 9,13 2,6',F,G)+path('M3 3 9 8 13 11 M6 2 9 8 12 14',G),'Tapered bone with distinct joints')
    a('loft',path('M3 12 C3 1 13 15 13 3',D,3)+ellipse(3,12,2,1,'none',C)+ellipse(8,8,3,1.5,'none',G)+ellipse(13,3,2,1,'none',C),'Profile sections following a loft path',note='Loft is a text button under Compound Objects. This asset replaces the unrelated geometry sphere only where an icon is appropriate.')

def material():
    checker=circle(6,6,4,G,G)+path('M3 3 9 9 M3 9 9 3 M2 6 H10 M6 2 V10',F,1.5)
    def a(n,b,i,mode='icon-only',note=''):
        add(n,b,i,'material','material',mode,'Compact Material Editor toolbar',note=note)
    a('mtl_get',path('M2 8 V2 H10',C,2)+checker,'Material sphere entering editor')
    a('mtl_assign',checker+path('M10 5 V11 H13',C,2)+poly('10,10 14,10 12,14',C)+rect(11,13,3,2,G,'none'),'Checker material assigned to selected object')
    a('mtl_reset',path('M3 4 H13 M5 4 V14 H11 V4 M6 2 H10',G,1.5),'Trash can resets material slot')
    a('mtl_select',checker+cursor(8,7),'Checker material sphere and selection pointer')
    a('mtl_pick',path('M3 12 11 4',G,2)+path('M9 3 12 6 M2 13 4 14',G,1.3)+poly('10,2 12,1 15,4 14,6',G),'Material eyedropper with diagonal stem')
    a('mtl_viewport',rect(2.5,2.5,11,11,F,C)+checker,'Checker material tile for viewport display')
    a('mtl_library',rect(2.5,1.5,11,13,F,G)+rect(5,2,6,4,G,'none')+path('M5 10 H11 M5 12 H11',G),'Save material into library')
    a('mtl_drag',checker+path('M10 7 H15 M12 5 15 7 12 9',C,1.4),'Material sphere moved to sibling slot',note='Legacy custom drag action has no exact Max toolbar counterpart. Use tooltip, do not invent a stock Max claim.')
    a('bitmap',rect(1.5,2.5,13,11,F,G)+poly('2,12 6,6 9,10 11,7 14,12',G)+circle(11,5,1,C,'none'),'Image tile with mountains and small light')
    a('search',circle(6.5,6.5,4)+path('M9.5 9.5 14 14',G,1.7),'Magnifying glass for search',mode='icon plus text',note='Keep Search Modifiers text in the command menu.')
    a('measure',poly('2,2 14,14 2,14','none',G)+path('M2 6 H4 M2 9 H5 M2 12 H4',G),'Triangular ruler',mode='text-only',note='Utilities Measure is a named button in Max.')

def poly_tools():
    """Reserve symbols, but retain Max's text buttons in these placements."""
    drawings = {
        'extrude':mesh()+poly('5,5 10,3 13,5 8,7',C)+path('M5 5 V2 M10 3 V1 M13 5 V2',G),
        'bevel':poly('2,11 6,13 14,9 11,3 6,2 3,5',F,G)+poly('3,5 6,2 11,3 8,6',C)+path('M3 5 6 13 M8 6 6 13 M11 3 14 9',G),
        'inset':poly('2,3 14,3 14,13 2,13',F,G)+poly('5,5 11,5 11,11 5,11',C,G)+path('M2 3 5 5 M14 3 11 5 M14 13 11 11 M2 13 5 11',G),
        'outline':rect(2.5,2.5,11,11,'none',G)+rect(5.5,5.5,5,5,'none',C)+path('M1 8 H5 M11 8 H15',G),
        'chamfer':path('M2.5 13.5 V6.5 L6.5 2.5 H13.5 M2.5 6.5 6.5 6.5 6.5 2.5',G,1.5)+path('M2.5 6.5 6.5 2.5',C,2),
        'connect':rect(2.5,2.5,11,11,'none',D)+path('M6 2.5 V13.5 M10 2.5 V13.5',C,1.5)+path('M2.5 8 H13.5',G),
        'bridge':rect(1.5,3.5,3,9,'none',G)+rect(11.5,3.5,3,9,'none',G)+path('M4.5 3.5 11.5 3.5 M4.5 8 H11.5 M4.5 12.5 H11.5',C),
        'weld':path('M2 3 8 8 14 3 M2 13 8 8 14 13',G)+dot(8,8)+path('M3 6 5 8 3 10 M13 6 11 8 13 10',C),
        'target_weld':path('M2 2 12 12 M2 12 12 2',D)+dot(2,2,G)+dot(12,12,C)+path('M5 5 9 9',C,1.8)+poly('7,10 11,11 10,7',C),
        'remove':mesh()+path('M3 3 13 13 M3 13 13 3',R,1.8),
        'remove_with_verts':mesh()+path('M3 3 13 13 M3 13 13 3',R,1.8)+dot(13,3,R),
        'break':path('M2 2 6 6 M10 10 14 14 M2 14 6 10 M10 6 14 2',G)+dot(6,6,C)+dot(10,10,C),
        'split':rect(1.5,2.5,5,11,'none',G)+rect(9.5,2.5,5,11,'none',C)+path('M7.5 1 V15',D,1,stroke_dasharray='1 1'),
        'cap':mesh()+poly('2.5,5.5 7.5,2.5 13.5,5.5 8.5,8.5',C,G),
        'flip':plane()+path('M8 7 V1',C,1.5)+poly('5,4 8,1 11,4',C),
        'detach':cube()+group(cube(C),'translate(7 -1) scale(.55)'),
        'collapse':path('M2 2 7 7 M14 2 9 7 M2 14 7 9 M14 14 9 9',G)+dot(8,8,C),
        'relax':path('M2 12 5 3 9 11 14 4',D)+path('M2 11 Q5 4 9 9 T14 5',C,1.6),
        'msmooth':rect(2.5,2.5,11,11,'none',G,1,3)+path('M8 2.5 V13.5 M2.5 8 H13.5',C),
        'tessellate':rect(2.5,2.5,11,11,'none',G)+path('M2.5 2.5 13.5 13.5 M13.5 2.5 2.5 13.5',C),
        'make_planar':path('M1 12 H15 M3 2 V7 M8 4 V7 M13 1 V7',G)+poly('1,6 5,6 3,10',C)+poly('6,6 10,6 8,10',C)+poly('11,6 15,6 13,10',C),
        'slice_plane':mesh()+poly('1,9 10,4 15,6 6,11','none',C),
        'cut':mesh()+path('M1 12 14 3',C,1.7)+dot(1,12,G)+dot(14,3,G),
        'loop':rect(2.5,2.5,11,11,'none',D)+path('M2.5 7.5 H13.5 M2.5 4 H13.5 M2.5 11 H13.5',G)+path('M7.5 2.5 V13.5',C,1.7),
        'ring':rect(2.5,2.5,11,11,'none',D)+path('M5 2.5 V13.5 M8 2.5 V13.5 M11 2.5 V13.5',C,1.3),
        'grow':rect(4.5,4.5,7,7,'none',G)+path('M2 8 H14 M8 2 V14',C,1.6),
        'shrink':rect(4.5,4.5,7,7,'none',G)+path('M2 8 H14',C,1.6),
        'insert_vertex':path('M2 13 14 3',G,1.5)+dot(8,8,C)+path('M11 12 H15 M13 10 V14',C),
        'create_shape':path('M2.5 12.5 6.5 3.5 13.5 9.5',C,1.5)+dot(2.5,12.5,G)+dot(6.5,3.5,G)+dot(13.5,9.5,G),
        'retriangulate':rect(2.5,2.5,11,11,'none',G)+path('M2.5 2.5 13.5 13.5 M13.5 2.5 8 8 2.5 13.5',C),
        'turn':rect(2.5,2.5,11,11,'none',D)+path('M2.5 2.5 13.5 13.5',G,1,stroke_dasharray='2 1')+path('M2.5 13.5 13.5 2.5',C,1.7),
        'edit_triangulation':rect(2.5,2.5,11,11,'none',G)+path('M2.5 13.5 13.5 2.5',C)+cursor(8,7),
        'hinge':plane()+path('M3 11 V3 L12 1 V7',C,1.4)+dot(3,11,G)+dot(12,7,G),
        'spline_extrude':path('M2 14 C1 3 14 14 14 2',C,2)+group(plane(),'translate(-1 5) scale(.65)'),
        'view_align':rect(2.5,2.5,11,8,'none',G)+path('M4 14 H12 M8 10.5 V14',G)+path('M4 6 H12',C,2),
        'grid_align':plane()+path('M2 2 14 14',C,1.5),
        'create_poly':mesh()+path('M10 1 V7 M7 4 H13',C,1.5),
        'quick_slice':mesh()+path('M1 12 14 3',C,1.8),
        'slice':mesh()+path('M1 8 H15',C,1.8),
        'reset_plane':plane()+path('M2 3 C7 -1 14 2 14 6',G,1.4)+poly('11,5 15,5 14,9',G),
        'attach':cube()+path('M12 1 V7 M9 4 H15',C,1.4),
        'copy_selection':rect(2.5,2.5,8,8,'none',D)+rect(5.5,5.5,8,8,'none',G),
        'paste_selection':rect(3.5,3.5,9,11,'none',G)+rect(6,1.5,4,3,C,'none'),
        'select_angle':path('M2 2 V13 H14 M2 13 13 3 M6 13 A4 4 0 0 0 5 10',G)+dot(13,3,C),
        'open_edges':mesh()+path('M2.5 5.5 7.5 2.5 13.5 5.5',C,1.7),
        'delete_isolated':mesh()+dot(14,1,C)+path('M11 1 15 5 M11 5 15 1',R),
        'remove_unused_map':rect(2.5,2.5,9,9,'none',G)+dot(14,13,C)+path('M12 11 15 14 M12 14 15 11',R),
        'hide_sel':path('M1 8 Q8 1 15 8 Q8 15 1 8 Z',G)+path('M2 14 14 2',D,1.5),
        'hide_unsel':path('M1 8 Q8 1 15 8 Q8 15 1 8 Z',D)+circle(8,8,2,C,'none'),
        'unhide':path('M1 8 Q8 1 15 8 Q8 15 1 8 Z',G)+circle(8,8,2,C,'none'),
    }
    drawings['swift_loop']=drawings['loop']+path('M12 1 9 6 H13 L10 11',Y,1.3)
    for axis,color in [('x',R),('y',GREEN),('z',B)]:
        drawings['planar_'+axis]=drawings['make_planar']+dot(14,2,color)
    for mode in ('ring','loop'):
        for direction in ('up','down'):
            drawings[mode+'_shift_'+direction]=drawings[mode]+group(arrow(direction,C),'translate(9 8) scale(.45)')
    for n,body in drawings.items():
        ref='poly_vertex' if n in {'weld','target_weld','break','delete_isolated','remove_unused_map'} else 'poly_edge' if n in {'chamfer','connect','bridge','split','create_shape','insert_vertex'} else 'poly_face' if n in {'bevel','inset','outline','hinge','spline_extrude','flip','turn','retriangulate'} else 'poly'
        add(n,body,n.replace('_',' ').capitalize()+' mesh metaphor','editable_poly',ref,'text-only','Editable Poly rollout and quad command',note='Max uses text at this spot. Keep the command label. Drawing is reserved, not authority to add a leading icon.')

def caddies():
    # Field icons have no field-name text in Max, only the value or dropdown.
    vbar=path('M4.5 2.5 V13.5 M11.5 2.5 V13.5 M3 2.5 H6 M10 2.5 H13 M3 13.5 H6 M10 13.5 H13',G)+path('M8 4 V12',C,1.5)
    width=path('M2.5 4 V12 M13.5 4 V12 M2.5 8 H13.5',G)+path('M5 6 2.5 8 5 10 M11 6 13.5 8 11 10',C)
    field={
        'distance':(vbar,'Measured separation between two ends','extrude'),
        'height':(vbar,'Vertical extrusion-height gauge','extrude'),
        'type':(rect(2.5,2.5,11,11,'none',G)+path('M6 2.5 V13.5 M10 2.5 V13.5 M2.5 6 H13.5 M2.5 10 H13.5',C),'Grouped mesh patches for extrusion mode','extrude'),
        'bias':(poly('6,3 10,3 12,13 4,13',F,G)+path('M8 12 V2',C)+poly('6,4 8,1 10,4',C),'Local normal or shifted centre bias','extrude'),
        'width':(width,'Opposed arrows measuring base width or pinch','connect'),
        'weld':(path('M2 3 8 8 14 3 M2 13 8 8 14 13',G)+dot(8,8,C),'Points converging at weld threshold','poly_vertex'),
        'segments':(rect(2.5,2.5,11,11,'none',G)+path('M6 2.5 V13.5 M10 2.5 V13.5 M2.5 8 H13.5',C),'Mesh divided into several segments','connect'),
        'open':(rect(2.5,2.5,11,11,'none',G)+rect(5,5,6,6,F,'none'),'Open chamfer centre','chamfer'),
        'tension':(path('M2 13 C2 5 14 11 14 3',C,1.5)+dot(2,13,G)+dot(14,3,G),'Curved edge with endpoint tension','tessellate'),
        'taper':(poly('6,2 10,2 14,14 2,14','none',G)+path('M5 8 H11',C),'Narrow top widening to a broad base','bridge'),
        'smooth':(circle(8,8,5.5,'none',G)+path('M8 2.5 V13.5 M2.5 8 H13.5',C),'Rounded subdivided surface for smoothing','smooth'),
        'twist':(path('M3 2 C14 2 2 14 13 14 M13 2 C2 2 14 14 3 14',G)+path('M3 2 H13 M3 14 H13',C),'Crossing twisted boundary strips','bridge'),
        'relax':(path('M2 12 5 3 9 11 14 4',D)+path('M2 11 Q5 5 9 9 T14 5',C,1.5),'Smoothed profile between mesh points','relax'),
        'hold':(rect(2.5,2.5,11,11,'none',G)+path('M6 2.5 V13.5 M10 2.5 V13.5 M2.5 6 H13.5 M2.5 10 H13.5',D)+dot(2.5,2.5,C)+dot(13.5,2.5,C)+dot(2.5,13.5,C)+dot(13.5,13.5,C),'Pinned boundary points on a subdivided mesh','relax'),
        'pick':(circle(8,8,4.5,'none',G)+circle(8,8,1.5,C,'none'),'Circular pick target','bridge'),
        'material':(rect(2.5,2.5,11,11,'none',G)+rect(3,3,5,5,C,'none')+rect(8,8,5,5,C,'none'),'Alternating material regions','smooth'),
        'chamfer':(path('M2.5 13.5 V6.5 L6.5 2.5 H13.5',G,1.5)+path('M2.5 6.5 6.5 2.5',C,2),'Bevelled corner amount','chamfer'),
    }
    for n,(body,idea,ref) in field.items():
        add('caddy_'+n,body,idea,'caddies',ref,'icon-only','Caddy field label',note=f"poly_caddies.LABELS kind '{n}'. Field name belongs in hover title or tooltip, numeric value stays visible.")
    aliases={
        'amount':'distance','extrusion_type':'type','bevel_type':'type','local_bias':'bias','base_width':'width',
        'threshold':'weld','tess_tension':'tension','twist1':'twist','twist2':'twist','bridge_selection':'type',
        'pinch':'width','slide':'bias','smoothness':'smooth','tessellate_type':'segments',
        'iterations':'segments','hold_boundary':'hold','hold_outer':'hold','individual':'type',
        'pick1':'pick','pick2':'pick','separate_smoothing':'smooth','separate_materials':'material',
    }
    for n,kind in aliases.items():
        body,idea,ref=field[kind]
        if n in {'pick1','pick2','twist1','twist2'}:
            body+=rect(12,11,1,3,C,'none')
            if n.endswith('2'):
                body+=rect(14,11,1,3,C,'none')
        add('caddy_'+n,body,idea+' ('+n.replace('_',' ')+')','caddies',ref,'icon-only','Caddy '+n.replace('_',' '),note=f"Exact pending branch field key '{n}'. Maps to kind '{kind}'.")
    add('caddy_weld_counts',path('M1 4 H6 M1 8 H6 M10 4 H15 M10 8 H15',G)+path('M7 6 H10 M8 4 10 6 8 8',C),'Before and after count comparison','caddies','poly_vertex','text-only','Weld caddy Before / After counts',note='Max shows Before and After text. This reserved asset must not replace those counts.')
    add('caddy_ok',circle(8,8,6,F,G)+path('M4 8 7 11 12 5',GREEN,1.7),'Circular OK check','caddies','caddy',spot='Caddy footer OK (Enter)')
    add('caddy_apply',circle(8,8,6,F,G)+path('M4 8 H12 M8 4 V12',GREEN,1.7),'Circular Apply and Continue plus','caddies','caddy',spot='Caddy footer Apply and Continue (Ctrl+Enter)')
    add('caddy_cancel',circle(8,8,6,F,G)+path('M5 5 11 11 M5 11 11 5',R,1.7),'Circular Cancel cross','caddies','caddy',spot='Caddy footer Cancel (Esc)')
    # Choice flyouts must change their pictogram instead of printing Group/Local.
    for name,body,idea in [
        ('group',rect(2.5,2.5,11,11,'none',C)+path('M6 2.5 V13.5 M10 2.5 V13.5 M2.5 6 H13.5 M2.5 10 H13.5',G),'Single connected group of polygons'),
        ('local',mesh()+path('M4 7 2 2 M10 7 14 2',C,1.5),'Separate local normal directions'),
        ('polygon',rect(2,2,5,5,C,'none')+rect(9,2,5,5,C,'none')+rect(2,9,5,5,C,'none')+rect(9,9,5,5,C,'none'),'Separated polygons'),
        ('edge',rect(2.5,2.5,11,11,'none',G)+path('M8 2.5 V13.5 M2.5 8 H13.5',C,1,stroke_dasharray='1 1'),'Edge-centre tessellation'),
        ('face',rect(2.5,2.5,11,11,'none',G)+path('M2.5 2.5 13.5 13.5 M13.5 2.5 2.5 13.5',C),'Face-centre tessellation'),
    ]:
        add('caddy_type_'+name,body,idea,'caddies','tessellate' if name in {'edge','face'} else 'extrude','icon-only','Caddy mode flyout',note='Choice name appears on hover, not printed beside this pictogram.')

def navigation_and_features():
    def a(n,b,i,ref='viewport',mode='icon-only',spot=None,note=''):
        add(n,b,i,'navigation',ref,mode,spot,note)
    lens=circle(6.5,6.5,4)+path('M9.5 9.5 14 14',G,1.7)
    a('zoom',lens,'Magnifying glass for viewport zoom')
    a('zoom_all',lens+path('M4 6.5 H9 M6.5 4 V9',C),'Magnifier with multiple-view cross')
    a('zoom_extents',path('M1.5 6 V1.5 H6 M10 1.5 H14.5 V6 M1.5 10 V14.5 H6 M10 14.5 H14.5 V10',G)+cube(C),'Object within four framing corners')
    a('zoom_extents_all',path('M1.5 6 V1.5 H6 M10 1.5 H14.5 V6 M1.5 10 V14.5 H6 M10 14.5 H14.5 V10 M8 2 V14 M2 8 H14',G),'Four viewport extents framed together')
    a('zoom_region',lens+'<g stroke-dasharray="1 1">'+rect(1.5,1.5,9,9,'none',C)+'</g>','Magnifier within dotted zoom boundary')
    hand=path('M4 8 V4 C4 3 6 3 6 4 V7 M6 7 V2 C6 1 8 1 8 2 V7 M8 7 V3 C8 2 10 2 10 3 V8 M10 8 V5 C10 4 12 4 12 5 V10 C12 15 7 16 5 13 L2 9 C1 7 3 7 4 8 Z',G,1,F)
    a('pan',hand,'Open hand for panning')
    a('orbit',ellipse(8,8,7,3,'none',C)+ellipse(8,8,3,7,'none',G)+poly('10,2 14,3 11,6',C),'Intersecting orbital paths and arrow')
    a('maximize_viewport',rect(2.5,2.5,11,11,'none',G)+path('M8 4 H12 V8 M12 4 4 12',G,1.5),'Viewport frame and diagonal maximize arrow')
    a('viewport_general',path('M4 4 V12 M1 8 H7',G)+path('M10 2 H14 V14 H10',G),'Bracketed plus viewport menu',ref='labels',mode='text-only',spot='Viewport label [+]',note='Draw [+] as live text. Asset is reserved and must not replace the label.')
    a('viewport_view',cube(),'Point-of-view menu',ref='labels',mode='text-only',spot='Viewport label [Perspective]',note='Keep active view name text.')
    a('viewport_shading',circle(8,8,5.5,G,G)+path('M8 2.5 A5.5 5.5 0 0 0 8 13.5 Z','none',0,F),'Shading label menu',ref='labels',mode='text-only',spot='Viewport label [Default Shading]',note='Keep shading mode text.')
    a('play',poly('4,2 14,8 4,14',G),'Solid playback triangle','time')
    a('pause',rect(4,2,3,12,G,'none')+rect(9,2,3,12,G,'none'),'Parallel stop or pause bars','time')
    a('time_start',rect(1,2,2,12,G,'none')+poly('4,8 9,3 9,13',G)+poly('9,8 14,3 14,13',G),'Start bar and two backward triangles','time')
    a('time_end',rect(13,2,2,12,G,'none')+poly('2,3 7,8 2,13',G)+poly('7,3 12,8 7,13',G),'Two forward triangles and end bar','time')
    a('previous_frame',poly('2,8 8,2 8,14',G)+rect(10,2,2,12,G,'none')+rect(13,2,1,12,G,'none'),'Previous-frame triangle with key bars','time')
    a('next_frame',poly('8,2 14,8 8,14',G)+rect(4,2,2,12,G,'none')+rect(2,2,1,12,G,'none'),'Next-frame triangle with key bars','time')
    key=circle(4,5,3,'none',G,1.5)+path('M6 7 13 14 M9 10 11 8 M11 12 13 10',C,2)
    a('key',key,'Key symbol for setting animation keys','time',note='Standalone Set Keys icon is icon-only. Auto Key and Set Key mode buttons retain their text.')
    a('record',rect(2,3,12,10,R,'none')+path('M4 8 H12 M8 4 V12',G),'Auto Key mode button','time','text-only','Auto Key mode',note='Use Auto Key text with state colour, not a record-dot replacement.')
    a('time_config',circle(6.5,6.5,5,G,'none')+path('M6.5 3 V6.5 H10',F,1.3)+circle(12,12,3,'none',Y,1.5)+path('M12 8 V10 M12 14 V16 M8 12 H10 M14 12 H16',Y),'Clock and gold settings wheel','time')
    a('key_mode',path('M2 2 V14 M14 2 V14 M3 7 H13 M5 4 3 7 5 10 M11 4 13 7 11 10',G)+rect(7,4,2,6,C,'none'),'Key navigation between frame bars','time')
    a('freeze',rect(3.5,7.5,9,7,'none',G)+path('M5 7.5 V4 C5 0 11 0 11 4 V7.5',G,1.3),'Locked object symbol','poly','text-only','Display rollout and quad menu',note='Keep Freeze Selection text. Max quad commands do not get added leading icons.')
    a('unfreeze',rect(3.5,7.5,9,7,'none',G)+path('M6 7 V4 C6 0 12 0 12 4',G,1.3),'Unlocked object symbol','poly','text-only','Display rollout and quad menu')
    # Pending branches use these Blender tool identifiers literally.
    add('ops.transform.translate',ART['move'],'Four-way Move tool cross','features','toolbar','icon-only','snaps and poly_constraints WorkSpaceTool.bl_icon',note='Exact pending branch name. Blender WorkSpaceTool requires a .dat tool icon or an equivalent custom tool draw route in phase 2.')
    add('ops.transform.rotate',ART['rotate'],'Circular Rotate tool arrow','features','toolbar','icon-only','max_rotate.WorkSpaceTool.bl_icon',note='Exact pending branch name. SVG/PNG previews alone do not replace a WorkSpaceTool .dat icon.')
    add('ops.transform.resize',ART['scale'],'Expanding Scale tool square','features','toolbar','icon-only','snaps WorkSpaceTool.bl_icon',note='Exact pending branch name. Tool-icon integration remains phase 2.')
    add('rotate_gizmo',ellipse(8,8,6.5,3,'none',R)+ellipse(8,8,3,6.5,'none',GREEN)+circle(8,8,5,'none',B),'Three coloured axis rings','features','toolbar','icon-only','Rotate gizmo tool variant',note='Only axis hints use RGB. Main toolbar rotate stays grey.')
    for n,b,i in [('none',path('M3 3 13 13 M3 13 13 3',D),'Unconstrained transform'),('edge',mesh()+path('M2.5 5.5 8.5 8.5',C,2),'Movement constrained to highlighted mesh edge'),('face',mesh()+poly('2.5,5.5 8.5,8.5 8.5,14.5 2.5,11.5',C),'Movement constrained to a polygon plane'),('normal',plane()+path('M8 8 V1',C,1.5)+poly('5,4 8,1 11,4',C),'Arrow along polygon normal')]:
        add('constraint_'+n,b,i,'features','poly','text-only','Edit Geometry > Constraints radio '+n.capitalize(),note='poly_constraints mode '+n.upper()+'. Max uses text radio choices, so retain None/Edge/Face/Normal labels.')
    sym=poly('2,4 6,6 6,13 2,11',G)+poly('10,6 14,4 14,11 10,13',C)+path('M8 1 V15',G,1,stroke_dasharray='2 1')
    add('symmetry',sym,'Mirrored halves separated by a centre plane','features','symmetry','icon plus text','Modifier stack Symmetry row',note='Keep Symmetry text in stack. No stock standalone Symmetry toolbar icon is established by this reference.')
    add('symmetry_align',path('M2 5 C2 0 8 1 8 4 M14 11 C14 16 8 15 8 12',G,1.8)+poly('5,3 9,3 8,7',G)+poly('11,13 7,13 8,9',G),'Opposed circular arrows for Align to Face','features','symmetry','icon-only','Symmetry Align to Face',note='Reference symmetry-04.png is an icon button.')

def main():
    toolbar()
    command_panel()
    create_objects()
    material()
    poly_tools()
    caddies()
    navigation_and_features()
    OUT.mkdir(parents=True, exist_ok=True)
    for row in CAT:
        n = row['name']
        desc = escape(row['idea'])
        svg = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<!-- Original NotuoDesk drawing. SPDX-License-Identifier: GPL-3.0-or-later -->\n'
               '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 16 16">\n'
               f'<title>{escape(n)}</title>\n<desc>{desc}</desc>\n'
               '<g stroke-linecap="square" stroke-linejoin="miter">\n'+ART[n]+'\n</g>\n</svg>\n')
        (OUT / (n+'.svg')).write_text(svg, encoding='utf-8')
    refs = {k:dict(url=BASE+book+'/files/GUID-'+guid+'.htm', evidence=image)
            for k,(book,guid,image) in REFS.items()}
    (OUT / 'catalog.json').write_text(json.dumps(dict(version=1,phase='integrated',
                references=refs,icons=CAT),indent=2)+'\n',encoding='utf-8')
    missing=BASELINE_NAMES-set(ART)
    assert not missing, 'Missing existing assets: '+str(sorted(missing))
    print(f'ARTWORK {len(ART)} original SVGs, all {len(BASELINE_NAMES)} original names covered')
    print('SVGs and placement catalog written. Run build_icons.py to render runtime PNGs.')

if __name__ == '__main__':
    main()
