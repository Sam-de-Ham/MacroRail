"""Stage 06: the top of the specimen holder, joined to the plate from stage 05c: neck disc,
clamp column, 45-deg tapered nose, pin hole on the yaw axis (through the whole holder), pad
pocket + M3 pad screw from +X with its nut slot (open to +Y). Plus the printed pad and
reference pad screw and nut. Specimens change by swapping the pin, so the holder stays on."""
import sys, importlib, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('col_Y', '14', 'clamp column size across (no overhang under the nose base)'),
    ('pinHoleD', '1', 'pin hole through nose and puck (pins 00-1 = 0.30-0.40)'),
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
    s = sk('z', '-(d_puckBot)', 'PL Puck Bottom', 'PK 01 Neck')
    s.circle('0', '0', 'puck_D')
    pk = body('Specimen Holder')
    ext(s, JOIN, 'PK Neck', 'puck_T', POS, bodies=[pk])
    s = sk('z', '-(d_puckTop)', 'PL Puck Top', 'PK 02 Column')
    s.rect('-(col_X / 2)', 'col_X / 2', '-(col_Y / 2)', 'col_Y / 2')
    ext(s, JOIN, 'PK Column', 'col_H', POS, bodies=[pk])
    s = Sk(root.xZConstructionPlane, 'PK 03 Nose', ('x', 'z'))
    s.poly([('0', '-(d_colTop)'), ('nose_baseD / 2', '-(d_colTop)'), ('nose_tipD / 2', '-(d_noseTip)'), ('0', '-(d_noseTip)')])
    revolve(s, root.zConstructionAxis, JOIN, 'PK Nose', bodies=[pk])
    s = sk('z', '-(d_plateBot)', 'PL Ring Floor Top', 'PK 04 Pin Hole')
    s.circle('0', '0', 'pinHoleD')
    ext(s, CUT, 'PK Pin Hole', 'd_plateBot - d_noseTip + 1', POS, bodies=[pk])
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
    print(report())
