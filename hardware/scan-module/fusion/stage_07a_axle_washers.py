"""Stage 07: tilt axle (flange outside the 608, shank through the bearing and spacer, spigot into
the +Y arm), axle spacer, four carriage washers, reference axle bolt + carriage bolts + nuts,
(the pin height gauge is stage 07b)."""
import sys, importlib, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('axle_D', 'brg_ID - 0.05', 'axle shank in the 608 bore'),
    ('axle_flangeD', '11.5', 'axle flange (clamps the inner race only)'),
    ('axle_flangeT', '1.5', 'axle flange thickness'),
    ('spacer_OD', '11', 'spacer between arm and inner race'),
    ('y_armOut', 'arm_in + arm_T', 'arm outer face |Y|'),
    ('y_brgIn', 'up_in + brg_lip', 'bearing inner face Y'),
    ('y_brgOut', 'up_in + brg_lip + brg_W', 'bearing outer face Y'),
    ('bolt_L', '25.8', 'long M3 bolt under head (27.7 overall assumed)'),
    ('wash_D', '9', 'printed washer diameter'),
    ('wash_T', '1.5', 'printed washer thickness'),
    ('gauge_step', '6', 'height gauge step length'),
    ('gauge_W', '12', 'height gauge width'),
    ('gauge_slot', '2', 'height gauge pin slot'),
    ('gauge_h0', '17', 'lowest gauge step above the nose tip'),
    ('gauge_park', '110', 'height gauge parked at X = -gauge_park, behind the module (tool, not mounted)'),
]


def run(_):
    for n, e, c in PARAMS:
        param(n, e, c)
    # axle
    s = sk('y', 'y_brgOut', 'PL Bearing Outer Face', 'AX 01 Axle Flange')
    s.circle('0', '0', 'axle_flangeD')
    ax = name_new(ext(s, NEW, 'AX Flange', 'axle_flangeT', POS), 'Tilt Axle')
    s = sk('y', 'y_brgOut', 'PL Bearing Outer Face', 'AX 02 Axle Shank')
    s.circle('0', '0', 'axle_D')
    ext(s, JOIN, 'AX Shank', 'y_brgOut - y_armOut', NEG, bodies=[ax])
    s = sk('y', 'y_armOut', 'PL Arm +Y Outer', 'AX 03 Axle Spigot')
    s.circle('0', '0', 'axle_spigotD')
    ext(s, JOIN, 'AX Spigot', 'axle_spigotL', NEG, bodies=[ax])
    s = sk('y', 'y_brgOut + axle_flangeT', 'PL Axle Flange Outer', 'AX 04 Axle Bore')
    s.circle('0', '0', 'm3_clr')
    ext(s, CUT, 'AX Bore', 'y_brgOut + axle_flangeT - y_armOut + axle_spigotL', NEG, bodies=[ax])
    # spacer
    s = sk('y', 'y_armOut', 'PL Arm +Y Outer', 'AS 01 Spacer')
    s.circle('0', '0', 'spacer_OD')
    s.circle('0', '0', 'axle_D + 0.3')
    repair(s)
    name_new(ext(s, NEW, 'AS Spacer', 'y_brgIn - y_armOut', POS, profiles=coll([s.s.profiles.item(k) for k in range(s.s.profiles.count) if s.s.profiles.item(k).profileLoops.count == 2])), 'Axle Spacer')
    # reference axle bolt + nut
    s = sk('y', 'y_brgOut + axle_flangeT', 'PL Axle Flange Outer', 'REF Sk Axle Bolt')
    s.circle('0', '0', 'm3_D')
    ab = name_new(ext(s, NEW, 'REF Axle Bolt Shank', 'bolt_L', NEG), 'REF Axle Bolt')
    s = sk('y', 'y_brgOut + axle_flangeT', 'PL Axle Flange Outer', 'REF Sk Axle Bolt Head')
    s.circle('0', '0', 'm3_headD')
    ext(s, JOIN, 'REF Axle Bolt Head', 'm3_headH', POS, bodies=[ab])
    s = sk('y', 'arm_in - hubBoss_in + 0.2', 'PL Axle Nut', 'REF Sk Axle Nut')
    hexagon(s, '0', '0', 'm3_nutAF')
    name_new(ext(s, NEW, 'REF Axle Nut', 'm3_nutT', POS, profiles=s.hex_profiles()), 'REF Axle Nut')
    # reference tilt home flag bolt + nut
    s = sk('y', 'arm_in', 'PL Arm +Y Inner', 'REF Sk Flag Bolt')
    s.circle('0', 'flag_Z', 'm3_D')
    fb = name_new(ext(s, NEW, 'REF Flag Bolt Shank', 'bolt_M', POS), 'REF Flag Bolt')
    s = sk('y', 'arm_in', 'PL Arm +Y Inner', 'REF Sk Flag Bolt Head')
    s.circle('0', 'flag_Z', 'm3_headD')
    ext(s, JOIN, 'REF Flag Bolt Head', 'm3_headH', NEG, bodies=[fb])
    s = sk('y', 'arm_in + arm_T', 'PL Arm +Y Outer', 'REF Sk Flag Nut')
    hexagon(s, '0', 'flag_Z', 'm3_nutAF')
    name_new(ext(s, NEW, 'REF Flag Nut', 'm3_nutT', POS, profiles=s.hex_profiles()), 'REF Flag Nut')
    # carriage washers (printed) + reference bolts and nuts
    zb = '-(axis_H + carr_T)'
    s = sk('z', zb, 'PL Carriage Underside', 'WS 01 Washers')
    for sx in [1, -1]:
        for sy in [1, -1]:
            s.circle('carr_hx / 2' if sx > 0 else '-(carr_hx / 2)', 'carr_hy / 2' if sy > 0 else '-(carr_hy / 2)', 'wash_D')
    repair(s)
    name_all(ext(s, NEW, 'WS Washers', 'wash_T', NEG), 'Carriage Washer')
    s = sk('z', zb, 'PL Carriage Underside', 'WS 02 Washer Holes')
    for sx in [1, -1]:
        for sy in [1, -1]:
            s.circle('carr_hx / 2' if sx > 0 else '-(carr_hx / 2)', 'carr_hy / 2' if sy > 0 else '-(carr_hy / 2)', 'm3_clr')
    repair(s)
    ext(s, CUT, 'WS Washer Holes', 'wash_T', NEG, bodies=[b for b in root.bRepBodies if b.name.startswith('Carriage Washer')])
    s = sk('z', '-(axis_H - base_T)', 'PL Base Top', 'REF Sk Carriage Bolts')
    for sx in [1, -1]:
        for sy in [1, -1]:
            s.circle('carr_hx / 2' if sx > 0 else '-(carr_hx / 2)', 'carr_hy / 2' if sy > 0 else '-(carr_hy / 2)', 'm3_D')
    repair(s)
    name_all(ext(s, NEW, 'REF Carriage Bolt Shanks', 'bolt_M', NEG), 'REF Carriage Bolt')
    s = sk('z', '-(axis_H - base_T)', 'PL Base Top', 'REF Sk Carriage Bolt Heads')
    for sx in [1, -1]:
        for sy in [1, -1]:
            s.circle('carr_hx / 2' if sx > 0 else '-(carr_hx / 2)', 'carr_hy / 2' if sy > 0 else '-(carr_hy / 2)', 'm3_headD')
    repair(s)
    name_all(ext(s, NEW, 'REF Carriage Bolt Heads', 'm3_headH', POS), 'REF Carriage Bolt Head')
    print(report())
