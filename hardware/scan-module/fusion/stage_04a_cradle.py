"""Stage 04a: the cradle body: floor, two arms with rounded counterweight tops, tilt hubs.
-Y arm: double-D bore on the tilt motor shaft. +Y arm: socket + bolt + nut for the axle."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa


def run(_):
    s = sk('z', '-(d_floorBot)', 'PL Floor Underside', 'CR 01 Floor')
    s.rect('-(floor_back)', 'floor_front', '-(arm_in + arm_T)', 'arm_in + arm_T')
    cr = name_new(ext(s, NEW, 'CR Floor', 'floor_T', POS), 'Cradle')
    for side, yexp, plname, nm in [(1, 'arm_in', 'PL Arm +Y Inner', '+Y'), (-1, '-(arm_in + arm_T)', 'PL Arm -Y Outer', '-Y')]:
        s = sk('y', yexp, plname, 'CR 02 Arm %s' % nm)
        s.rect('-(arm_W / 2)', 'arm_W / 2', '-(d_floorBot)', 'arm_top - arm_W / 2')
        s.circle('0', 'arm_top - arm_W / 2', 'arm_W')
        ext(s, JOIN, 'CR Arm %s' % nm, 'arm_T', POS, bodies=[cr])
    s = sk('y', 'arm_in', 'PL Arm +Y Inner', 'CR 03 Hub Boss +Y')
    s.circle('0', '0', 'hubBoss_D')
    ext(s, JOIN, 'CR Hub Boss +Y', 'hubBoss_in', NEG, bodies=[cr])
    s = sk('y', '-(arm_in)', 'PL Arm -Y Inner', 'CR 04 Hub Boss -Y')
    s.circle('0', '0', 'hubBoss_D')
    ext(s, JOIN, 'CR Hub Boss -Y', 'hubBoss_in', POS, bodies=[cr])
    s = sk('y', '-(arm_in + arm_T)', 'PL Arm -Y Outer', 'CR 05 Tilt D-Bore')
    pr = dd_bore(s, '0', '0', 'byj_shaftD + fit_D', 'byj_flat + fit_D', 'x')
    ext(s, CUT, 'CR Tilt D-Bore', 'tiltBoreDepth', POS, bodies=[cr], profiles=pr)
    s = sk('y', 'arm_in + arm_T', 'PL Arm +Y Outer', 'CR 06 Axle Socket')
    s.circle('0', '0', 'axle_spigotD + fit_slide / 2')
    ext(s, CUT, 'CR Axle Socket', 'axle_spigotL + 0.5', NEG, bodies=[cr])
    s = sk('y', 'arm_in - hubBoss_in', 'PL Hub Boss +Y Face', 'CR 07 Axle Bolt Hole')
    s.circle('0', '0', 'm3_clr')
    ext(s, CUT, 'CR Axle Bolt Hole', 'hubBoss_in + arm_T', POS, bodies=[cr])
    s = sk('y', 'arm_in - hubBoss_in', 'PL Hub Boss +Y Face', 'CR 08 Axle Nut Pocket')
    hexagon(s, '0', '0', 'm3_pocketAF')
    ext(s, CUT, 'CR Axle Nut Pocket', 'm3_pocketT', POS, bodies=[cr], profiles=s.hex_profiles())
    s = Sk(root.xZConstructionPlane, 'CR 09 Counterweight Hole', ('x', 'z'))
    s.circle('0', 'cw_Z', 'cw_holeD')
    ext_sym(s, CUT, 'CR Counterweight Hole', '2 * (arm_in + arm_T) + 4', bodies=[cr])
    # tilt home flag: an M3 x 17.5 bolt through the +Y arm (head inside, nut outside); its end
    # passes the endstop lever just past +90 deg
    s = sk('y', 'arm_in', 'PL Arm +Y Inner', 'CR 10 Flag Bolt Hole')
    s.circle('0', 'flag_Z', 'm3_clr')
    ext(s, CUT, 'CR Flag Bolt Hole', 'arm_T', POS, bodies=[cr])
    print(report())
