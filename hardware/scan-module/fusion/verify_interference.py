"""Verification: interference between all bodies at the rest pose (coincident faces excluded),
and the yaw head's clearance to the cradle all the way round."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

SKIP = ('REF Lens Keep-out', 'REF Objective')


def run(_):
    mode = globals().get('MODE', 'static')
    if mode == 'static':
        bodies = coll([b for b in root.bRepBodies if b.name not in SKIP])
        inp = des.createInterferenceInput(bodies)
        inp.areCoincidentFacesIncluded = False
        res = des.analyzeInterference(inp)
        for r in res:
            print('%-24s x %-24s %8.3f mm3' % (r.entityOne.name, r.entityTwo.name, r.interferenceBody.volume * 1000))
        print('pairs', res.count)
    else:
        mm = app.measureManager
        cr = body('Cradle')
        # the flag bolt must clear the fork over the whole tilt range
        pt = des.userParameters.itemByName('pose_tilt')
        fl = (1e9, None)
        for t in range(-35, 101, 5):
            pt.expression = '%d deg' % t
            for n in ('REF Flag Bolt', 'REF Flag Nut'):
                d = mm.measureMinimumDistance(body('Fork'), body(n)).value * 10
                if d < fl[0]:
                    fl = (d, '%s @ tilt %d' % (n, t))
        pt.expression = '0 deg'
        print('flag vs fork min %.2f mm (%s)' % fl)
        heads = ['Yaw Head', 'Spring Plunger', 'Centring Plate', 'Puck', 'REF Pad Screw', 'REF Screw X', 'REF Screw Y']
        py = des.userParameters.itemByName('pose_yaw')
        worst = (1e9, None, None)
        for y in range(0, 360, 15):
            py.expression = '%d deg' % y
            for n in heads:
                d = mm.measureMinimumDistance(cr, body(n)).value * 10
                if d < worst[0]:
                    worst = (d, n, y)
        py.expression = '0 deg'
        print('head vs cradle min %.2f mm (%s @ yaw %s)' % worst)
        h = body('REF Hall Sensor')
        best = (1e9, None)
        for y in range(0, 360, 5):
            py.expression = '%d deg' % y
            d = mm.measureMinimumDistance(h, body('REF Hub Magnet')).value * 10
            if d < best[0]:
                best = (d, y)
        py.expression = '0 deg'
        print('hall sensor to hub magnet: closest %.2f mm at yaw %s' % best)
