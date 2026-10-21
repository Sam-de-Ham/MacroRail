"""Stage 05a: the yaw head (one printed body, printed hub-down, no supports): a bell-shaped hub
(flat bottom, 45-deg cone up to the ring floor) on the yaw motor's double-D shaft with an M3 set
screw (-X), the centring ring (floor + wall), two radial M3 screws (+X, +Y in head frame) with
nut slots, and the hall magnet in the bell's flat underside (+X), over the sensor."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('yawBoreDepth', 'd_hubBot - (d_floorBot - byj_bossH - byj_shaftL) + 0.3', 'D-bore depth for the yaw motor shaft'),
    ('bell_r0', 'ring_OD / 2 - hub_H', 'bell hub flat-bottom radius (45 deg cone up to the ring rim)'),
    ('z_hubMid', 'd_hubBot - hub_H / 2', 'depth of the hub set screw axis'),
    ('setHeadR', 'byj_flat / 2 + bolt_S', 'set screw under-head radius (tip on the shaft flat)'),
    ('hubNut_x', '4.5', 'hub set screw nut slot inner |X|'),
    ('z_cx', 'd_plateTop + plate_T / 2', 'depth of the centring screw axis'),
    ('nut_r', 'ring_ID / 2 + 1.2', 'centring nut slot inner radius'),
]


def run(_):
    for n, e, c in PARAMS:
        param(n, e, c)
    s = Sk(root.xZConstructionPlane, 'HD 01 Bell Hub', ('x', 'z'))
    s.poly([('0', '-(d_hubBot)'), ('bell_r0', '-(d_hubBot)'), ('ring_OD / 2', '-(d_hubTop)'), ('0', '-(d_hubTop)')])
    hd = name_new(revolve(s, root.zConstructionAxis, NEW, 'HD Bell Hub'), 'Yaw Head')
    s = sk('z', '-(d_hubTop)', 'PL Hub Top', 'HD 02 Ring Floor')
    s.circle('0', '0', 'ring_OD')
    ext(s, JOIN, 'HD Ring Floor', 'ring_floorT', POS, bodies=[hd])
    s = sk('z', '-(d_plateBot)', 'PL Ring Floor Top', 'HD 03 Ring Wall')
    s.circle('0', '0', 'ring_OD')
    s.circle('0', '0', 'ring_ID')
    repair(s)
    ann = 3.14159 * ((ev('ring_OD') * 5) ** 2 - (ev('ring_ID') * 5) ** 2)
    ext(s, JOIN, 'HD Ring Wall', 'ring_wallH', POS, bodies=[hd], profiles=profiles_by_area(s, lambda a: abs(a - ann) < 2))
    s = sk('z', '-(d_hubBot)', 'PL Hub Bottom', 'HD 04 Yaw D-Bore')
    pr = dd_bore(s, '0', '0', 'byj_shaftD + fit_D', 'byj_flat + fit_D', 'y')
    ext(s, CUT, 'HD Yaw D-Bore', 'yawBoreDepth', POS, bodies=[hd], profiles=pr)
    # set screw along -X onto a flat: hole, head counterbore, nut slot open to the bell bottom
    s = Sk(root.yZConstructionPlane, 'HD 05 Hub Set Screw', ('y', 'z'))
    s.circle('0', '-(z_hubMid)', 'm3_clr')
    ext(s, CUT, 'HD Hub Set Screw', 'ring_OD / 2', NEG, bodies=[hd])
    s = sk('x', '-(setHeadR)', 'PL Set Screw Head', 'HD 06 Set Screw Counterbore')
    s.circle('0', '-(z_hubMid)', 'cb_D')
    ext(s, CUT, 'HD Set Screw Counterbore', 'ring_OD / 2', NEG, bodies=[hd])
    s = sk('z', '-(d_hubBot)', 'PL Hub Bottom', 'HD 07 Hub Nut Slot')
    s.rect('-(hubNut_x + m3_pocketT)', '-(hubNut_x)', '-(m3_pocketAF / 2)', 'm3_pocketAF / 2')
    ext(s, CUT, 'HD Hub Nut Slot', 'hub_H / 2 + 3.1', POS, bodies=[hd])
    # hall magnet, axial, in the flat underside right over the sensor
    s = sk('z', '-(d_hubBot)', 'PL Hub Bottom', 'HD 08 Hub Magnet Pocket')
    s.circle('ky_sensR', '0', 'magPocketD')
    ext(s, CUT, 'HD Hub Magnet Pocket', 'magPocketT', POS, bodies=[hd])
    # centring screws +X and +Y, nuts in slots open to the wall top
    s = Sk(root.yZConstructionPlane, 'HD 09 Screw Hole X', ('y', 'z'))
    s.circle('0', '-(z_cx)', 'm3_clr')
    ext(s, CUT, 'HD Screw Hole X', 'ring_OD / 2 + 1', POS, bodies=[hd])
    s = Sk(root.xZConstructionPlane, 'HD 10 Screw Hole Y', ('x', 'z'))
    s.circle('0', '-(z_cx)', 'm3_clr')
    ext(s, CUT, 'HD Screw Hole Y', 'ring_OD / 2 + 1', POS, bodies=[hd])
    s = sk('z', '-(z_cx + 3.1)', 'PL Ring Nut Slot Bottom', 'HD 11 Ring Nut Slots')
    s.rect('nut_r', 'nut_r + m3_pocketT', '-(m3_pocketAF / 2)', 'm3_pocketAF / 2')
    s.rect('-(m3_pocketAF / 2)', 'm3_pocketAF / 2', 'nut_r', 'nut_r + m3_pocketT')
    ext(s, CUT, 'HD Ring Nut Slots', 'ring_wallH + 3', POS, bodies=[hd])
    print(report())
