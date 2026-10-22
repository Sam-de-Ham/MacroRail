"""Exports the print files: exports/test-pieces (the TP slices plus the small parts that are
their own test) and exports/final (every printed part). Poses and explode are set to 0 first,
so the STLs are in model coordinates at rest."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'exports')
TEST = ['TP Bearing Seat', 'TP Motor Seat', 'TP Base Holes', 'TP Tilt D-Bore', 'TP Axle Socket',
        'TP Cradle Floor', 'Yaw Head', 'Specimen Holder',
        'Tilt Axle', 'Axle Spacer', 'Endstop Bracket']
FINAL = ['Fork', 'Cradle', 'Yaw Head', 'Specimen Holder',
         'Tilt Axle', 'Axle Spacer', 'Carriage Washer 1', 'Height Gauge', 'Endstop Bracket']


def fname(name):
    return name.replace('Carriage Washer 1', 'Carriage Washer').lower().replace(' ', '-') + '.stl'


def run(_):
    for p in ('explode', 'pose_tilt', 'pose_yaw'):
        des.userParameters.itemByName(p).expression = '0' if p == 'explode' else '0 deg'
    em = des.exportManager
    for folder, names in (('test-pieces', TEST), ('final', FINAL)):
        d = os.path.join(OUT, folder)
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            if f.endswith('.stl'):
                os.remove(os.path.join(d, f))
        for n in names:
            b = body(n)
            o = em.createSTLExportOptions(b, os.path.join(d, fname(n)))
            o.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
            em.execute(o)
        print(folder, len(os.listdir(d)))
