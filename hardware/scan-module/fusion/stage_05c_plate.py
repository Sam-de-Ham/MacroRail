"""Stage 05c: centring plate (printed bottom-down): disc, rim V-groove for the screw tips and
plunger (also stops the plate lifting), three domed bumps (kinematic seat) and three magnet
pockets, patterned around the yaw axis."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('rimV', '2', 'rim V-groove depth (90 deg, 4 mm wide at the rim)'),
    ('seat_r', '8', 'radius of the kinematic bumps and magnets'),
    ('bump_D', '4', 'kinematic bump diameter'),
    ('bump_H', '1.95', 'kinematic bump height'),
    ('bump_R', '1.9', 'kinematic bump dome radius'),
    ('magPocketD', 'mag_D + 0.2', 'magnet pocket diameter'),
    ('magPocketT', 'mag_T + 0.1', 'magnet pocket depth'),
]


def pattern3(features, name):
    oc = coll(features)
    ci = F.circularPatternFeatures.createInput(oc, root.zConstructionAxis)
    ci.quantity = VI.createByReal(3)
    ci.totalAngle = VI.createByString('360 deg')
    f = F.circularPatternFeatures.add(ci)
    f.name = name
    return f


def run(_):
    for n, e, c in PARAMS:
        param(n, e, c)
    s = sk('z', '-(d_plateBot)', 'PL Ring Floor Top', 'PT 01 Plate')
    s.circle('0', '0', 'plate_D')
    pt = name_new(ext(s, NEW, 'PT Plate', 'plate_T', POS), 'Centring Plate')
    s = Sk(root.xZConstructionPlane, 'PT 02 Rim Groove', ('x', 'z'))
    s.poly([('plate_D / 2 + 0.5', '-(z_cx + rimV + 0.5)'), ('plate_D / 2 - rimV', '-(z_cx)'), ('plate_D / 2 + 0.5', '-(z_cx - rimV - 0.5)')])
    revolve(s, root.zConstructionAxis, CUT, 'PT Rim Groove', bodies=[pt])
    s = sk('z', '-(d_plateTop)', 'PL Plate Top', 'PT 03 Bump')
    s.circle('0', 'seat_r', 'bump_D')
    fb = ext(s, JOIN, 'PT Bump', 'bump_H', POS, bodies=[pt])
    top = None
    for e in pt.edges:
        g = e.geometry
        if isinstance(g, adsk.core.Circle3D) and abs(g.radius * 10 - ev('bump_D') * 5) < 1e-3:
            if top is None or g.center.z > top[0]:
                top = (g.center.z, e)
    ff = fillet(coll([top[1]]), 'bump_R', 'PT Bump Dome')
    s = sk('z', '-(d_plateTop)', 'PL Plate Top', 'PT 04 Magnet Pocket')
    s.circle('seat_r * cos(30 deg)', 'seat_r * sin(30 deg)', 'magPocketD')
    fm = ext(s, CUT, 'PT Magnet Pocket', 'magPocketT', NEG, bodies=[pt])
    pattern3([fb, ff, fm], 'PT Seat Pattern')
    print(report())
