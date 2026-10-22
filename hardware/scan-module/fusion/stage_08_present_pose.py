"""Stage 08: appearances, selection sets, and the two pose moves at the very end of the
timeline (yaw about Z, then tilt about Y), driven by pose_yaw / pose_tilt. Keep both at 0 for
export; anything added later goes before these two moves."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

YAW = ['Yaw Head', 'Specimen Holder', 'REF Spring', 'REF Screw X', 'REF Screw Y', 'REF Nut X',
       'REF Nut Y', 'REF Hub Magnet', 'REF Clamp Screw', 'REF Clamp Nut', 'REF Insect', 'REF Pin']
TILT_ONLY = ['Cradle', 'REF Yaw Motor', 'REF KY-024 PCB', 'REF KY-024 Components', 'REF Hall Sensor',
             'Tilt Axle', 'Axle Spacer', 'REF Axle Bolt', 'REF Axle Nut', 'REF Flag Bolt', 'REF Flag Nut']
PRINTED = ['Fork', 'Cradle', 'Yaw Head', 'Specimen Holder', 'Tilt Axle', 'Axle Spacer', 'Carriage Washer 1', 'Carriage Washer 2',
           'Carriage Washer 3', 'Carriage Washer 4', 'Height Gauge', 'Endstop Bracket']


def find_appearance(*keys):
    lib = app.materialLibraries.itemByName('Fusion Appearance Library')
    for i in range(lib.appearances.count):
        a = lib.appearances.item(i)
        if all(k.lower() in a.name.lower() for k in keys):
            return a
    return None


def local_appearance(name, *keys):
    a = des.appearances.itemByName(name)
    if a:
        return a
    src = find_appearance(*keys)
    return des.appearances.addByCopy(src, name) if src else None


def run(_):
    printed = local_appearance('MR Printed PLA', 'plastic', 'matte', 'blue') or local_appearance('MR Printed PLA', 'plastic')
    steel = local_appearance('MR Hardware Steel', 'steel', 'satin') or local_appearance('MR Hardware Steel', 'steel')
    ref = local_appearance('MR Reference', 'plastic', 'matte', 'gray') or local_appearance('MR Reference', 'plastic')
    hw_keys = ('Screw', 'Nut', 'Bolt', 'Magnet', 'Spring', 'Pin', 'Bearing')
    sets = {'1 Printed Parts': [], '2 Hardware': [], '3 Reference': [], '4 Lens Keep-out': []}
    for b in root.bRepBodies:
        if b.name in PRINTED or b.name.startswith('Carriage Washer'):
            if printed:
                b.appearance = printed
            sets['1 Printed Parts'].append(b)
        elif b.name.startswith('REF') and any(k in b.name for k in hw_keys):
            if steel:
                b.appearance = steel
            sets['2 Hardware'].append(b)
        elif b.name == 'REF Lens Keep-out':
            b.opacity = 0.18
            sets['4 Lens Keep-out'].append(b)
        else:
            if ref:
                b.appearance = ref
            b.opacity = 0.45
            sets['3 Reference'].append(b)
    for n, bl in sets.items():
        old = des.selectionSets.itemByName(n) if hasattr(des.selectionSets, 'itemByName') else None
        if old:
            old.deleteMe()
        if bl:
            des.selectionSets.add(bl, n)
    yaw_b = [body(n) for n in YAW]
    tilt_b = yaw_b + [body(n) for n in TILT_ONLY]
    missing = [n for n, b in zip(YAW + TILT_ONLY, tilt_b) if b is None]
    if missing:
        raise RuntimeError('missing bodies %s' % missing)
    move_rot(yaw_b, root.zConstructionAxis, 'pose_yaw', 'POSE Yaw')
    move_rot(tilt_b, root.yConstructionAxis, 'pose_tilt', 'POSE Tilt')
    print('appearances', printed and printed.name, steel and steel.name, ref and ref.name)
    print(report())
