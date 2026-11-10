"""Original caddy pictograms with the field compositions in Max 2026 Help.

Drawn on the family's 16-unit grid. Reference images inform the visual idea.
This module never reads reference pixels or paths. GPL-3.0-or-later.
"""


def caddy_icons(add, path, poly, rect, circle):
    edge, light, mid, dark = '#303b40', '#d2d8db', '#9ba8ae', '#64757e'
    blue, cyan = '#428fcb', '#64c6d3'

    def line(d, color=edge, width=1):
        return path(d, color, width)

    def face(points, shade=mid):
        return poly(points, shade, edge)

    def emit(op, key, body, idea, ref=None, mode='icon-only'):
        ref = ref or {'msmooth':'smooth'}.get(op,op)
        add('caddy_'+op+'_'+key,body,idea,'caddies',ref,mode,
            op.title()+' caddy, '+key.replace('_',' '),
            note='Original shaded pictogram. Operation and field have their own key. Max reference is visual study only.')

    def grid():
        return rect(2,2,12,12,light,edge) + line('M8 2 V14 M2 8 H14', dark)

    def mode(value):
        if value == 'polygon':
            return ''.join(rect(x,y,4.5,4.5,mid,edge) for x in (2,9) for y in (2,9))
        if value == 'local':
            return (rect(2,10,12,4,mid,edge) +
                    poly('6,10 6,6 4,6 8,2 12,6 10,6 10,10',cyan,edge))
        return (line('M5 2 H2 V14 H5 M11 2 H14 V14 H11',cyan,2) +
                ''.join(rect(x,y,3,4,mid,edge,.7) for x in (5,9) for y in (3,9)))

    def height():
        return (rect(2,2,5,12,mid,edge) + rect(2.5,2.5,1,11,light,'none') +
                poly('10,2 14,2 14,4 13,4 13,12 14,12 14,14 10,14 10,12 11,12 11,4 10,4',cyan,edge,.7))

    def bias():
        return (face('6,2 10,2 10,8 14,13 14,14 2,14 2,13 6,8',cyan) +
                poly('7,3 8,3 8,9 4,13 3,13 7,8',light) +
                poly('9,3 10,8 13,13 10,12 8,8',dark))

    def pointer():
        return poly('8,6 8,14 10,12 12,15 14,14 12,11 15,11',light,edge,.7)

    def patch_pointer():
        return (rect(1.5,2,12,6.5,mid,edge) +
                rect(2.5,3,7,4.5,cyan,'none') + pointer())

    def stack(flat=False, pinch=False, slide=False):
        if flat:
            return rect(5,1.5,6,13,cyan,edge) + line('M6 6 H10 M6 10 H10',edge)
        body = (face('3,4 6,1.5 12,1.5 10,4',light) +
                face('3,4 10,4 10,14 3,14',mid) +
                face('10,4 12,1.5 12,11.5 10,14',dark))
        ys = (7,10) if not slide else (10.5,12)
        body += ''.join(line(f'M3 {y} H10 L12 {y-2.5}',blue) for y in ys)
        if pinch or slide:
            body = '<g transform="translate(-1 0)">'+body+'</g>'
            body += line('M14 3 V8 M12.5 6 H15.5',blue)
            if pinch:
                body += line('M14 10 V15 M12.5 12 H15.5',blue)
        return body

    def sphere():
        return (circle(8,8,6.5,mid,edge) +
                path('M2 9 Q8 12 14 9 Q13 15 8 14.5 Q3 15 2 9 Z',blue,.7,cyan) +
                line('M2 6 Q8 3 14 6 M1.5 9 H14.5',edge,.8) +
                line('M8 1.5 C3 4 3 10 8 11 M8 1.5 C13 4 13 10 8 11',dark,.8) +
                line('M8 1.5 V11',light,.8))

    def badge(number):
        digit = 'M11 10.5 12 10 V14 M11 14 H13' if number == 1 else 'M10.5 11 V10 H13 V12 L10.5 14 H13'
        return rect(9,9,6.5,6.5,blue,light,.5) + line(digit,'#f1f5f6',.9)

    for op in ('extrude','bevel'):
        key = 'bevel_type' if op == 'bevel' else 'extrusion_type'
        emit(op,key,mode('group'),'Bracketed connected polygon grid for Group')
        for value in ('group','local','polygon'):
            emit(op,key+'_'+value,mode(value),
                 {'group':'Bracketed polygon grid','local':'Up arrow above a flat base',
                  'polygon':'Four separate square polygons'}[value])
        emit(op,'height',height(),'Vertical rectangle beside an I-shaped height bar')
        emit(op,'local_bias',bias(),'Upright stem with a flared foot')
    emit('extrude','base_width',rect(2,3,12,7,mid,edge)+line('M2 6 H14',light)+
         line('M2 12 V15 M2 13.5 H14 M14 12 V15',blue),
         'Horizontal rectangle above a width bar')
    emit('bevel','amount',rect(2,2,12,12,cyan,edge)+rect(5,5,6,6,mid,edge),
         'Square outline band surrounding a smaller square')

    emit('chamfer','amount',patch_pointer(),'Short selected rectangle with a pointer below its right half')
    emit('chamfer','segments',stack(True),'Upright narrow strip divided into three stacked segments')
    emit('chamfer','tension',
         rect(2,2,3,12,mid,edge)+rect(2,2,12,3,mid,edge)+
         face('3,3 8,5 5,9',cyan)+line('M3 3 6 6',dark)+
         poly('10,9 15,9 15,11 13.5,11 13.5,15 11.5,15 11.5,11 10,11',cyan,edge,.7),
         'Right-angle corner with a selected triangular corner and a tension bar')
    emit('chamfer','open',
         ''.join(rect(x,y,3,3,cyan if (x,y)==(6.5,6.5) else mid,edge,.6)
                 for x in (2,6.5,11) for y in (2,6.5,11)),
         'Nine small square openings in a flat polygon grid')
    miter = (face('3,3 8,2 13,3 13,13 8,10 3,13',cyan)+
             line('M8 2 V10 M3 7 8 5 13 7',edge))
    emit('chamfer','chamfer_miter',miter,'Folded quad corner for the 2026 mitering flyout')
    corner = (rect(2,2,3,12,mid,edge)+rect(2,2,12,3,mid,edge)+
              face('3,3 8,5 5,9',cyan)+line('M3 3 6 6',dark)+
              poly('10,9 15,9 15,11 13.5,11 13.5,15 11.5,15 11.5,11 10,11',cyan,edge,.7))
    for key in ('chamfer_depth','end_bias','radial_bias'):
        emit('chamfer',key,corner,'Corner profile used for '+key.replace('_',' '))
    emit('chamfer','invert_open',grid()+rect(4,4,8,8,mid,edge),
         'Inset gridded square for Invert Open')
    cylinder = (path('M2 5 V12 C2 16 14 16 14 12 V5',edge,1,cyan)+
                path('M2 5 C2 1 14 1 14 5 C14 9 2 9 2 5 Z',edge,1,mid))
    emit('chamfer','chamfer_smooth',cylinder,'Cylinder with a cyan smooth wall')
    smooth_cube = (face('2,5 8,2 14,5 8,8',light)+face('2,5 8,8 8,14 2,11',cyan)+
                   face('8,8 14,5 14,11 8,14',mid))
    emit('chamfer','smooth_type',smooth_cube,'Shaded cube for the smoothing scope flyout')
    emit('chamfer','smooth_threshold',smooth_cube+pointer(),'Shaded cube with a threshold pointer')

    emit('connect','segments',stack(),'Upright block divided by horizontal segment lines')
    emit('connect','pinch',stack(pinch=True),'Stacked block with two plus marks along its right edge')
    emit('connect','slide',stack(slide=True),'Block with low segment lines and an upper right plus mark')

    emit('inset','amount',rect(2,2,12,12,light,edge)+rect(4.5,4.5,7,7,cyan,blue),
         'Small cyan square inside a larger square outline')
    for key,value in (('individual','group'),('individual_group','group'),('individual_polygon','polygon')):
        emit('inset',key,mode(value),'Bracketed grid for Group' if value=='group' else 'Four separate polygon squares')
    emit('outline','amount',rect(4,4,8,8,light,edge)+line('M1 1 H15 V15 H1 Z',blue),
         'Outer polygon boundary around the original face, caddy appearance unverified')

    emit('bridge','segments',stack(),'Upright block divided by horizontal segment lines')
    emit('bridge','taper',face('6,2 10,2 12,14 2,14',light)+
         face('10,2 14,10 12,14',dark)+line('M6 3 3.5 13',mid),
         'Upright tapered prism with a narrow top and broad base')
    emit('bridge','bias',path('M6 2 H9 Q9 9 14 13 L12 14 H2 Q6 9 6 2 Z',edge,1,light)+
         path('M9 2 Q10 9 14 13 L12 14 Q9 10 8 3 Z',dark,.7,mid),
         'Flared bell shape with a narrow neck and curved sides')
    emit('bridge','smooth',sphere(),'Gridded sphere with a cyan lower hemisphere')
    emit('bridge','bridge_adjacent',face('2,4 8,2 8,13 2,15',mid)+
         face('8,2 14,4 14,15 8,13',cyan),'Two adjacent border faces')
    emit('bridge','reverse_triangulation',grid()+line('M2 14 14 2',blue),
         'Reversed diagonal in a polygon grid')
    hourglass = (face('2,1.5 12,1.5 9,8 12,14 2,14 6,8',light) +
                 face('12,1.5 14,1.5 11,8 13,14 12,14 9,8',dark) +
                 face('2,1.5 9,8 6,8',mid) + face('6,8 12,14 2,14',mid))
    for number in (1,2):
        emit('bridge','twist'+str(number),hourglass+badge(number),
             'Upright hourglass with a blue '+str(number)+' badge at lower right')
        body = grid()
        if number == 1:
            body += rect(2.5,2.5,5,5,cyan,'none')
        else:
            body += line('M2 8 H14',blue)
            body += ''.join(rect(x,y,2.5,2.5,light,edge,.6) for x in (1,12) for y in (1,12))
        emit('bridge','pick'+str(number),body+badge(number),
             'Flat polygon grid with a numbered lower right badge and '+('selected face' if number==1 else 'corner points'))
    emit('bridge','bridge_selection',grid()+line('M8 2 V14',blue)+pointer(),
         'Flat polygon grid with a pointer over its right side')
    emit('bridge','pick_cursor',circle(6,6,4.5,light,edge,.8)+pointer(),
         'Circular pick cursor with an arrow at its lower right')

    emit('weld','threshold',patch_pointer(),'Selected rectangular patch and a pointer')
    emit('weld','weld_counts',line('M1 4 H6 M1 8 H6 M10 4 H15 M10 8 H15',mid)+
         line('M7 6 H10',blue),'Before and after counts remain text in the caddy',mode='text-only')

    for value in ('edge','face'):
        divisions = line('M2 2 14 14 M14 2 2 14',blue,.9)
        if value == 'edge':
            # Square stroke caps close a one-unit dash gap. Separate tiles
            # keep Max's dotted cross visibly dotted at native caddy size.
            divisions = ''.join(rect(x,y,1,1,blue,'none')
                                for x,y in ([(7.5,p) for p in (2.5,5,7.5,10,12.5)]+
                                            [(p,7.5) for p in (2.5,5,10,12.5)]))
        body = rect(2,2,12,12,light,edge)+divisions
        emit('tessellate','tessellate_type_'+value,body,
             'Dotted cross in a square' if value=='edge' else 'Diagonal cross in a square')
        if value == 'edge':
            emit('tessellate','tessellate_type',body,'Dotted cross in a square')
    emit('tessellate','tess_tension',patch_pointer(),'Selected rectangular patch and a pointer')

    emit('msmooth','smoothness',sphere(),'Gridded sphere with a cyan lower hemisphere')
    # Reserved only. Max leaves both separation pills blank before the check.
    emit('msmooth','separate_smoothing',rect(2,2,5,12,light,edge)+rect(9,2,5,12,mid,edge),
         'Reserved separation artwork, Max pill has no field pictogram',mode='text-only')
    emit('msmooth','separate_materials',grid()+rect(2,2,6,6,cyan,edge),
         'Reserved material artwork, Max pill has no field pictogram',mode='text-only')

    emit('relax','relax',patch_pointer(),'Selected rectangular patch and a pointer')
    emit('relax','iterations',rect(2,2,11,12,light,dark)+
         path('M2 9 Q7 0 13 9 V14 H2 Z',blue,.8,cyan)+
         poly('11,9 14,9 14,11 15.5,11 15.5,14 14,14 14,15.5 11,15.5 11,14 9,14 9,11 11,11','#56bb55',light,.6),
         'Square curved patch with a green repeat plus at lower right')
    emit('relax','hold_boundary',rect(2,2,12,12,light,dark)+
         path('M2 9 Q8 -1 14 9 V14 H2 Z',blue,.8,cyan)+
         line('M5 7 11 7 11 12 5 12 Z',dark)+
         ''.join(rect(x,y,2.5,2.5,light,edge,.7) for x in (4,9.5) for y in (6,11)),
         'Curved patch in a square with four interior boundary pins')
    emit('relax','hold_outer',rect(2,2,12,12,light,dark)+
         path('M2 6 Q8 15 14 6 V14 H2 Z',blue,.8,cyan)+
         rect(1,5,3,3,light,edge,.7)+rect(12,5,3,3,light,edge,.7),
         'Sagging patch in a square pinned at its two outer sides')
