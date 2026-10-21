"""Stage 05c: base of the specimen holder (printed bottom-down): the centring plate disc and its
rim V-groove for the screw tips and plunger (which also stops it lifting). Stage 06 adds the
neck, clamp column and nose to the same body."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

PARAMS = [
    ('rimV', '2', 'rim V-groove depth (90 deg, 4 mm wide at the rim)'),
]


def run(_):
    for n, e, c in PARAMS:
        param(n, e, c)
    s = sk('z', '-(d_plateBot)', 'PL Ring Floor Top', 'PT 01 Plate')
    s.circle('0', '0', 'plate_D')
    pt = name_new(ext(s, NEW, 'PT Plate', 'plate_T', POS), 'Specimen Holder')
    s = Sk(root.xZConstructionPlane, 'PT 02 Rim Groove', ('x', 'z'))
    s.poly([('plate_D / 2 + 0.5', '-(z_cx + rimV + 0.5)'), ('plate_D / 2 - rimV', '-(z_cx)'), ('plate_D / 2 + 0.5', '-(z_cx - rimV - 0.5)')])
    revolve(s, root.zConstructionAxis, CUT, 'PT Rim Groove', bodies=[pt])
    print(report())
