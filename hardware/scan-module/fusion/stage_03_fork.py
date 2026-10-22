"""Stage 03: the fork, one printed body: base plate on the carriage, two uprights with ribs,
608 housing (+Y), tilt motor seat (-Y)."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa


def run(_):
    zc = '-(axis_H)'
    s = sk('z', zc, 'PL Carriage Top', 'FK 01 Base')
    s.rect('-(base_LX / 2)', 'base_LX / 2', '-(base_LY / 2)', 'base_LY / 2')
    fk = name_new(ext(s, NEW, 'FK Base', 'base_T', POS), 'Fork')
    for yexp, plname, nm, t in [('up_in', 'PL Upright +Y Inner', '+Y', 'up_T'), ('-(up_in + upM_T)', 'PL Upright -Y Outer', '-Y', 'upM_T')]:
        s = sk('y', yexp, plname, 'FK 02 Upright %s' % nm)
        s.rect('-(up_W / 2)', 'up_W / 2', '-(axis_H - base_T)', '0')
        s.circle('0', '0', 'up_W')
        ext(s, JOIN, 'FK Upright %s' % nm, t, POS, bodies=[fk])
    s = sk('y', 'up_in + up_T', 'PL Upright +Y Outer', 'FK 03 Bearing Housing')
    s.circle('0', '0', 'brg_boss')
    ext(s, JOIN, 'FK Bearing Housing', 'brg_lip + brg_W - up_T', POS, bodies=[fk])
    s = sk('y', 'up_in + brg_lip', 'PL Bearing Inner Face', 'FK 04 Bearing Seat')
    s.circle('0', '0', 'brg_OD + fit_press')
    ext(s, CUT, 'FK Bearing Seat', 'brg_W + 1', POS, bodies=[fk])
    s = sk('y', 'up_in', 'PL Upright +Y Inner', 'FK 05 Bearing Lip Hole')
    s.circle('0', '0', 'brg_lipD')
    ext(s, CUT, 'FK Bearing Lip Hole', 'brg_lip', POS, bodies=[fk])
    s = sk('y', '-(up_in + upM_T)', 'PL Upright -Y Outer', 'FK 06 Motor Shaft Hole')
    s.circle('0', '0', 'tiltHoleD')
    ext(s, CUT, 'FK Motor Shaft Hole', 'upM_T', POS, bodies=[fk])
    s = sk('y', '-(up_in + upM_T)', 'PL Upright -Y Outer', 'FK 07 Motor Boss Recess')
    s.circle('0', '0', 'byj_bossD + boss_clr')
    ext(s, CUT, 'FK Motor Boss Recess', 'byj_bossH + 0.2', POS, bodies=[fk])
    s = sk('y', '-(up_in + upM_T)', 'PL Upright -Y Outer', 'FK 08 Motor Bolt Holes')
    s.circle('byj_tabS / 2', '-(byj_off)', 'm3_clr')
    s.circle('-(byj_tabS / 2)', '-(byj_off)', 'm3_clr')
    repair(s)
    ext(s, CUT, 'FK Motor Bolt Holes', 'upM_T', POS, bodies=[fk])
    s = sk('y', '-(up_in)', 'PL Upright -Y Inner', 'FK 09 Motor Bolt Counterbores')
    s.circle('byj_tabS / 2', '-(byj_off)', 'cb_D')
    s.circle('-(byj_tabS / 2)', '-(byj_off)', 'cb_D')
    repair(s)
    ext(s, CUT, 'FK Motor Bolt Counterbores', 'cb_H', NEG, bodies=[fk])
    for sx in [1, -1]:
        xe = 'rib_X' if sx > 0 else '-(rib_X)'
        for sy in [1, -1]:
            yo = 'up_in + up_T' if sy > 0 else '-(up_in + upM_T)'
            ye = 'base_LY / 2' if sy > 0 else '-(base_LY / 2)'
            tag = '%s%s' % ('X+' if sx > 0 else 'X-', 'Y+' if sy > 0 else 'Y-')
            s = sk('x', xe, 'PL Rib %s' % ('X+' if sx > 0 else 'X-'), 'FK 10 Rib %s' % tag)
            s.poly([(yo, '-(axis_H - base_T)'), (ye, '-(axis_H - base_T)'), (yo, '-(axis_H - base_T - rib_H)')])
            ext_sym(s, JOIN, 'FK Rib %s' % tag, 'rib_T', bodies=[fk])
    s = sk('z', zc, 'PL Carriage Top', 'FK 11 Carriage Bolt Holes')
    for sx in [1, -1]:
        for sy in [1, -1]:
            s.circle('carr_hx / 2' if sx > 0 else '-(carr_hx / 2)', 'carr_hy / 2' if sy > 0 else '-(carr_hy / 2)', 'm3_clr')
    repair(s)
    ext(s, CUT, 'FK Carriage Bolt Holes', 'base_T', POS, bodies=[fk])
    s = sk('z', zc, 'PL Carriage Top', 'FK 12 Screw Head Pockets')
    for Y in ['carr_headY1', 'carr_headY2']:
        for sx in [1, -1]:
            for sy in [1, -1]:
                s.circle('carr_headX1' if sx > 0 else '-(carr_headX1)', Y if sy > 0 else '-(%s)' % Y, 'carr_headD + pocket_clr')
    repair(s)
    ext(s, CUT, 'FK Screw Head Pockets', 'carr_headH + 0.5', POS, bodies=[fk])
    # endstop bracket interface: two M3 holes through the +Y upright, nut pockets on its inner face
    s = sk('y', 'up_in', 'PL Upright +Y Inner', 'FK 13 Endstop Bracket Holes')
    s.circle('brk_X', '-(brk_Z1)', 'm3_clr')
    s.circle('brk_X', '-(brk_Z2)', 'm3_clr')
    repair(s)
    ext(s, CUT, 'FK Endstop Bracket Holes', 'up_T', POS, bodies=[fk])
    s = sk('y', 'up_in', 'PL Upright +Y Inner', 'FK 14 Endstop Bracket Nut Pockets')
    hexagon(s, 'brk_X', '-(brk_Z1)', 'm3_pocketAF')
    hexagon(s, 'brk_X', '-(brk_Z2)', 'm3_pocketAF')
    ext(s, CUT, 'FK Endstop Bracket Nut Pockets', 'm3_pocketT', POS, bodies=[fk], profiles=s.hex_profiles())
    print(report())
