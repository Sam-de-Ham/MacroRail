"""The shots: which parts show, where each part moves (mm, rail coordinates), the view
direction (from the subject towards the camera) and the image size. Rail coordinates: X along
the rail from the motor end, Y across it, Z up. Module parts are 'm.<pose>.<Fusion body>'."""

BIG = (2000, 1250)
GUIDE = (1600, 1100)

RAIL = [
    "motor_end",
    "far_end",
    "carriage",
    "nut_carrier",
    "platform",
    "trigger",
    "rods",
    "lead_screw",
    "motor",
    "motor_bolts",
    "coupler",
    "bearings",
    "bearing_bolts",
    "t8_nut",
    "platform_bolts",
    "switch",
    "trigger_screw",
]
RAIL_BARE = [k for k in RAIL if k not in ("platform", "platform_bolts")]  # as the module needs it
CARRIAGE = [
    "carriage",
    "bearings",
    "bearing_bolts",
    "nut_carrier",
    "t8_nut",
    "trigger",
    "trigger_screw",
]


def m(pose, *names):
    return [f"m.{pose}.{n}" for n in names]


FORK = ("Fork", "REF 608 Bearing")
TILT_MOTOR = ("REF Tilt Motor",)
ENDSTOP = (
    "Endstop Bracket",
    "REF Switch",
    "REF Switch Roller",
    "REF Wood Screw 1",
    "REF Wood Screw 2",
    "REF Bracket Bolt 1",
    "REF Bracket Bolt 2",
    "REF Bracket Nut 1",
    "REF Bracket Nut 2",
)
CRADLE = ("Cradle", "REF Yaw Motor", "REF KY-024 PCB", "REF KY-024 Components", "REF Hall Sensor")
AXLE = (
    "Tilt Axle",
    "Axle Spacer",
    "REF Axle Bolt",
    "REF Axle Nut",
    "REF Flag Bolt",
    "REF Flag Nut",
)
HEAD = (
    "Yaw Head",
    "Specimen Holder",
    "REF Screw X",
    "REF Screw Y",
    "REF Nut X",
    "REF Nut Y",
    "REF Spring",
    "REF Clamp Screw",
    "REF Clamp Nut",
    "REF Pin",
    "REF Insect",
    "REF Hub Magnet",
)
MOUNT = (
    tuple(f"Carriage Washer {i}" for i in range(1, 5))
    + tuple(f"REF Carriage Bolt {i}" for i in range(1, 5))
    + tuple(f"REF Carriage Bolt Head {i}" for i in range(1, 5))
)


def md(x, y, z):
    """A view direction given in the module's own frame (x towards the camera), in rail axes."""
    return (-x, -y, z)


HERO = (-0.75, -1.35, 0.78)  # front left, the motor end and the endstop side
BACK = (1.0, 1.25, 0.7)
MODULE_VIEW = md(1, -1.25, 0.75)  # as the module guide: from the lens side, the bearing side

FOCUS_MODULE = ((110, -99, 15), (230, 99, 999))  # the module and the rail around it

RAIL_EXPLODE = {
    "motor": (-80, 0, 0),
    "motor_bolts": (35, 0, 0),
    "coupler": (-40, 0, 0),
    "far_end": (70, 0, 0),
    "rods": (35, 0, 0),
    "lead_screw": (35, 0, 70),
    "t8_nut": (0, 0, 70),
    "nut_carrier": (0, 0, 100),
    "bearings": (0, 0, 125),
    "carriage": (0, 0, 160),
    "bearing_bolts": (0, 0, 185),
    "trigger": (0, -30, 160),
    "trigger_screw": (-25, -30, 160),
    "platform": (0, 0, 200),
    "platform_bolts": (0, 0, 225),
    "switch": (0, 25, 0),
}

SHOTS = [
    # README and overview images
    {"path": "docs/images/rail.png", "show": RAIL, "view": HERO, "size": BIG},
    {
        "path": "docs/images/rail-exploded.png",
        "show": RAIL,
        "view": (-0.75, -1.35, 0.95),
        "size": BIG,
        "offsets": RAIL_EXPLODE,
    },
    {
        "path": "docs/images/module.png",
        "show": RAIL_BARE + m("rest", "*"),
        "view": MODULE_VIEW,
        "size": BIG,
        "focus": FOCUS_MODULE,
    },
    {
        "path": "docs/images/module-exploded.png",
        "show": ["carriage", *m("exploded", "*")],
        "view": md(1, -1.25, 0.55),
        "size": (1600, 2000),
        "offsets": {"carriage": (0, 0, -115)},
    },
    {
        "path": "docs/images/rail-with-module.png",
        "show": RAIL_BARE + m("rest", "*"),
        "view": (-0.85, 1.35, 0.7),
        "size": BIG,
    },
    {
        "path": "social/rail.png",
        "show": RAIL,
        "view": HERO,
        "size": (2560, 1280),
        "window": (0.08, 0.05, 0.92, 0.60),
    },
    # rail assembly guide
    {
        "path": "docs/guides/img/rail/01-motor-end-block.png",
        "show": ["motor_end"],
        "view": HERO,
        "size": GUIDE,
    },
    {
        "path": "docs/guides/img/rail/02-far-end-block.png",
        "show": ["far_end"],
        "view": (0.9, -1.3, 0.8),
        "size": GUIDE,
    },
    {
        "path": "docs/guides/img/rail/03-carriage.png",
        "show": ["carriage"],
        "view": HERO,
        "size": GUIDE,
    },
    {
        "path": "docs/guides/img/rail/04-floating-nut-carrier.png",
        "show": ["nut_carrier"],
        "view": (0.9, -1.2, 0.7),
        "size": GUIDE,
    },
    {
        "path": "docs/guides/img/rail/05-sample-platform.png",
        "show": ["platform"],
        "view": HERO,
        "size": GUIDE,
    },
    {
        "path": "docs/guides/img/rail/06-endstop-trigger.png",
        "show": ["trigger"],
        "view": (-0.9, -1.2, 0.7),
        "size": GUIDE,
    },
    {
        "path": "docs/guides/img/rail/07-carriage-bearings.png",
        "show": ["carriage", "bearings", "bearing_bolts"],
        "view": (-0.8, 1.3, 0.75),
        "size": GUIDE,
        "flip": True,
    },
    {
        "path": "docs/guides/img/rail/08-rods-end-blocks.png",
        "show": ["motor_end", "far_end", "rods", "carriage", "bearings", "bearing_bolts"],
        "view": HERO,
        "size": BIG,
    },
    {
        "path": "docs/guides/img/rail/09-motor-coupler.png",
        "show": ["motor_end", "rods", "motor", "motor_bolts", "coupler"],
        "view": (1.0, -0.9, 0.75),
        "size": GUIDE,
        "focus": ((-60, -99, -99), (70, 99, 999)),
    },
    {
        "path": "docs/guides/img/rail/10-lead-screw-nut-carrier.png",
        "show": [
            "motor_end",
            "far_end",
            "rods",
            "motor",
            "motor_bolts",
            "coupler",
            "lead_screw",
            "t8_nut",
            "nut_carrier",
        ],
        "view": (0.35, -1.3, 0.75),
        "size": BIG,
    },
    {
        "path": "docs/guides/img/rail/11-carriage-on-nut.png",
        "show": RAIL_BARE,
        "view": (0.5, -1.3, 0.35),
        "size": BIG,
        "focus": ((60, -99, -99), (300, 99, 999)),
    },
    {
        "path": "docs/guides/img/rail/12-sample-platform.png",
        "show": RAIL,
        "view": (-0.6, -1.0, 1.1),
        "size": GUIDE,
        "focus": ((100, -99, -99), (240, 99, 999)),
    },
    {
        "path": "docs/guides/img/rail/13-endstop.png",
        "show": RAIL,
        "view": (0.15, 0.55, 1.0),
        "size": GUIDE,
        "focus": ((15, -85, 0), (130, -30, 60)),
    },
    {"path": "docs/guides/img/rail/14-finished-front.png", "show": RAIL, "view": HERO, "size": BIG},
    {"path": "docs/guides/img/rail/15-finished-back.png", "show": RAIL, "view": BACK, "size": BIG},
    # scan module guide
    {
        "path": "docs/guides/img/module/01-fork-bearing.png",
        "show": m("rest", *FORK),
        "view": md(0.7, 1.3, 0.5),
        "size": GUIDE,
    },
    {
        "path": "docs/guides/img/module/02-fork-tilt-motor-endstop.png",
        "show": m("rest", *FORK + TILT_MOTOR + ENDSTOP),
        "view": md(0.9, -1.3, 0.7),
        "size": GUIDE,
    },
    {
        "path": "docs/guides/img/module/03-cradle-yaw-motor.png",
        "show": m("rest", *CRADLE),
        "view": md(0.9, 0.8, 0.7),
        "flip": True,
        "size": GUIDE,
    },
    {
        "path": "docs/guides/img/module/04-head-holder.png",
        "show": m("rest", *HEAD),
        "view": md(1.0, -0.8, 0.9),
        "size": GUIDE,
    },
    {
        "path": "docs/guides/img/module/05-head-exploded.png",
        "show": m("exploded", *HEAD),
        "view": md(1, -0.9, 0.55),
        "size": (1300, 1600),
    },
    {
        "path": "docs/guides/img/module/06-cradle-in-fork.png",
        "show": m("rest", *FORK + TILT_MOTOR + CRADLE + AXLE),
        "view": md(1, -1.25, 0.8),
        "size": GUIDE,
    },
    {
        "path": "docs/guides/img/module/07-tilt-endstop.png",
        "show": [*m("home", "*"), "!*Carriage*"],
        "view": md(1, -0.35, 0.3),
        "size": GUIDE,
        "focus": ((105, -66, 80), (175, -20, 190)),
    },
    {
        "path": "docs/guides/img/module/08-on-carriage.png",
        "show": RAIL_BARE + m("rest", "*"),
        "view": MODULE_VIEW,
        "size": GUIDE,
        "focus": FOCUS_MODULE,
    },
    {
        "path": "docs/guides/img/module/09-tilted.png",
        "show": RAIL_BARE + m("tilted", "*"),
        "view": md(1, -0.6, 0.5),
        "size": GUIDE,
        "focus": FOCUS_MODULE,
    },
]
