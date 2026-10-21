"""Verification: sweep pose_tilt x pose_yaw and report, per tilt, the smallest distance between
the lens keep-out zone and every moving body, and between the moving bodies and the fixed
fork/tilt motor (cradle swing). Globals TILTS and YAWS come from runpy init_globals."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa
import stage_08_present_pose as S8
importlib.reload(S8)

MM = app.measureManager


def mind(a, b):
    return MM.measureMinimumDistance(a, b).value * 10


def run(_):
    tilts = globals().get('TILTS', [0])
    yaws = globals().get('YAWS', [0, 45, 90, 135, 180, 225, 270, 315])
    ko = body('REF Lens Keep-out')
    fixed = [body('Fork')]
    moving = [body(n) for n in S8.YAW + S8.TILT_ONLY if n not in ('REF Insect',)]
    pt = des.userParameters.itemByName('pose_tilt')
    py = des.userParameters.itemByName('pose_yaw')
    for t in tilts:
        pt.expression = '%s deg' % t
        worst_lens = (1e9, None, None)
        worst_fix = (1e9, None, None)
        for y in yaws:
            py.expression = '%s deg' % y
            for b in moving:
                d = mind(ko, b)
                if d < worst_lens[0]:
                    worst_lens = (d, b.name, y)
                for f in fixed:
                    d2 = mind(f, b)
                    if d2 < worst_fix[0]:
                        worst_fix = (d2, b.name, y)
        print('tilt %4s: lens %.2f mm (%s @ yaw %s) | fork %.2f mm (%s @ yaw %s)' % (
            t, worst_lens[0], worst_lens[1], worst_lens[2], worst_fix[0], worst_fix[1], worst_fix[2]))
    pt.expression = '0 deg'
    py.expression = '0 deg'
