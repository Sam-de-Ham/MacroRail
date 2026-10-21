"""Verification: saved section analyses (hidden), and one shown at a time for screenshots.
Global SHOW = name of the section to show (or None)."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

SECTIONS = [
    ('SEC Stack XZ (y=0)', lambda: root.xZConstructionPlane, 0.0),
    ('SEC Tilt Axis YZ (x=0)', lambda: root.yZConstructionPlane, 0.0),
    ('SEC Carriage Bolts YZ (x=30)', lambda: root.yZConstructionPlane, 3.0),
    ('SEC Yaw Motor Bolts XZ (y=17.5)', lambda: root.xZConstructionPlane, 1.75),
]


def run(_):
    sa = des.analyses.sectionAnalyses
    have = {a.name: a for a in sa}
    for name, plane, off in SECTIONS:
        if name not in have:
            a = sa.add(sa.createInput(plane(), off))
            a.name = name
            have[name] = a
    show = globals().get('SHOW')
    for n, a in have.items():
        a.isLightBulbOn = (n == show)
    print('sections', list(have))
