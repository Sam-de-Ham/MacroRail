"""Stage 10: exploded view for the assembly guide, driven by `explode` (0 = assembled, 1 =
exploded). One Move per group at the very end of the timeline. Keep explode at 0 for export."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

GROUPS = [
    ('Pin', (0, 0, 90), ['REF Pin', 'REF Insect']),
    ('Holder', (0, 0, 62), ['Specimen Holder']),
    ('Pad', (16, 0, 62), ['Pin Pad']),
    ('Pad Screw', (34, 0, 62), ['REF Pad Screw']),
    ('Pad Nut', (0, 16, 62), ['REF Pad Nut']),
    ('Screw X', (30, 0, 32), ['REF Screw X']),
    ('Screw Y', (0, 30, 32), ['REF Screw Y']),
    ('Head Nuts', (0, 0, 44), ['REF Nut X', 'REF Nut Y']),
    ('Plunger', (-18, -18, 32), ['Spring Plunger', 'REF Spring']),
    ('Head', (0, 0, 32), ['Yaw Head']),
    ('Hub Magnet', (0, 0, 20), ['REF Hub Magnet']),
    ('Yaw Motor', (0, 0, -30), ['REF Yaw Motor']),
    ('KY-024', (0, 0, -50), ['REF KY-024 PCB', 'REF KY-024 Components']),
    ('Hall Sensor', (0, 0, 10), ['REF Hall Sensor']),
    ('Tilt Motor', (0, -48, 0), ['REF Tilt Motor']),
    ('Axle', (0, 52, 0), ['Tilt Axle']),
    ('Spacer', (0, 28, 0), ['Axle Spacer']),
    ('Axle Bolt', (0, 82, 0), ['REF Axle Bolt']),
    ('Bearing', (0, 40, 0), ['REF 608 Bearing']),
    ('Flag Bolt', (0, -18, 0), ['REF Flag Bolt']),
    ('Flag Nut', (0, 14, 0), ['REF Flag Nut']),
    ('Endstop Bracket', (0, 30, -75), ['Endstop Bracket']),
    ('Switch', (0, 14, -75), ['REF Switch', 'REF Switch Roller']),
    ('Wood Screws', (0, -2, -75), ['REF Wood Screw 1', 'REF Wood Screw 2']),
    ('Bracket Bolts', (0, 50, -75), ['REF Bracket Bolt 1', 'REF Bracket Bolt 2']),
    ('Bracket Nuts', (0, -5, -75), ['REF Bracket Nut 1', 'REF Bracket Nut 2']),
    ('Fork', (0, 0, -75), ['Fork']),
    ('Carriage Bolts', (0, 0, -45), ['REF Carriage Bolt 1', 'REF Carriage Bolt 2', 'REF Carriage Bolt 3', 'REF Carriage Bolt 4',
                                     'REF Carriage Bolt Head 1', 'REF Carriage Bolt Head 2', 'REF Carriage Bolt Head 3', 'REF Carriage Bolt Head 4']),
    ('Carriage', (0, 0, -115), ['REF Carriage']),
    ('Washers', (0, 0, -132), ['Carriage Washer 1', 'Carriage Washer 2', 'Carriage Washer 3', 'Carriage Washer 4']),
]


def run(_):
    if not des.userParameters.itemByName('explode'):
        des.userParameters.add('explode', VI.createByString('0'), '', 'EXPLODE 0 = assembled, 1 = exploded (guide pictures only)')
    for name, (dx, dy, dz), bodies in GROUPS:
        bl = [body(n) for n in bodies]
        missing = [n for n, b in zip(bodies, bl) if b is None]
        if missing:
            raise RuntimeError('missing %s' % missing)
        move_xyz(bl, '%d mm * explode' % dx, '%d mm * explode' % dy, '%d mm * explode' % dz, 'EXPLODE %s' % name)
    print(report())
