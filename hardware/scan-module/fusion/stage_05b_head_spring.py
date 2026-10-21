"""Stage 05b: spring housing on the yaw head at 225 deg (opposite the two screws), its bore,
the printed spring plunger, and the reference spring."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('spr_boreD', 'spr_OD + 0.4', 'spring bore'),
    ('spr_bossD', '8', 'spring housing outer diameter'),
    ('spr_end', '29', 'spring bore closed end, radius from the yaw axis'),
    ('plg_D', 'spr_OD - 0.3', 'plunger diameter'),
    ('plg_r0', 'plate_D / 2 - rimV + 0.6', 'plunger nose radius (cone tip sits in the rim V)'),
    ('plg_L', '3', 'plunger body length'),
    ('plg_spigotD', '2.8', 'plunger spigot inside the spring'),
    ('plg_spigotL', '2.5', 'plunger spigot length'),
]


def diag_plane():
    """Plane through the Z axis whose normal points along (-1,-1,0)/sqrt2 or its opposite."""
    p = plane_angle(root.zConstructionAxis, '45 deg', root.yZConstructionPlane, 'PL Spring Axis 225')
    n = p.geometry.normal
    if abs(abs(n.x + n.y) / 2 ** 0.5 - 1) > 1e-3:
        p.deleteMe()
        p = plane_angle(root.zConstructionAxis, '-45 deg', root.yZConstructionPlane, 'PL Spring Axis 225')
        n = p.geometry.normal
    direction = POS if (-n.x - n.y) > 0 else NEG
    return p, direction


def run(_):
    for n, e, c in PARAMS:
        param(n, e, c)
    hd = body('Yaw Head')
    p, dirn = diag_plane()
    s = Sk(p, 'HD 11 Spring Housing', ('x', 'z'))
    s.circle('0', '-(z_cx)', 'spr_bossD')
    ext_from(s, JOIN, 'HD Spring Housing', 'ring_ID / 2', 'spr_end + 1.5 - ring_ID / 2', dirn, bodies=[hd])
    s = Sk(p, 'HD 12 Spring Bore', ('x', 'z'))
    s.circle('0', '-(z_cx)', 'spr_boreD')
    ext_from(s, CUT, 'HD Spring Bore', 'plg_r0 - 0.5', 'spr_end - plg_r0 + 0.5', dirn, bodies=[hd])
    s = Sk(p, 'SP 01 Plunger', ('x', 'z'))
    s.circle('0', '-(z_cx)', 'plg_D')
    pl_body = name_new(ext_from(s, NEW, 'SP Plunger Body', 'plg_r0', 'plg_L', dirn), 'Spring Plunger')
    s = Sk(p, 'SP 02 Plunger Spigot', ('x', 'z'))
    s.circle('0', '-(z_cx)', 'plg_spigotD')
    ext_from(s, JOIN, 'SP Plunger Spigot', 'plg_r0 + plg_L', 'plg_spigotL', dirn, bodies=[pl_body])
    # cone nose: chamfer the circular edge nearest the axis
    best = None
    for e in pl_body.edges:
        g = e.geometry
        if isinstance(g, adsk.core.Circle3D) and abs(g.radius * 10 - ev('plg_D') * 5) < 1e-3:
            r = (g.center.x ** 2 + g.center.y ** 2) ** 0.5
            if best is None or r < best[0]:
                best = (r, e)
    chamfer(coll([best[1]]), 'plg_D / 2 - 0.6', 'SP Plunger Nose')
    s = Sk(p, 'REF Sk 21 Spring', ('x', 'z'))
    s.circle('0', '-(z_cx)', 'spr_OD')
    s.circle('0', '-(z_cx)', 'spr_OD - 1')
    repair(s)
    name_new(ext_from(s, NEW, 'REF Spring', 'plg_r0 + plg_L', 'spr_end - plg_r0 - plg_L', dirn, profiles=profiles_by_area(s, lambda a: a < 7)), 'REF Spring')
    # snap-off support fin under the spring housing (the head prints hub-down without supports)
    param('fin_T', '0.8', 'snap-off support fin thickness under the spring housing')
    s = sk('z', '-(d_hubBot)', 'PL Hub Bottom', 'HD 13 Support Fin')
    s.rect('ring_OD / 2 - 1', 'spr_end + 1', '-(fin_T / 2)', 'fin_T / 2')
    fin = name_new(ext(s, NEW, 'HD Support Fin', 'd_hubBot - z_cx - spr_bossD / 2 + 0.5', POS), 'TMP Support Fin')
    move_rot([fin], root.zConstructionAxis, '225 deg', 'HD Support Fin Turn')
    ci = F.combineFeatures.createInput(hd, coll([fin]))
    ci.operation = JOIN
    cf = F.combineFeatures.add(ci)
    cf.name = 'HD Support Fin Join (snap off after printing)'
    print(report())
