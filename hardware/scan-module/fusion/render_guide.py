"""Renders for the assembly guide (hardware/scan-module/guide/img). Global SHOT picks one shot,
so each call stays short."""
import sys, importlib, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanhelp
importlib.reload(scanhelp)
from scanhelp import *  # noqa

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'guide', 'img')
ALWAYS_HIDE = ('REF Lens Keep-out',)


def tp_and_tools():
    return tuple(b.name for b in root.bRepBodies if b.name.startswith('TP ')) + ('Height Gauge',)


def set_params(explode=0, tilt=0, yaw=0):
    des.userParameters.itemByName('explode').expression = str(explode)
    des.userParameters.itemByName('pose_tilt').expression = '%s deg' % tilt
    des.userParameters.itemByName('pose_yaw').expression = '%s deg' % yaw


def only(names):
    return tuple(b.name for b in root.bRepBodies if b.name not in names)


SHOTS = {
    'assembled': lambda: (set_params(), look((0, 0, -35), (1, -1.25, 0.8), 450, None, hide=ALWAYS_HIDE + tp_and_tools())),
    'exploded': lambda: (set_params(1), look((0, 0, -10), (1, -1.25, 0.55), 700, None, hide=ALWAYS_HIDE + tp_and_tools() + ('REF Objective',))),
    'head_exploded': lambda: (set_params(1), look((0, 0, -15), (1, -0.9, 0.55), 350, None, hide=ALWAYS_HIDE + tp_and_tools() + (
        'REF Objective', 'Fork', 'REF Carriage', 'REF Tilt Motor', 'Cradle', 'REF 608 Bearing', 'Tilt Axle', 'Axle Spacer',
        'REF Axle Bolt', 'REF Axle Nut', 'REF Flag Bolt', 'REF Flag Nut', 'Carriage Washer 1', 'Carriage Washer 2',
        'Carriage Washer 3', 'Carriage Washer 4', 'Endstop Bracket', 'REF Switch', 'REF Switch Roller',
        'REF Wood Screw 1', 'REF Wood Screw 2', 'REF Bracket Bolt 1', 'REF Bracket Bolt 2', 'REF Bracket Nut 1',
        'REF Bracket Nut 2') + tuple('REF Carriage Bolt %d' % i for i in range(1, 5)) +
        tuple('REF Carriage Bolt Head %d' % i for i in range(1, 5)))),
    'holder': lambda: (set_params(), look((0, 0, -32), (1.1, 0.9, 0.55), 160, None, hide=only((
        'Specimen Holder', 'REF Clamp Screw', 'REF Clamp Nut', 'REF Pin', 'REF Insect', 'Yaw Head',
        'REF Screw X', 'REF Screw Y', 'REF Spring')))),
    'tilted': lambda: (set_params(0, 60, 40), look((0, 0, -35), (1, -0.55, 0.45), 450, None, hide=ALWAYS_HIDE + tp_and_tools() + ('REF Objective',))),
    'endstop': lambda: (set_params(0, 97, 0), look((32, 44, -10), (1, -0.35, 0.3), 260, 80, hide=ALWAYS_HIDE + tp_and_tools() + ('REF Objective',))),
    'hex_access': lambda: (set_params(0, 0, 180), look((0, 0, -45), (-1, -0.35, 0.45), 300, None, hide=ALWAYS_HIDE + tp_and_tools() + ('REF Objective',))),
    'fork_sub': lambda: (set_params(), look((0, 0, -40), (0.9, -1.3, 0.7), 400, None, hide=only((
        'Fork', 'REF 608 Bearing', 'REF Tilt Motor', 'Endstop Bracket', 'REF Switch', 'REF Switch Roller',
        'REF Wood Screw 1', 'REF Wood Screw 2', 'REF Bracket Bolt 1', 'REF Bracket Bolt 2', 'REF Bracket Nut 1',
        'REF Bracket Nut 2')))),
    'fork_bearing': lambda: (set_params(), look((10, 40, -10), (0.7, 1.3, 0.5), 300, None, hide=only((
        'Fork', 'REF 608 Bearing', 'Endstop Bracket', 'REF Switch', 'REF Switch Roller', 'REF Wood Screw 1',
        'REF Wood Screw 2', 'REF Bracket Bolt 1', 'REF Bracket Bolt 2')))),
    'cradle_sub': lambda: (set_params(), look((0, 0, -50), (0.9, -0.8, -0.7), 300, None, hide=only((
        'Cradle', 'REF Yaw Motor', 'REF KY-024 PCB', 'REF KY-024 Components', 'REF Hall Sensor')))),
    'head_sub': lambda: (set_params(), look((0, 0, -35), (1.0, -0.8, 0.9), 200, None, hide=only((
        'Yaw Head', 'Specimen Holder', 'REF Screw X', 'REF Screw Y', 'REF Nut X', 'REF Nut Y', 'REF Spring',
        'REF Clamp Screw', 'REF Clamp Nut', 'REF Pin', 'REF Insect')))),
    'test_pieces': lambda: (set_params(), look((0, -250, -40), (1, 0.7, 1.1), 500, None, hide=only(tuple(b.name for b in root.bRepBodies if b.name.startswith('TP '))))),
}


def run(_):
    os.makedirs(OUT, exist_ok=True)
    shot = globals().get('SHOT')
    for sa in des.analyses.sectionAnalyses:
        sa.isLightBulbOn = False
    refs = [b for b in root.bRepBodies if b.name.startswith('REF') and b.name not in ALWAYS_HIDE]
    for b in refs:
        b.opacity = 1.0
    SHOTS[shot]()
    app.activeViewport.saveAsImageFile(os.path.join(OUT, '%s.png' % shot), 1600, 1150)
    for b in refs:
        b.opacity = 0.45 if not any(k in b.name for k in ('Screw', 'Nut', 'Bolt', 'Magnet', 'Spring', 'Pin', 'Bearing')) else 1.0
    set_params()
    for b in root.bRepBodies:
        b.isLightBulbOn = b.name not in ALWAYS_HIDE
    print('saved', shot)
