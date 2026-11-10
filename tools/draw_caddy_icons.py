"""Original shaded caddy pictograms on the family's 16-unit grid.

Autodesk 2026 Help informs the modeling idea only. No image pixels or paths
are read by this authoring module. SPDX-License-Identifier: GPL-3.0-or-later
"""


def caddy_icons(add, path, poly, rect, circle):
    edge, light, mid, dark = '#303b40', '#d2d8db', '#9ba8ae', '#64757e'
    blue, cyan = '#428fcb', '#64c6d3'

    def line(d, color=edge, width=1):
        return path(d, color, width)

    def face(points, shade=mid):
        return poly(points, shade, edge)

    def box():
        return (face('2,5 7,2 14,5 9,8', light) +
                face('2,5 9,8 9,14 2,11', mid) +
                face('9,8 14,5 14,11 9,14', dark))

    def slab():
        return (face('2,5 11,3 14,7 5,10', light) +
                face('5,10 14,7 14,10 5,13', dark) +
                face('2,5 5,10 5,13 2,8', mid))

    def raised(bevel=False):
        return (slab() + face('5,5 8,3 11,5 8,7', cyan) +
                face('5,5 8,7 8,11 4,9' if bevel else '5,5 8,7 8,11 5,9', mid) +
                face('8,7 11,5 12,9 8,11' if bevel else '8,7 11,5 11,9 8,11', dark) +
                line('M13 2 V7', blue) + poly('11,3 13,0 15,3', blue))

    def bias():
        return (face('2,13 6,9 7,2 9,2 10,9 14,13', mid) +
                face('7,2 9,2 10,9 14,13 8,11', cyan))

    def chamfer():
        return (face('2,7 7,2 14,5 9,10', light) +
                face('2,7 9,10 9,14 2,11', mid) +
                face('9,10 14,5 14,11 9,14', dark) +
                face('2,7 4,5 11,8 9,10', cyan))

    def bridge(shape='straight'):
        if shape == 'taper':
            return face('2,2 6,6 6,10 2,14 8,14 10,10 10,6 8,2', mid) + face('8,2 14,4 11,7 11,9 14,12 8,14 10,10 10,6', light) + line('M6 6 10 6 M6 10 10 10', blue)
        if shape == 'bias':
            return face('2,2 7,2 9,8 7,14 2,14 5,8', mid) + face('7,2 12,4 14,8 12,12 7,14 9,8', light) + line('M5 8 9 8 14 8', blue)
        if shape == 'twist':
            return face('2,2 8,2 5,8 11,14 5,14 2,8', mid) + face('8,2 13,4 10,8 14,12 11,14 5,8', light) + line('M2 2 8 2 M5 14 11 14', blue)
        return face('2,2 8,2 8,14 2,14', mid) + face('8,2 13,5 13,11 8,14', light) + line('M2 6 H8 L13 7 M2 10 H8 L13 9', blue)

    def sphere():
        return (circle(8,8,6, mid, edge) +
                path('M3 5 Q8 2 13 5 L14 8 Q8 11 2 8 Z', edge, 1, light) +
                line('M8 2 C4 5 4 11 8 14 M8 2 C12 5 12 11 8 14', dark) +
                line('M2 9 Q8 13 14 9', blue))

    def badge(number):
        # A seven-unit badge stays legible at 16px, unlike a one-pixel tick.
        digit = 'M11 11 12 10 V14 M11 14 H13' if number == 1 else 'M10 11 V10 H13 V12 L10 14 H13'
        return rect(8.5,8.5,7,7,blue,edge) + line(digit,'#f1f5f6')

    def pointer():
        return poly('9,6 9,14 11,12 13,15 15,14 13,11 15,10',light,edge)

    def patch():
        return face('2,3 12,3 12,11 2,11', light) + rect(4,5,6,4,cyan,blue)

    def inset(individual=False):
        art = face('2,2 14,2 14,14 2,14', mid)
        if individual:
            return art + rect(4,4,3,3,cyan,blue) + rect(9,4,3,3,cyan,blue) + rect(4,9,3,3,cyan,blue) + rect(9,9,3,3,cyan,blue)
        return art + rect(5,5,6,6,cyan,blue) + line('M2 2 5 5 M14 2 11 5 M2 14 5 11 M14 14 11 11',dark)

    def mode(value, bevel=False):
        if value == 'polygon':
            return (face('1,5 5,3 8,5 4,7',cyan) + face('8,10 12,8 15,10 11,12',light) +
                    line('M4 7 V11 M11 12 V15',blue))
        if value == 'local':
            return box() + line('M4 8 1 6 M11 7 15 4',blue,2)
        return box() + line('M5 6.5 V12.5 M2 8 9 11',blue)

    def emit(op, key, body, idea, ref=None, mode='icon-only'):
        ref = ref or {'msmooth':'smooth','weld':'weld','bevel':'bevel','outline':'outline'}.get(op,op)
        add('caddy_'+op+'_'+key,body,idea,'caddies',ref,mode,
            op.title()+' caddy, '+key.replace('_',' '),
            note='Original shaded pictogram. Operation and field have their own key. Max reference is visual study only.')

    for op, bevel in (('extrude',False),('bevel',True)):
        type_key = 'bevel_type' if bevel else 'extrusion_type'
        emit(op,type_key,mode('group',bevel),'Connected raised polygons for group mode')
        for value in ('group','local','polygon'):
            emit(op,type_key+'_'+value,mode(value,bevel),'Raised polygon '+value+' mode')
        emit(op,'height',raised(bevel),'A face raised above the surrounding mesh with a height indicator')
        emit(op,'local_bias',bias(),'A flared local-normal base')
    emit('extrude','base_width',slab()+line('M3 14 H13',blue)+line('M3 12 V15 M13 12 V15',blue),'Extrusion footprint with a horizontal width indicator')
    emit('bevel','amount',inset()+line('M3 3 5 5 M11 11 14 14',blue,2),'Outline of the beveled top face')

    emit('chamfer','amount',chamfer(),'A cyan chamfer strip replaces a sharp mesh edge')
    emit('chamfer','segments',chamfer()+line('M3 6 10 9 M4 5 11 8',blue),'Parallel divisions across a chamfer strip')
    emit('chamfer','tension',face('2,14 2,3 14,3',mid)+path('M2 3 Q4 12 14 14 L14 3 Z',edge,1,light)+line('M2 3 Q4 12 14 14',blue,2),'Curved chamfer profile between two faces')
    emit('chamfer','open',face('2,6 6,2 14,5 10,9',light)+face('2,9 10,12 10,15 2,12',mid)+line('M2 7 10 10 14 6',blue),'A visible gap where the chamfer strip is removed')

    emit('connect','segments',box()+line('M2 7 9 10 14 7 M2 10 9 13 14 10',blue),'New parallel edges across a mesh')
    emit('connect','pinch',box()+line('M2 8 9 11 14 8 M2 9 9 12 14 9',blue)+line('M1 4 V7 M1 12 V10',cyan,2),'Two new edges pinched toward the middle')
    emit('connect','slide',box()+line('M2 10 9 13 14 10',blue,2)+line('M1 5 V9 M0 8 1 10 2 8',blue),'A connecting edge slid toward one end of the mesh')

    emit('inset','amount',inset(),'A smaller cyan face inside an unchanged outer polygon')
    inset_group = rect(2,2,12,12,mid,edge)+rect(4,4,8,8,light,blue)+line('M8 4 V12 M4 8 H12',blue)
    emit('inset','individual',inset_group,'Connected polygon grid for group inset mode')
    emit('inset','individual_group',inset_group,'Connected polygon grid for group inset mode')
    emit('inset','individual_polygon',inset(True),'Separate inset borders inside individual polygons')
    emit('outline','amount',face('4,4 12,4 12,12 4,12',light)+line('M1 1 H15 V15 H1 Z',blue)+line('M4 4 1 1 M12 12 15 15',blue),'The outer polygon boundary expanded around the original face')

    emit('bridge','segments',bridge(),'A divided strip joining two borders')
    emit('bridge','taper',bridge('taper'),'Bridge narrowed at its middle')
    emit('bridge','bias',bridge('bias'),'Bridge waist moved toward one end')
    emit('bridge','smooth',sphere(),'A rounded bridge surface with a smooth equator')
    for number in (1,2):
        emit('bridge','twist'+str(number),bridge('twist')+badge(number),'Twisted bridge with visible end '+str(number)+' badge')
        emit('bridge','pick'+str(number),box()+pointer()+badge(number),'Pick bridge end '+str(number)+' with a numbered mesh badge')
    emit('bridge','bridge_selection',box()+line('M2 5 9 8 14 5',blue,2)+pointer(),'Pick the bridge border or polygon selection')

    emit('weld','threshold',patch()+pointer(),'Weld threshold acts on selected mesh points')
    emit('weld','weld_counts',line('M1 4 H6 M1 8 H6 M10 4 H15 M10 8 H15',mid)+line('M7 6 H10',blue),'Before and after counts remain text in the caddy',mode='text-only')

    tess = face('2,2 14,2 14,14 2,14',light)
    for value in ('edge','face'):
        body = tess + line('M8 2 V14 M2 8 H14' if value == 'edge' else 'M2 2 14 14 M14 2 2 14',blue)
        emit('tessellate','tessellate_type_'+value,body,value.title()+' centre tessellation divisions')
        if value == 'edge':
            emit('tessellate','tessellate_type',body,'Edge centre tessellation divisions')
    emit('tessellate','tess_tension',patch()+line('M2 10 Q7 4 12 10',blue)+pointer(),'Tension changes the newly divided surface profile')

    emit('msmooth','smoothness',sphere(),'Smooth rounded mesh with cyan latitude')
    emit('msmooth','separate_smoothing',face('1,5 6,2 6,13 1,10',light)+face('10,2 15,5 15,10 10,13',mid)+line('M6 3 V12 M10 3 V12',blue),'Two curved mesh groups divided by a visible gap')
    emit('msmooth','separate_materials',face('2,2 14,2 14,14 2,14',mid)+rect(3,3,5,5,cyan,'none')+rect(8,8,5,5,blue,'none'),'Separate alternating material patches')

    emit('relax','relax',patch()+line('M2 10 Q7 14 12 10',blue)+pointer(),'Selected mesh points move toward a relaxed profile')
    emit('relax','iterations',path('M2 12 V7 Q2 2 8 2 Q14 2 14 7 V12 Z',edge,1,light)+line('M2 7 Q8 2 14 7',blue)+line('M12 9 V15 M9 12 H15',cyan,2),'A relaxed curved patch with a repeat plus')
    emit('relax','hold_boundary',box()+line('M2 5 7 2 14 5 14 11 9 14 2 11 Z',blue)+rect(1,4,3,3,light,edge)+rect(12,4,3,3,light,edge)+rect(7,12,3,3,light,edge),'Pinned points around a mesh boundary')
    emit('relax','hold_outer',path('M2 3 V14 H14 V3 Q8 12 2 3 Z',edge,1,light)+line('M2 3 Q8 12 14 3',blue)+rect(1,2,3,3,light,edge)+rect(12,2,3,3,light,edge),'Outer corner pins hold a sagging mesh patch')
