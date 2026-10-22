"""Stage 09: test pieces = parametric slices of the real printed bodies (they follow every later
change), laid out beside the module. Inserted before the pose moves. The small parts (yaw head,
specimen holder, axle, spacer, endstop bracket, washers, gauge) are printed whole as their own
tests; these slices cover the big parts' risky interfaces:
  TP Bearing Seat  - 608 press fit and lip in the +Y upright
  TP Motor Seat    - tilt motor boss recess, shaft hole, ear bolt holes (-Y upright)
  TP Base Holes    - carriage hole pattern and screw-head pockets (lay it on the real carriage)
  TP Tilt Hubs     - double-D bore on the motor shaft; axle socket, bolt hole and nut pocket
  TP Cradle Floor  - yaw motor seat, KY-024 seat, hall sensor pocket and lead slot"""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('tp_dy', '250', 'test pieces laid out at Y = -tp_dy'),
    ('tp_baseT', '2.5', 'base hole test piece: bottom slice (holds the hole pattern and screw-head pockets)'),
]


def slice_of(src, name, axis, plane_expr, plname, rect, depth):
    cp = copy_body(body(src), name)
    s = sk(axis, plane_expr, plname, 'TP Sk %s' % name)
    s.rect(*rect)
    ext(s, INT, 'TP %s Slice' % name, depth, POS, bodies=[cp])
    return cp


def run(_):
    for n, e, c in PARAMS:
        param(n, e, c)
    tl = des.timeline
    pos = None
    for i in range(tl.count):
        if tl.item(i).name == 'POSE Yaw':
            pos = i
    if pos is not None:
        tl.markerPosition = pos
    made = []
    made.append(slice_of('Fork', 'TP Bearing Seat', 'y', 'up_in - 1', 'PL TP Bearing',
                         ('-(brg_boss / 2 + 1)', 'brg_boss / 2 + 1', '-(brg_boss / 2 + 1)', 'brg_boss / 2 + 1'),
                         'brg_lip + brg_W + 2'))
    made.append(slice_of('Fork', 'TP Motor Seat', 'y', '-(up_in + upM_T + 1)', 'PL TP Motor',
                         ('-(byj_tabS / 2 + 5)', 'byj_tabS / 2 + 5', '-(byj_off + 8)', 'byj_off + 8'),
                         'upM_T + 2'))
    made.append(slice_of('Fork', 'TP Base Holes', 'z', '-(axis_H + 1)', 'PL TP Base',
                         ('-(base_LX / 2 + 1)', 'base_LX / 2 + 1', '-(carr_headY1 + 6)', 'carr_headY1 + 6'),
                         'tp_baseT + 1'))
    hubs = slice_of('Cradle', 'TP Tilt Hubs', 'z', '-(hubBoss_D / 2 + 2)', 'PL TP Hubs',
                    ('-(hubBoss_D / 2 + 2)', 'hubBoss_D / 2 + 2', '-(arm_in + arm_T + 1)', 'arm_in + arm_T + 1'),
                    'hubBoss_D + 4')
    made.append(hubs)
    made.append(slice_of('Cradle', 'TP Cradle Floor', 'z', '-(d_floorBot + 1)', 'PL TP Floor',
                         ('-(floor_back + 1)', 'floor_front + 1', '-(arm_in - 0.5)', 'arm_in - 0.5'),
                         'floor_T + 2'))
    # the hub slice is two lumps -> two bodies ('TP Tilt Hubs' and 'TP Tilt Hubs (1)')
    made = [b for b in made if b.name != 'TP Tilt Hubs']
    for b in root.bRepBodies:
        if b.name.startswith('TP Tilt Hubs'):
            b.name = 'TP Axle Socket' if b.boundingBox.maxPoint.y > 0 else 'TP Tilt D-Bore'
            made.append(b)
    move_xyz(made, '0 mm', '-(tp_dy)', '0 mm', 'TP Lay Out')
    tl.moveToEnd()
    test = des.appearances.itemByName('MR Test Piece')
    if not test:
        lib = app.materialLibraries.itemByName('Fusion Appearance Library')
        src = None
        for i in range(lib.appearances.count):
            a = lib.appearances.item(i)
            if 'plastic' in a.name.lower() and 'yellow' in a.name.lower():
                src = a
                break
        test = des.appearances.addByCopy(src, 'MR Test Piece') if src else None
    for b in made:
        if test:
            b.appearance = test
        b.opacity = 1.0
    des.selectionSets.add(made, '5 Test Pieces')
    print([b.name for b in made])
    print(report())
