"""Stage 07c: tilt home endstop. A printed bracket on the outside of the +Y upright (two M3 x
11.8 into the nut pockets from stage 03) holds a roller microswitch beside the upright's +X
edge, lever up, in the plane the flag bolt sweeps. The switch is held by two small wood
screws in pilot holes, plus glue. It clicks when the flag reaches home_t; the flag first
touches the roller at about +90 deg. Plus reference switch, roller, screws, bolts and nuts."""
import sys, importlib, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('sw_L', '20', 'MEAS switch body length'),
    ('sw_H', '10', 'MEAS switch body height (pin edge to lever edge)'),
    ('sw_T', '5.8', 'MEAS switch body thickness'),
    ('sw_holeS', '9', 'MEAS S1 switch hole spacing'),
    ('sw_holeL', '4.7', 'MEAS L1 pivot end to first hole centre'),
    ('sw_holeH', '2.7', 'MEAS H1 pin edge to hole centres'),
    ('sw_holeD', '2.5', 'MEAS d1 switch hole diameter'),
    ('sw_rollerL', '16.4', 'MEAS L2 pivot end to roller centre (along the body)'),
    ('sw_rollerFree', '10.8', 'MEAS P1 roller top above the body, free'),
    ('sw_rollerClick', '7.1', 'MEAS P2 roller top above the body at the click'),
    ('sw_rollerD', 'sw_rollerFree - 6.2', 'REF roller diameter (P1 with roller minus P1 metal)'),
    ('sw_rollerW', '3', 'REF roller width (approx, reference only)'),
    ('sw_pinL', '3.5', 'MEAS P3 pin length below the body'),
    ('ws_D', '1.9', 'MEAS wood screw outer diameter'),
    ('ws_L', '10.5', 'MEAS wood screw length under the head (11.5 overall - 1 head)'),
    ('ws_headD', '3.2', 'MEAS wood screw head diameter'),
    ('ws_headH', '1', 'MEAS wood screw head height'),
    ('ws_pilotD', '1.5', 'pilot hole for the wood screws'),
    ('sw_Y0', '42', 'switch inner face |Y| (roller clear of the flag nut, under the flag bolt end)'),
    ('brk_T', 'bolt_S - (sw_Y0 + sw_T - up_in)', 'bracket plate thickness (M3 x 11.8 ends flush with the upright inner face)'),
    ('brk_x0', 'brk_X - 5', 'bracket -X edge'),
    ('brk_top', '9', 'bracket top edge depth below the axis (stays out of the flag sweep)'),
    ('brk_bot', 'brk_Z2 + 4', 'bracket bottom edge depth below the axis'),
    ('sw_rx', 'flag_Z * sin(home_t)', 'roller centre X: under the flag at home'),
    ('sw_px', 'sw_rx + sw_rollerL', 'switch pivot end X (pivot end towards +X)'),
    ('d_swTop', '-(flag_Z * cos(home_t)) + m3_D / 2 + sw_rollerClick', 'switch lever edge depth below the axis'),
    ('d_swHole', 'd_swTop + sw_H - sw_holeH', 'switch hole depth below the axis'),
]


def run(_):
    if not des.userParameters.itemByName('home_t'):
        des.userParameters.add('home_t', VI.createByString('97 deg'), 'deg', 'tilt home angle: the switch clicks here')
    for n, e, c in PARAMS:
        param(n, e, c)
    up_out = 'up_in + up_T'
    # bracket: pad on the upright face + plate behind the switch, one body
    s = sk('y', up_out, 'PL Upright +Y Outer', 'ES 01 Bracket Pad')
    s.rect('brk_x0', 'up_W / 2', '-(brk_bot)', '-(brk_top)')
    es = name_new(ext(s, NEW, 'ES Pad', 'sw_Y0 + sw_T + brk_T - (%s)' % up_out, POS), 'Endstop Bracket')
    s = sk('y', 'sw_Y0 + sw_T', 'PL Switch Back', 'ES 02 Bracket Plate')
    s.rect('up_W / 2', 'sw_px + 2', '-(brk_bot)', '-(brk_top)')
    ext(s, JOIN, 'ES Plate', 'brk_T', POS, bodies=[es])
    s = sk('y', up_out, 'PL Upright +Y Outer', 'ES 03 Bolt Holes')
    s.circle('brk_X', '-(brk_Z1)', 'm3_clr')
    s.circle('brk_X', '-(brk_Z2)', 'm3_clr')
    repair(s)
    ext(s, CUT, 'ES Bolt Holes', 'sw_Y0 + sw_T + brk_T - (%s)' % up_out, POS, bodies=[es])
    s = sk('y', 'sw_Y0 + sw_T', 'PL Switch Back', 'ES 04 Pilot Holes')
    s.circle('sw_px - sw_holeL', '-(d_swHole)', 'ws_pilotD')
    s.circle('sw_px - sw_holeL - sw_holeS', '-(d_swHole)', 'ws_pilotD')
    repair(s)
    ext(s, CUT, 'ES Pilot Holes', 'brk_T', POS, bodies=[es])
    # reference switch body, roller (free position) and wood screws
    s = sk('y', 'sw_Y0', 'PL Switch Front', 'REF Sk Switch')
    s.rect('sw_px - sw_L', 'sw_px', '-(d_swTop + sw_H)', '-(d_swTop)')
    name_new(ext(s, NEW, 'REF Switch Body', 'sw_T', POS), 'REF Switch')
    s = sk('y', 'sw_Y0 + sw_T / 2 - sw_rollerW / 2', 'PL Roller Side', 'REF Sk Roller')
    s.circle('sw_rx', '-(d_swTop - sw_rollerFree + sw_rollerD / 2)', 'sw_rollerD')
    name_new(ext(s, NEW, 'REF Roller', 'sw_rollerW', POS), 'REF Switch Roller')
    for i, x in enumerate(['sw_px - sw_holeL', 'sw_px - sw_holeL - sw_holeS']):
        s = sk('y', 'sw_Y0', 'PL Switch Front', 'REF Sk Wood Screw %d' % (i + 1))
        s.circle(x, '-(d_swHole)', 'ws_D')
        sc = name_new(ext(s, NEW, 'REF Wood Screw Shank %d' % (i + 1), 'ws_L', POS), 'REF Wood Screw %d' % (i + 1))
        s = sk('y', 'sw_Y0', 'PL Switch Front', 'REF Sk Wood Screw Head %d' % (i + 1))
        s.circle(x, '-(d_swHole)', 'ws_headD')
        ext(s, JOIN, 'REF Wood Screw Head %d' % (i + 1), 'ws_headH', NEG, bodies=[sc])
    # reference bracket bolts (head on the bracket) and their nuts in the upright's pockets
    for i, z in enumerate(['brk_Z1', 'brk_Z2']):
        s = sk('y', 'up_in', 'PL Upright +Y Inner', 'REF Sk Bracket Bolt %d' % (i + 1))
        s.circle('brk_X', '-(%s)' % z, 'm3_D')
        b = name_new(ext(s, NEW, 'REF Bracket Bolt Shank %d' % (i + 1), 'bolt_S', POS), 'REF Bracket Bolt %d' % (i + 1))
        s = sk('y', 'sw_Y0 + sw_T + brk_T', 'PL Bracket Back', 'REF Sk Bracket Bolt Head %d' % (i + 1))
        s.circle('brk_X', '-(%s)' % z, 'm3_headD')
        ext(s, JOIN, 'REF Bracket Bolt Head %d' % (i + 1), 'm3_headH', POS, bodies=[b])
        s = sk('y', 'up_in', 'PL Upright +Y Inner', 'REF Sk Bracket Nut %d' % (i + 1))
        hexagon(s, 'brk_X', '-(%s)' % z, 'm3_nutAF')
        name_new(ext(s, NEW, 'REF Bracket Nut %d' % (i + 1), 'm3_nutT', POS, profiles=s.hex_profiles()), 'REF Bracket Nut %d' % (i + 1))
    print(report())
