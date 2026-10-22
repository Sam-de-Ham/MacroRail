"""Stage 06: the top of the specimen holder, joined to the plate from stage 05c: neck disc,
clamp column, 45-deg tapered nose and the pin hole on the yaw axis (through the whole holder).
Pin clamp: one M3 screw on a straight line along +X, through a captive nut (slot open to +Y,
flats up and down so it can't turn), its tip pressing the pin against the far end of the
screw hole. No pad (user, after the test print). Plus the reference clamp screw and nut."""
import sys, importlib, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('col_Y', '14', 'clamp column size across (no overhang under the nose base)'),
    ('pinHoleD', '1.2', 'pin hole through nose and holder (pins 00-1 = 0.30-0.40; 1.0 was tight, test print)'),
    ('z_clamp', 'd_colTop + col_H / 2', 'depth of the clamp screw axis'),
    ('clampNut_x', '3', 'captive nut slot inner face, X'),
    ('clampNut_H', 'm3_nutAF + 0.3', 'nut slot height: flats up/down, under the 6.0 corner size so the nut cannot turn'),
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
    # clamp screw hole: straight along X from the +X face to the far wall of the pin hole
    s = sk('x', '-(pinHoleD / 2)', 'PL Clamp Hole End', 'PK 07 Clamp Screw Hole')
    s.circle('0', '-(z_clamp)', 'm3_clr')
    ext(s, CUT, 'PK Clamp Screw Hole', 'col_X / 2 + pinHoleD / 2 + 1', POS, bodies=[pk])
    # captive nut slot, open to +Y (push the nut in, corners along Y)
    s = sk('z', '-(z_clamp + clampNut_H / 2)', 'PL Clamp Nut Slot Bottom', 'PK 08 Clamp Nut Slot')
    s.rect('clampNut_x', 'clampNut_x + m3_pocketT', '-(m3_nutAF / sqrt(3) + 0.1)', 'col_Y / 2 + 1')
    ext(s, CUT, 'PK Clamp Nut Slot', 'clampNut_H', POS, bodies=[pk])
    # reference clamp screw (tip on a centred pin) and nut
    s = sk('x', 'pin_D / 2', 'PL Clamp Screw Tip', 'REF Sk Clamp Screw')
    s.circle('0', '-(z_clamp)', 'm3_D')
    cs = name_new(ext(s, NEW, 'REF Clamp Screw Shank', 'bolt_S', POS), 'REF Clamp Screw')
    s = sk('x', 'pin_D / 2 + bolt_S', 'PL Clamp Screw Head', 'REF Sk Clamp Screw Head')
    s.circle('0', '-(z_clamp)', 'm3_headD')
    ext(s, JOIN, 'REF Clamp Screw Head', 'm3_headH', POS, bodies=[cs])
    s = sk('x', 'clampNut_x + 0.2', 'PL Clamp Nut', 'REF Sk Clamp Nut')
    hexagon(s, '0', '-(z_clamp)', 'm3_nutAF')
    name_new(ext(s, NEW, 'REF Clamp Nut', 'm3_nutT', POS, profiles=s.hex_profiles()), 'REF Clamp Nut')
    print(report())
