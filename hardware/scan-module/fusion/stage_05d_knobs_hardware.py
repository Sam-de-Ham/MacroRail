"""Stage 05d: printed knobs on the two centring screws, and reference hardware in the head:
the screws, their nuts, the hub magnet and the three plate magnets."""
import sys, importlib, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('cx_tipR', 'plate_D / 2 - rimV + m3_D / 2', 'centring screw tip radius: the flat M3 end bears on both V flanks (plate centred)'),
    ('cx_headR', 'cx_tipR + bolt_S', 'centring screw under-head radius (plate centred)'),
    ('knob_D', '9', 'centring knob diameter'),
    ('knob_L', '4', 'centring knob length'),
]


def knob(axis, tag):
    if axis == 'x':
        s = sk('x', 'cx_headR', 'PL Knob X', 'KN 01 Knob %s' % tag)
        s.circle('0', '-(z_cx)', 'knob_D')
    else:
        s = sk('y', 'cx_headR', 'PL Knob Y', 'KN 01 Knob %s' % tag)
        s.circle('0', '-(z_cx)', 'knob_D')
    k = name_new(ext(s, NEW, 'KN Knob %s' % tag, 'knob_L', POS), 'Knob %s' % tag)
    s2 = sk(axis, 'cx_headR', 'PL Knob %s' % axis.upper(), 'KN 02 Knob %s Head Pocket' % tag)
    s2.circle('0', '-(z_cx)', 'm3_headD + 0.3')
    ext(s2, CUT, 'KN Knob %s Head Pocket' % tag, 'm3_headH + 0.2', POS, bodies=[k])
    s3 = sk(axis, 'cx_headR', 'PL Knob %s' % axis.upper(), 'KN 03 Knob %s Shank Hole' % tag)
    s3.circle('0', '-(z_cx)', 'm3_clr')
    ext(s3, CUT, 'KN Knob %s Shank Hole' % tag, 'knob_L', POS, bodies=[k])
    outer = [e for e in k.edges if isinstance(e.geometry, adsk.core.Circle3D) and abs(e.geometry.radius * 10 - ev('knob_D') * 5) < 1e-3]
    chamfer(coll(outer), '0.6', 'KN Knob %s Chamfer' % tag)
    # reference screw + nut
    s4 = sk(axis, 'cx_tipR', 'PL Screw Tip %s' % axis.upper(), 'REF Sk Screw %s' % tag)
    s4.circle('0', '-(z_cx)', 'm3_D')
    sc = name_new(ext(s4, NEW, 'REF Screw %s Shank' % tag, 'bolt_S', POS), 'REF Screw %s' % tag)
    s5 = sk(axis, 'cx_headR', 'PL Knob %s' % axis.upper(), 'REF Sk Screw %s Head' % tag)
    s5.circle('0', '-(z_cx)', 'm3_headD')
    ext(s5, JOIN, 'REF Screw %s Head' % tag, 'm3_headH', POS, bodies=[sc])
    s6 = sk(axis, 'nut_r + 0.2', 'PL Nut %s' % axis.upper(), 'REF Sk Nut %s' % tag)
    # flats facing the 5.7 mm slot width: on the YZ plane (X nut) that is rot pi/6, on XZ (Y nut) rot 0
    hexagon(s6, '0', '-(z_cx)', 'm3_nutAF', math.pi / 6 if axis == 'x' else 0.0)
    name_new(ext(s6, NEW, 'REF Nut %s' % tag, 'm3_nutT', POS, profiles=s6.hex_profiles()), 'REF Nut %s' % tag)


def run(_):
    for n, e, c in PARAMS:
        param(n, e, c)
    knob('x', 'X')
    knob('y', 'Y')
    s = sk('z', '-(d_hubBot)', 'PL Hub Bottom', 'REF Sk Hub Magnet')
    s.circle('ky_sensR', '0', 'mag_D')
    name_new(ext(s, NEW, 'REF Hub Magnet', 'mag_T', POS), 'REF Hub Magnet')
    s = sk('z', '-(d_plateTop + mag_T)', 'PL Plate Magnet Bottom', 'REF Sk Plate Magnets')
    s.circle('seat_r * cos(30 deg)', 'seat_r * sin(30 deg)', 'mag_D')
    s.circle('-(seat_r * cos(30 deg))', 'seat_r * sin(30 deg)', 'mag_D')
    s.circle('0', '-(seat_r)', 'mag_D')
    repair(s)
    name_all(ext(s, NEW, 'REF Plate Magnets', 'mag_T', POS), 'REF Plate Magnet')
    print(report())
