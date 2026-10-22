"""Stage 02: reference bodies (not printed): carriage, objective + lens keep-out zone, insect,
pin, 608 bearing, both 28BYJ-48s, KY-024, hall sensor."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa


def carriage_objective():
    s = sk('z', '-(axis_H)', 'PL Carriage Top', 'REF Sk 01 Carriage')
    s.rect('-(carr_LX / 2)', 'carr_LX / 2', '-(carr_LY / 2 - carr_yOff)', 'carr_LY / 2 + carr_yOff')
    b = name_new(ext(s, NEW, 'REF Carriage Plate', 'carr_T', NEG), 'REF Carriage')
    s = sk('z', '-(axis_H)', 'PL Carriage Top', 'REF Sk 02 Carriage Holes')
    for sx in [1, -1]:
        for sy in [1, -1]:
            s.circle('carr_hx / 2' if sx > 0 else '-(carr_hx / 2)', 'carr_hy / 2' if sy > 0 else '-(carr_hy / 2)', 'carr_holeD')
    repair(s)
    ext(s, CUT, 'REF Carriage Holes', 'carr_T', NEG, bodies=[b])
    s = sk('z', '-(axis_H)', 'PL Carriage Top', 'REF Sk 03 Screw Heads')
    for X in ['carr_headX1', 'carr_headX2']:
        for Y in ['carr_headY1', 'carr_headY2']:
            for sx in [1, -1]:
                for sy in [1, -1]:
                    s.circle(X if sx > 0 else '-(%s)' % X, Y if sy > 0 else '-(%s)' % Y, 'carr_headD')
    repair(s)
    ext(s, JOIN, 'REF Carriage Screw Heads', 'carr_headH', POS, bodies=[b])
    for nm, c in [('Objective', '0'), ('Lens Keep-out', 'lens_clr')]:
        s = Sk(root.xZConstructionPlane, 'REF Sk %s' % nm, ('x', 'z'))
        k = '' if c == '0' else ' + %s' % c
        s.poly([('obj_WD%s' % ('' if c == '0' else ' - %s' % c), '0'),
                ('obj_WD%s' % ('' if c == '0' else ' - %s' % c), 'obj_sleeveD / 2%s' % k),
                ('obj_WD + obj_L1', 'obj_sleeveD / 2%s' % k),
                ('obj_WD + obj_L1', 'obj_knurlD / 2%s' % k),
                ('obj_WD + obj_L2', 'obj_knurlD / 2%s' % k),
                ('obj_WD + obj_L2', 'obj_adapterD / 2%s' % k),
                ('obj_WD + obj_L2 + obj_tubeL', 'obj_adapterD / 2%s' % k),
                ('obj_WD + obj_L2 + obj_tubeL', '0')])
        name_new(revolve(s, root.xConstructionAxis, NEW, 'REF %s' % nm), 'REF %s' % nm)


def insect_pin_bearing():
    s = sk('z', '-(insect_D / 2)', 'PL Insect Bottom', 'REF Sk 06 Insect')
    s.circle('0', '0', 'insect_D')
    name_new(ext(s, NEW, 'REF Insect', 'insect_D', POS), 'REF Insect')
    s = sk('z', '-(insect_D / 2)', 'PL Insect Bottom', 'REF Sk 07 Pin')
    s.circle('0', '0', 'pin_D')
    name_new(ext(s, NEW, 'REF Pin', 'pin_L - insect_D / 2', NEG), 'REF Pin')
    s = sk('y', 'up_in + brg_lip', 'PL Bearing Inner Face', 'REF Sk 08 Bearing')
    s.circle('0', '0', 'brg_OD')
    s.circle('0', '0', 'brg_ID')
    name_new(ext(s, NEW, 'REF 608 Bearing', 'brg_W', POS, profiles=profiles_by_area(s, lambda a: a > 100)), 'REF 608 Bearing')


def motors():
    Z = '-(d_floorBot)'
    s = sk('z', Z, 'PL Floor Underside', 'REF Sk 10 Yaw Motor Body')
    s.circle('-(byj_off)', '0', 'byj_D')
    m = name_new(ext(s, NEW, 'REF Yaw Motor Body', 'byj_H', NEG), 'REF Yaw Motor')
    s = sk('z', Z, 'PL Floor Underside', 'REF Sk 11 Yaw Motor Tabs')
    s.rect('-(byj_off + byj_earR)', '-(byj_off - byj_earR)', '-(byj_tabS / 2)', 'byj_tabS / 2')
    s.circle('-(byj_off)', 'byj_tabS / 2', '2 * byj_earR')
    s.circle('-(byj_off)', '-(byj_tabS / 2)', '2 * byj_earR')
    repair(s)
    ext(s, JOIN, 'REF Yaw Motor Tabs', 'byj_tabT', NEG, bodies=[m])
    s = sk('z', Z, 'PL Floor Underside', 'REF Sk 12 Yaw Motor Tab Holes')
    s.circle('-(byj_off)', 'byj_tabS / 2', 'byj_tabHoleD')
    s.circle('-(byj_off)', '-(byj_tabS / 2)', 'byj_tabHoleD')
    repair(s)
    ext(s, CUT, 'REF Yaw Motor Tab Holes', 'byj_tabT', NEG, bodies=[m])
    s = sk('z', Z, 'PL Floor Underside', 'REF Sk 13 Yaw Motor Boss')
    s.circle('0', '0', 'byj_bossD')
    ext(s, JOIN, 'REF Yaw Motor Boss', 'byj_bossH', POS, bodies=[m])
    s = sk('z', '-(d_floorBot - byj_bossH)', 'PL Yaw Boss Top', 'REF Sk 14 Yaw Motor Shaft')
    s.circle('0', '0', 'byj_shaftD')
    ext(s, JOIN, 'REF Yaw Motor Shaft', 'byj_shaftL', POS, bodies=[m])
    s = sk('z', '-(d_floorBot - byj_bossH - byj_shaftL + byj_flatL)', 'PL Yaw Flats Start', 'REF Sk 15 Yaw Motor Flats')
    s.rect('byj_flat / 2', 'byj_shaftD / 2 + 1', '-(byj_shaftD / 2 + 1)', 'byj_shaftD / 2 + 1')
    s.rect('-(byj_shaftD / 2 + 1)', '-(byj_flat / 2)', '-(byj_shaftD / 2 + 1)', 'byj_shaftD / 2 + 1')
    ext(s, CUT, 'REF Yaw Motor Flats', 'byj_flatL', POS, bodies=[m])
    s = sk('z', Z, 'PL Floor Underside', 'REF Sk 16 Yaw Motor Wire Box')
    s.rect('-(byj_off + byj_D / 2 + byj_boxP)', '-(byj_off + byj_D / 2 - 4)', '-(byj_boxW / 2)', 'byj_boxW / 2')
    ext(s, JOIN, 'REF Yaw Motor Wire Box', 'byj_boxH', NEG, bodies=[m])
    # tilt motor: a linked copy, turned and moved onto the -Y upright
    t = copy_body(m, 'REF Tilt Motor')
    move_rot([t], root.zConstructionAxis, '-90 deg', 'REF Tilt Motor Turn 1')
    move_rot([t], root.xConstructionAxis, '-90 deg', 'REF Tilt Motor Turn 2')
    move_xyz([t], '0 mm', 'd_floorBot - up_in - upM_T', '0 mm', 'REF Tilt Motor Place')


def ky024():
    Z = '-(d_floorBot)'
    s = sk('z', Z, 'PL Floor Underside', 'REF Sk 17 KY-024')
    s.rect('ky_x0', 'ky_x0 + ky_W', '-(ky_L - ky_y0)', 'ky_y0')
    k = name_new(ext(s, NEW, 'REF KY-024 PCB', 'ky_pcbT', NEG), 'REF KY-024 PCB')
    s = sk('z', '-(d_floorBot + ky_pcbT)', 'PL KY Components', 'REF Sk 18 KY-024 Components')
    s.rect('ky_x0', 'ky_x0 + ky_W', '-(ky_L - ky_y0)', 'ky_y0')
    kc = name_new(ext(s, NEW, 'REF KY-024 Components', 'ky_T - ky_pcbT', NEG), 'REF KY-024 Components')
    s = sk('z', Z, 'PL Floor Underside', 'REF Sk 19 KY-024 Hole')
    s.circle('ky_x0 + ky_W / 2', '-(ky_L - ky_y0 - ky_holeY)', '3')
    ext(s, CUT, 'REF KY-024 Hole', 'ky_T', NEG, bodies=[k, kc])
    s = sk('z', '-(d_floorTop + sens_pocket)', 'PL Sensor Pocket Floor', 'REF Sk 20 Hall Sensor')
    s.rect('ky_sensR - to92_H / 2', 'ky_sensR + to92_H / 2', '-(to92_W / 2)', 'to92_W / 2')
    name_new(ext(s, NEW, 'REF Hall Sensor', 'to92_T', POS), 'REF Hall Sensor')


def run(_):
    carriage_objective()
    insect_pin_bearing()
    motors()
    ky024()
    print(report())
