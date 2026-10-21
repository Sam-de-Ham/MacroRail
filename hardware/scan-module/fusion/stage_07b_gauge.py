"""Stage 07b: pin height gauge (a tool, parked beside the module): five steps 17-21 mm above
the nose tip, with a slot for the pin."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa


def run(_):
    # pin height gauge: five steps 17..21 mm above the nose tip, slot for the pin
    # one simple sketch per step (a stair of overlapping blocks), joined
    g = None
    for i in range(5):
        s = sk('z', '-(d_noseTip)', 'PL Nose Tip', 'GG 01 Gauge Step %d' % (i + 1))
        s.rect('-(gauge_park - %d * gauge_step)' % i, '-(gauge_park - 5 * gauge_step)', '-(gauge_W / 2)', 'gauge_W / 2')
        f = ext(s, NEW if i == 0 else JOIN, 'GG Step %d' % (i + 1), 'gauge_h0 + %d' % i, POS, bodies=None if i == 0 else [g])
        if i == 0:
            g = name_new(f, 'Height Gauge')
    s = sk('z', '-(d_noseTip)', 'PL Nose Tip', 'GG 02 Gauge Slot')
    s.rect('-(gauge_park - 3)', '-(gauge_park - 5 * gauge_step - 1)', '-(gauge_slot / 2)', 'gauge_slot / 2')
    ext(s, CUT, 'GG Slot', 'gauge_h0 + 5', POS, bodies=[g])
    print(report())
