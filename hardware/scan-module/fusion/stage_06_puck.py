"""Stage 06: the puck (printed base-down): base disc with three V-grooves and three magnet
pockets underneath (kinematic seat on the plate's domes), clamp column, 45-deg tapered nose,
pin hole on the yaw axis, pad pocket + M3 pad screw from +X with its nut slot (open to +Y).
Plus the printed pad and reference pad screw and nut."""
import sys, importlib, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('col_Y', '14', 'clamp column size across (no overhang under the nose base)'),
    ('pinHoleD', '1', 'pin hole through nose and puck (pins 00-1 = 0.30-0.40)'),
    ('puck_V', 'bump_H - bump_R + bump_R * sqrt(2) - puck_gap + 0.12', 'V-groove depth under the puck (+0.12: the filleted dome seats without overlap)'),
    ('puck_Vlen', '5', 'V-groove length'),
    ('z_pad', 'd_colTop + col_H / 2', 'depth of the pad screw axis'),
    ('pad_wall', '0.3', 'pin rests against the pocket wall this far past the axis'),
    ('pad_L', '4', 'pad length along X'),
    ('pad_W', '3.2', 'pad width (Y)'),
    ('pad_H', '3', 'pad height (Z)'),
    ('padPocket_clr', '0.4', 'pad pocket clearance (each size)'),
    ('padNut_x', 'pin_D - pad_wall + pad_L + 0.4', 'pad nut slot inner X'),
]


def run(_):
    for n, e, c in PARAMS:
        param(n, e, c)
    s = sk('z', '-(d_puckBot)', 'PL Puck Bottom', 'PK 01 Puck Base')
    s.circle('0', '0', 'puck_D')
    pk = name_new(ext(s, NEW, 'PK Base', 'puck_T', POS), 'Puck')
    s = sk('z', '-(d_puckTop)', 'PL Puck Top', 'PK 02 Column')
    s.rect('-(col_X / 2)', 'col_X / 2', '-(col_Y / 2)', 'col_Y / 2')
    ext(s, JOIN, 'PK Column', 'col_H', POS, bodies=[pk])
    s = Sk(root.xZConstructionPlane, 'PK 03 Nose', ('x', 'z'))
    s.poly([('0', '-(d_colTop)'), ('nose_baseD / 2', '-(d_colTop)'), ('nose_tipD / 2', '-(d_noseTip)'), ('0', '-(d_noseTip)')])
    revolve(s, root.zConstructionAxis, JOIN, 'PK Nose', bodies=[pk])
    s = sk('z', '-(d_puckBot)', 'PL Puck Bottom', 'PK 04 Pin Hole')
    s.circle('0', '0', 'pinHoleD')
    ext(s, CUT, 'PK Pin Hole', 'd_puckBot - d_noseTip + 1', POS, bodies=[pk])
    # kinematic V-groove (radial, under the bump at 90 deg), patterned x3
    s = sk('y', 'seat_r', 'PL Seat Radius', 'PK 05 V-Groove')
    s.poly([('-(puck_V)', '-(d_puckBot)'), ('puck_V', '-(d_puckBot)'), ('0', '-(d_puckBot - puck_V)')])
    fv = ext_sym(s, CUT, 'PK V-Groove', 'puck_Vlen', bodies=[pk])
    s = sk('z', '-(d_puckBot)', 'PL Puck Bottom', 'PK 06 Magnet Pocket')
    s.circle('seat_r * cos(30 deg)', 'seat_r * sin(30 deg)', 'magPocketD')
    fm = ext(s, CUT, 'PK Magnet Pocket', 'magPocketT', POS, bodies=[pk])
    ci = F.circularPatternFeatures.createInput(coll([fv, fm]), root.zConstructionAxis)
    ci.quantity = VI.createByReal(3)
    ci.totalAngle = VI.createByString('360 deg')
    f = F.circularPatternFeatures.add(ci)
    f.name = 'PK Seat Pattern'
    # pad pocket from +X face to just past the pin, screw hole, nut slot open to +Y
    s = sk('z', '-(z_pad + pad_H / 2 + padPocket_clr / 2)', 'PL Pad Pocket Bottom', 'PK 07 Pad Pocket')
    # pocket ends just past the pad; it opens to +Y so the pad slides in from the side
    s.rect('-(pad_wall)', 'pin_D - pad_wall + pad_L + 0.3', '-(pad_W / 2 + padPocket_clr / 2)', 'col_Y / 2 + 1')
    ext(s, CUT, 'PK Pad Pocket', 'pad_H + padPocket_clr', POS, bodies=[pk])
    s = Sk(root.yZConstructionPlane, 'PK 08 Pad Screw Hole', ('y', 'z'))
    s.circle('0', '-(z_pad)', 'm3_clr')
    ext(s, CUT, 'PK Pad Screw Hole', 'col_X / 2 + 1', POS, bodies=[pk])
    s = sk('z', '-(z_pad + 3.1)', 'PL Pad Nut Slot Bottom', 'PK 09 Pad Nut Slot')
    s.rect('padNut_x', 'padNut_x + m3_pocketT', '-(m3_pocketAF / 2)', 'col_Y / 2 + 1')
    ext(s, CUT, 'PK Pad Nut Slot', '6.2', POS, bodies=[pk])
    # printed pad
    s = sk('z', '-(z_pad + pad_H / 2)', 'PL Pad Bottom', 'PD 01 Pad')
    s.rect('pin_D - pad_wall', 'pin_D - pad_wall + pad_L', '-(pad_W / 2)', 'pad_W / 2')
    name_new(ext(s, NEW, 'PD Pad', 'pad_H', POS), 'Pin Pad')
    # reference pad screw and nut
    s = sk('x', 'pin_D - pad_wall + pad_L', 'PL Pad Screw Tip', 'REF Sk Pad Screw')
    s.circle('0', '-(z_pad)', 'm3_D')
    ps = name_new(ext(s, NEW, 'REF Pad Screw Shank', 'bolt_S', POS), 'REF Pad Screw')
    s = sk('x', 'pin_D - pad_wall + pad_L + bolt_S', 'PL Pad Screw Head', 'REF Sk Pad Screw Head')
    s.circle('0', '-(z_pad)', 'm3_headD')
    ext(s, JOIN, 'REF Pad Screw Head', 'm3_headH', POS, bodies=[ps])
    s = sk('x', 'padNut_x + 0.2', 'PL Pad Nut', 'REF Sk Pad Nut')
    hexagon(s, '0', '-(z_pad)', 'm3_nutAF', math.pi / 6)
    name_new(ext(s, NEW, 'REF Pad Nut', 'm3_nutT', POS, profiles=s.hex_profiles()), 'REF Pad Nut')
    s = sk('z', '-(d_puckBot)', 'PL Puck Bottom', 'REF Sk Puck Magnets')
    s.circle('seat_r * cos(30 deg)', 'seat_r * sin(30 deg)', 'mag_D')
    s.circle('-(seat_r * cos(30 deg))', 'seat_r * sin(30 deg)', 'mag_D')
    s.circle('0', '-(seat_r)', 'mag_D')
    repair(s)
    name_all(ext(s, NEW, 'REF Puck Magnets', 'mag_T', POS), 'REF Puck Magnet')
    print(report())
