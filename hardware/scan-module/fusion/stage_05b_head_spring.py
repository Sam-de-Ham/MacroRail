"""Stage 05b: spring housing on the yaw head at 225 deg (opposite the two screws), its bore
(open to the inside of the ring) and the reference spring. The pen spring bears straight on
the holder's rim, no plunger (user, after the test print)."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('spr_boreD', 'spr_OD + 0.4', 'spring bore'),
    ('spr_bossD', '8', 'spring housing outer diameter'),
    ('spr_pre', '1.5', 'spring compression left when the holder is pushed fully towards the screws'),
    ('spr_end', 'plate_D / 2 - cx_travel + spr_L - spr_pre', 'spring bore closed end, radius from the yaw axis'),
]


def diag_plane():
    """Plane through the Z axis whose normal points along (-1,-1,0)/sqrt2 or its opposite."""
    p = plane_angle(root.zConstructionAxis, '45 deg', root.yZConstructionPlane, 'PL Spring Axis 225')
    n = p.geometry.normal
    if abs(abs(n.x + n.y) / 2 ** 0.5 - 1) > 1e-3:
        p.deleteMe()
        p = plane_angle(root.zConstructionAxis, '-45 deg', root.yZConstructionPlane, 'PL Spring Axis 225')
        n = p.geometry.normal
    direction = POS if (-n.x - n.y) > 0 else NEG
    return p, direction


def run(_):
    for n, e, c in PARAMS:
        param(n, e, c)
    hd = body('Yaw Head')
    p, dirn = diag_plane()
    s = Sk(p, 'HD 11 Spring Housing', ('x', 'z'))
    s.circle('0', '-(z_cx)', 'spr_bossD')
    ext_from(s, JOIN, 'HD Spring Housing', 'ring_ID / 2', 'spr_end + 1.5 - ring_ID / 2', dirn, bodies=[hd])
    s = Sk(p, 'HD 12 Spring Bore', ('x', 'z'))
    s.circle('0', '-(z_cx)', 'spr_boreD')
    ext_from(s, CUT, 'HD Spring Bore', 'ring_ID / 2 - 0.5', 'spr_end - ring_ID / 2 + 0.5', dirn, bodies=[hd])
    s = Sk(p, 'REF Sk 21 Spring', ('x', 'z'))
    s.circle('0', '-(z_cx)', 'spr_OD')
    s.circle('0', '-(z_cx)', 'spr_OD - 1')
    repair(s)
    name_new(ext_from(s, NEW, 'REF Spring', 'plate_D / 2', 'spr_end - plate_D / 2', dirn, profiles=profiles_by_area(s, lambda a: a < 7)), 'REF Spring')
    # snap-off support fin under the spring housing (the head prints hub-down without supports)
    param('fin_T', '0.8', 'snap-off support fin thickness under the spring housing')
    s = sk('z', '-(d_hubBot)', 'PL Hub Bottom', 'HD 13 Support Fin')
    s.rect('ring_OD / 2 - 1', 'spr_end + 1', '-(fin_T / 2)', 'fin_T / 2')
    fin = name_new(ext(s, NEW, 'HD Support Fin', 'd_hubBot - z_cx - spr_bossD / 2 + 0.5', POS), 'TMP Support Fin')
    move_rot([fin], root.zConstructionAxis, '225 deg', 'HD Support Fin Turn')
    ci = F.combineFeatures.createInput(hd, coll([fin]))
    ci.operation = JOIN
    cf = F.combineFeatures.add(ci)
    cf.name = 'HD Support Fin Join (snap off after printing)'
    print(report())
