"""Verification (global MODE): static = interference between all bodies at the rest pose
(coincident faces excluded); flag = the tilt home flag against the fork, bracket, switch and
roller; yaw = the yaw head's clearance to the cradle all the way round, and the hall sensor."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'verify.log')


def out(line):
    """Print and append to verify.log (a timed-out MCP call loses its printed output)."""
    print(line)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + chr(10))

SKIP = ('REF Lens Keep-out', 'REF Objective')


def run(_):
    mode = globals().get('MODE', 'static')
    if mode == 'static':
        bodies = coll([b for b in root.bRepBodies if b.name not in SKIP])
        inp = des.createInterferenceInput(bodies)
        inp.areCoincidentFacesIncluded = False
        res = des.analyzeInterference(inp)
        for r in res:
            out('%-24s x %-24s %8.3f mm3' % (r.entityOne.name, r.entityTwo.name, r.interferenceBody.volume * 1000))
        out('pairs %d' % res.count)
    elif mode == 'flag':
        mm = app.measureManager
        # the flag bolt must clear the fork over the whole tilt range
        pt = des.userParameters.itemByName('pose_tilt')
        fl = (1e9, None)
        for t in range(-35, 101, 5):
            pt.expression = '%d deg' % t
            for n in ('REF Flag Bolt', 'REF Flag Nut'):
                d = mm.measureMinimumDistance(body('Fork'), body(n)).value * 10
                if d < fl[0]:
                    fl = (d, '%s @ tilt %d' % (n, t))
        out('flag vs fork min %.2f mm (%s)' % fl)
        # the flag must clear the bracket and switch body, and meet the roller near home
        es = (1e9, None)
        touch = None
        for t in range(80, 101, 2):
            pt.expression = '%d deg' % t
            for n in ('REF Flag Bolt', 'REF Flag Nut'):
                for f in ('Endstop Bracket', 'REF Switch'):
                    d = mm.measureMinimumDistance(body(f), body(n)).value * 10
                    if d < es[0]:
                        es = (d, '%s vs %s @ tilt %d' % (n, f, t))
            if touch is None and mm.measureMinimumDistance(body('REF Switch Roller'), body('REF Flag Bolt')).value < 1e-4:
                touch = t
        pt.expression = '0 deg'
        out('flag vs bracket/switch min %.2f mm (%s); flag meets the roller at tilt %s' % (es[0], es[1], touch))
    else:
        mm = app.measureManager
        cr = body('Cradle')
        heads = ['Yaw Head', 'Spring Plunger', 'Specimen Holder', 'REF Pad Screw', 'REF Screw X', 'REF Screw Y']
        py = des.userParameters.itemByName('pose_yaw')
        worst = (1e9, None, None)
        for y in range(0, 360, 15):
            py.expression = '%d deg' % y
            for n in heads:
                d = mm.measureMinimumDistance(cr, body(n)).value * 10
                if d < worst[0]:
                    worst = (d, n, y)
        py.expression = '0 deg'
        out('head vs cradle min %.2f mm (%s @ yaw %s)' % worst)
        h = body('REF Hall Sensor')
        best = (1e9, None)
        for y in range(0, 360, 5):
            py.expression = '%d deg' % y
            d = mm.measureMinimumDistance(h, body('REF Hub Magnet')).value * 10
            if d < best[0]:
                best = (d, y)
        py.expression = '0 deg'
        out('hall sensor to hub magnet: closest %.2f mm at yaw %s' % best)
