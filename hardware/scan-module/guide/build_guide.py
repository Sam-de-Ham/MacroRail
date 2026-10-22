"""Generates the scan-module assembly and usage guide as HTML (scan-module-guide.html); see
README.md to make the PDF. The pictures in img/ come from ../fusion/render_guide.py."""

import html
import os

HERE = os.path.dirname(os.path.abspath(__file__))

CSS = """
@page { size: A4; margin: 14mm 14mm 16mm 14mm; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.45 "Segoe UI", system-ui, sans-serif; color: #1d2127; margin: 0; }
h1 { font-size: 24pt; margin: 0 0 2mm; color: #0f8a8a; }
h2 { font-size: 15pt; margin: 0 0 3mm; color: #0f8a8a; border-bottom: 2px solid #0f8a8a; padding-bottom: 1mm; }
h3 { font-size: 11.5pt; margin: 4mm 0 1.5mm; }
p { margin: 0 0 2mm; }
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }
.sub { color: #6b7280; font-size: 11pt; margin-bottom: 5mm; }
img { width: 100%; border-radius: 3mm; display: block; }
.fig { margin: 2mm 0 3mm; break-inside: avoid; }
.fig.half { width: 72%; margin-left: auto; margin-right: auto; }
.fig.small { width: 44%; margin-left: auto; margin-right: auto; }
.cap { color: #6b7280; font-size: 9pt; margin-top: 1mm; text-align: center; }
table { border-collapse: collapse; width: 100%; margin: 1mm 0 3mm; font-size: 9.5pt; }
th, td { border: 1px solid #d0d5dc; padding: 1.2mm 2mm; text-align: left; vertical-align: top; }
th { background: #eef6f6; }
ol.steps { padding-left: 6mm; margin: 0 0 2mm; }
ol.steps li { margin-bottom: 1.8mm; }
.note { background: #fff4e6; border-left: 3px solid #e8590c; padding: 2mm 3mm; margin: 2mm 0 3mm; font-size: 9.5pt; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }
.box { background: #f4f6f8; border-radius: 2mm; padding: 2.5mm 3.5mm; }
.box b { color: #0f8a8a; }
.crop img { height: 50mm; object-fit: cover; }
"""


def esc(s):
    return html.escape(s, quote=False)


def fig(name, caption, size=""):
    cls = f"fig {size}".strip()
    return f'<div class="{cls}"><img src="img/{name}.png"><div class="cap">{caption}</div></div>'


def table(head, rows):
    h = "".join(f"<th>{esc(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{h}</tr>{b}</table>"


def steps(items):
    return '<ol class="steps">' + "".join(f"<li>{i}</li>" for i in items) + "</ol>"


PRINTED = [
    ("Fork", "1", "Base underside", "Bolts to the rail carriage; holds the tilt motor, the 608 and the endstop bracket. The longest print (about 12 cm tall)."),
    ("Cradle", "1", "Floor underside", "Swings on the tilt axis; carries the yaw motor and the head. Its hub bores print lying on their side; the tilt D-bore fit is tuned for that."),
    ("Yaw Head", "1", "Bell underside", "Prints without supports. A thin fin holds up the spring housing; snap it off afterwards."),
    ("Specimen Holder", "1", "Plate underside", "Centring plate, clamp column and nose in one part."),
    ("Tilt Axle", "1", "Flange", "Shank pointing up, so it comes out round."),
    ("Axle Spacer", "1", "Flat", ""),
    ("Endstop Bracket", "1", "Back (the flat side)", "Pad side up."),
    ("Carriage Washer", "4", "Flat", "The carriage holes are &Oslash;4.5, so M3 nuts need a washer."),
    ("Height Gauge", "1", "Underside", "A tool for setting the pin height, not mounted."),
]

HARDWARE = [
    ("28BYJ-48 + ULN2003 board", "2", "Tilt motor (outside the &minus;Y upright), yaw motor (under the cradle floor)"),
    ("608 bearing", "1", "+Y upright"),
    ("KY-024 hall board", "1", "Under the cradle floor"),
    ("Magnet &Oslash;5.7 &times; 1.8", "1", "Under the yaw head (yaw home)"),
    ("Pen spring &Oslash;4.6 &times; 19", "1", "Spring housing on the yaw head"),
    ("Roller microswitch 20 &times; 10", "1", "Endstop bracket, with 2 small &Oslash;1.9 wood screws"),
    ("M3 &times; 11.8", "11", "Tilt motor 2, yaw motor 2, KY-024 1, centring screws 2, pin clamp 1, yaw set screw 1, endstop bracket 2"),
    ("M3 &times; 17.5", "5", "Fork to carriage 4, tilt home flag 1"),
    ("M3 &times; 27.7", "1", "Tilt axle"),
    ("M3 nut", "17", "One for every bolt"),
    ("Pin size 00, 0 or 1", "", "Specimen pin"),
]

TOOLS = ("2 mm hex key (the M3 button heads), small Phillips screwdriver (the switch's wood screws), "
         "flat pliers (pushing nuts into slots), superglue, a vice or clamp (the bearing), and a "
         "5 mm drill bit to clean a D-bore by hand if it is too tight.")

TESTS = [
    ("tp-motor-seat", "<b>Reprint.</b> The tilt motor upright is now 4 mm (was 6), so the shaft reaches further. Motor boss drops into the recess, both bolts line up, heads sink into the counterbores."),
    ("tp-tilt-d-bore", "<b>Reprint.</b> Tighter (0.05 mm clearance, was 0.2). Push it onto the shaft of the motor on <i>tp-motor-seat</i>: it should go on firmly by hand, cover the shaft's flats and have no play. If it won't go on, run a 5 mm drill through by hand."),
    ("yaw-head", "<b>Reprint.</b> Bigger magnet pocket (+0.2 mm); the spring now sits straight in its bore, no plunger. Magnet presses in; the spring drops in from inside the ring."),
    ("specimen-holder", "<b>Reprint.</b> New pin clamp and a &Oslash;1.2 pin hole. A nut slides into the side slot and can't turn; the clamp screw runs through it and pinches a pin in the hole."),
    ("tp-bearing-seat", "Optional. 0.1 mm more room for the 608 (it was a little tight)."),
    ("tp-axle-socket, tp-cradle-floor, tp-base-holes, tilt-axle, axle-spacer, endstop-bracket", "Unchanged. Already passed."),
]

FITS = [
    ("608 too tight or loose", "<code>fit_press</code> (now 0.35)"),
    ("Tilt D-bore (cradle)", "<code>fit_Dt</code> (now 0.05)"),
    ("Yaw D-bore (head)", "<code>fit_D</code> (0.2, passed)"),
    ("Nut pockets", "<code>m3_pocketAF</code> (5.7, passed)"),
    ("Pin clamp nut turns", "<code>clampNut_H</code> (now 5.5)"),
    ("Magnet pocket", "<code>magPocketD</code> (now magnet + 0.4)"),
    ("Pin hole", "<code>pinHoleD</code> (now 1.2)"),
    ("Switch screws", "<code>ws_pilotD</code> (1.5)"),
]


def page_cover():
    return f"""<section class="page">
<h1>MacroRail scan module</h1>
<div class="sub">Assembly and use &middot; v1 &middot; 2026-10-22</div>
{fig('assembled', 'The module on the rail carriage. The grey cylinder on the right is the objective, for scale.', 'half')}
<div class="two">
<div class="box"><b>Tilt</b> &mdash; the cradle swings between the fork's two uprights. A 28BYJ-48 drives it
directly on the &minus;Y side; the +Y side turns in a 608 bearing. Range &minus;33&deg; (belly towards
the lens) to +90&deg; (looking straight down on the back). Home: a roller microswitch at +97&deg;.</div>
<div class="box"><b>Yaw</b> &mdash; the head sits straight on the shaft of a second 28BYJ-48 under the
cradle floor and turns all the way round. Home: a magnet in the head passes a hall sensor.</div>
<div class="box"><b>Centring</b> &mdash; the insect has to sit where the two axes cross, or it swings
out of the picture as it turns. Two M3 screws push the specimen holder in X and Y, a spring pushes it
back. &plusmn;2.5 mm each way, set once per specimen with the app's wizard.</div>
<div class="box"><b>Specimen holder</b> &mdash; one printed part: the centring plate with a clamp
column and nose on top. A single M3 screw pinches the pin. To change specimens you swap the pin.</div>
</div>
<p style="margin-top:4mm"><b>Directions used in this guide:</b> <b>+X</b> points at the camera (the
lens side), <b>+Y</b> is the bearing side, <b>&minus;Y</b> the tilt motor side, and <b>up</b> is up
with the cradle level.</p>
<p><b>Tools:</b> {TOOLS}</p>
</section>"""


def page_parts():
    return f"""<section class="page">
<h2>1 &middot; Parts and tools</h2>
<h3>Printed (PLA, 0.2 mm layers, no supports)</h3>
{table(('Part', 'Qty', 'Face on the bed', 'Notes'), PRINTED)}
<p>Files: <code>exports/final/</code>. They are in model coordinates, so use <i>Place on face</i> in the
slicer.</p>
<h3>Hardware</h3>
{table(('Item', 'Qty', 'Where'), HARDWARE)}
<p>Lengths are under the head. All M3 screws are button heads (2 mm hex); socket heads fit too.</p>
</section>"""


def page_tests():
    return f"""<section class="page">
<h2>2 &middot; Test pieces (round 2)</h2>
<p>The first round showed which fits were off, and these were changed. Reprint the ones marked
<b>Reprint</b> before the big parts. Files: <code>exports/test-pieces/</code>.</p>
{table(('Piece', 'What changed, and when it passes'), TESTS)}
<h3>If a fit is still off</h3>
<p>Every fit is one parameter in the Fusion model. Say what is wrong (too tight or too loose, roughly by
how much): the parameter changes, everything rebuilds, and only the affected parts need reprinting.</p>
{table(('Fit', 'Parameter'), FITS)}
</section>"""


def page_fork():
    return f"""<section class="page">
<h2>3 &middot; Assembly</h2>
<p>Build three groups on the bench &mdash; the <b>fork</b>, the <b>cradle</b> and the <b>yaw head</b>
&mdash; then put them together. Every nut goes into its printed pocket or slot first, so a single hex
key turns every screw. If a nut won't stay in, a dab of glue on its outside is fine.</p>
<h3>A &middot; Fork</h3>
<div class="two"><div>{fig('fork_sub', 'Fork from the motor side: tilt motor on the &minus;Y upright, bearing and switch bracket on the +Y upright.')}</div>
<div>{fig('fork_bearing', 'From the +Y side: the 608 sits in its housing from the outside; the bracket hangs past the upright edge.')}</div></div>
{steps([
    "<b>Bearing.</b> Press the 608 into the round housing on the +Y upright <i>from the outside</i>, flat and "
    "square, with a vice or a clamp and a flat block. It stops against a thin lip on the inside. Check that "
    "the inner race still spins freely. <i>Why from the outside: the lip takes the load, and the axle later "
    "clamps only the inner race, so the outer race never gets squeezed.</i>",
    "<b>Switch on the bracket.</b> Hold the microswitch on the bracket's flat face, next to the raised pad, "
    "at the end away from the two big holes: pins down, roller up, the lever's pivot end towards the far "
    "end of the bracket. Drive the two wood screws through the switch's holes into the small pilot holes. "
    "Click the lever: it must move freely. Don't glue yet.",
    "<b>Bracket on the fork.</b> Push two M3 nuts into the hex pockets on the <i>inside</i> of the +Y upright "
    "(below the bearing). Hold the bracket against the outside, pad against the upright and the switch "
    "towards the camera side, and bolt it with two M3 &times; 11.8.",
    "<b>Tilt motor: not yet.</b> It goes on after the cradle is in (step D2), because its shaft has to "
    "slide into the cradle's hub from outside.",
])}
</section>"""


def page_head():
    return f"""<section class="page">
<h3>B &middot; Cradle</h3>
<div class="two crop"><div>{fig('cradle_sub', 'Cradle from below: the yaw motor and the KY-024 hang under the floor.')}</div>
<div>{steps([
    "<b>Hall sensor.</b> On the KY-024, bend the small black sensor (the TO-92 on long legs) flat, the face "
    "with the writing up. From below, feed its legs through the slot in the floor so the sensor lies in "
    "the shallow pocket on top, flush with the surface. <i>The head's magnet passes 0.8 mm above it, so "
    "nothing may stick up.</i>",
    "<b>KY-024 board.</b> Bolt the board under the floor with one M3 &times; 11.8: head on top in its "
    "counterbore, nut under the board.",
    "<b>Yaw motor.</b> From below, push the shaft up through the big hole, boss into its recess. Bolt the "
    "two ears with M3 &times; 11.8, heads from the top in their counterbores, nuts under the ears. The "
    "heads must end flush or below the floor: the head spins 1 mm above it.",
])}</div></div>
<h3>C &middot; Yaw head and specimen holder</h3>
<div class="two crop"><div>{fig('head_sub', 'The finished head: centring screws on the +X and +Y sides, spring housing opposite them, clamp screw in the holder.')}</div>
<div>{fig('holder', 'The holder: the clamp screw goes in from one face, through the nut in the side slot, to the pin.')}</div></div>
{steps([
    "<b>Fin.</b> Snap off the thin fin under the spring housing (wiggle it; it breaks at its root).",
    "<b>Nuts.</b> Push M3 nuts into the two slots in the top of the ring wall (for the X and Y screws) and "
    "one into the slot in the hub (for the set screw).",
    "<b>Magnet.</b> Press the magnet into the small off-centre pocket under the head; a drop of glue keeps "
    "it. Either pole works.",
    "<b>Centring screws.</b> Turn an M3 &times; 11.8 into each ring nut from outside until the tip just "
    "shows inside the ring.",
    "<b>Onto the motor.</b> Push the head onto the yaw shaft, flats lined up with the bore. Turn the set "
    "screw (M3 &times; 11.8) into the hub nut until it bites on the shaft's flat. Spin it by hand: it must "
    "clear the floor and run true.",
    "<b>Holder.</b> Push an M3 nut into the side slot of the holder's column. It only fits flats up and "
    "down, which is what stops it turning. Turn the clamp screw in from the opposite face until it just "
    "reaches the pin hole.",
    "<b>Spring.</b> Drop the pen spring into its bore from inside the ring. Press the holder's rim against "
    "the spring, lower it into the ring and let go. <i>The screw tips and the spring sit in the rim's "
    "V-groove, so the holder slides but can't lift.</i>",
])}
</section>"""


def page_join():
    return f"""<section class="page">
<h3>D &middot; Put it together</h3>
<div class="two"><div>{fig('exploded', 'Everything pulled apart along the direction it goes on.')}</div>
<div>{fig('head_exploded', 'The yaw stack, top to bottom: pin, holder with clamp nut and screw, head with centring screws, nuts and spring, hub magnet, hall sensor, yaw motor, KY-024.')}</div></div>
{steps([
    "<b>Cradle in.</b> Lower the cradle (with its head) between the uprights. It fits with 1 mm each side.",
    "<b>Tilt motor.</b> From outside the &minus;Y upright, push the motor's shaft through the hole into the "
    "cradle's hub. Turn the cradle until the flats line up, then push until the motor's boss drops into its "
    "recess and the motor sits flat. Bolt the two ears: M3 &times; 11.8 from the <i>inside</i> (heads in the "
    "counterbores; reach them past the cradle arm), nuts on the ears. <i>The shaft carries the cradle on "
    "this side, so it has to be fully seated: about 6 mm of its flats are inside the hub.</i>",
    "<b>Axle.</b> Push an M3 nut into the hex pocket on the inside of the cradle's +Y hub. Hold the spacer "
    "against the outside of the +Y arm, centred, and push the axle in from outside: through the bearing, "
    "the spacer and into the arm's socket. Bolt it with the M3 &times; 27.7 from the flange side into the "
    "nut, until nothing wobbles. <i>This clamps the axle, spacer and bearing inner race to the cradle; "
    "the bearing does the turning.</i>",
    "<b>Flag.</b> M3 &times; 17.5 through the small hole near the top of the +Y arm, head inside, nut "
    "outside. This bolt's end presses the home switch.",
])}
<h3>E &middot; On the rail</h3>
<p>Tilt the cradle to about 90&deg; to reach the base. Four M3 &times; 17.5 go down through the base and
the carriage, with a printed washer and a nut underneath. <i>Stack: base 6 + carriage 6 + washer 1.5 +
nut 2.2 = 15.7 mm, so the bolt shows 1.8 mm past the nut, clear of the lead nut and the bearing
blocks.</i></p>
<h3>F &middot; Checks before any power</h3>
{steps([
    "Swing the cradle slowly by hand from &minus;30&deg; to past +90&deg; (the gearbox turns stiffly; that "
    "is normal). Nothing rubs, and the arms stay 1 mm from the uprights.",
    "Past +90&deg; the flag meets the roller, and the switch clicks at about +97&deg;. Once that is right, "
    "put a drop of superglue between the switch and the bracket.",
    "Turn the head a full turn by hand (slowly, through the gearbox). The holder stays in its ring.",
    "Leave slack in the motor and sensor cables for the whole tilt range, and route them along the "
    "&minus;Y arm. Wiring and the app's 3D mode come next.",
])}
</section>"""


def page_homing():
    return f"""<section class="page">
<h2>4 &middot; How it homes</h2>
{fig('endstop', 'Tilt at +97&deg;: the flag bolt on the +Y arm presses the switch roller.', 'half')}
<h3>Tilt: roller microswitch</h3>
<p>The motors are steppers: they know how far they have turned, not where they are. So at start-up each
axis finds a fixed point. Tilt turns slowly <i>away</i> from the lens, past +90&deg;. The flag bolt meets
the roller at about +90&deg; and the switch clicks at +97&deg;: that is tilt zero for everything after it.
Homing away from the lens means a missed switch can never drive the insect into the objective. The
click angle is the <code>home_t</code> parameter; the bracket follows it.</p>
<h3>Yaw: magnet and hall sensor</h3>
<p>The magnet under the head passes 0.8 mm over the hall sensor once per turn. Homing turns the head
until the KY-024 switches; that is yaw zero. Set the board's potentiometer so its LED lights only when
the magnet is right above the sensor.</p>
<h3>The holes at the top of the arms</h3>
<p>The &Oslash;8.3 holes 38 mm above the axis are for an optional counterweight. The cradle hangs below
the axis, so at 90&deg; it pulls with about 40 mN&middot;m. The motor's gearbox should hold that; if it
ever loses steps, push an 8 mm rod through both holes and add nuts until the cradle balances.</p>
</section>"""


def page_use():
    return f"""<section class="page">
<h2>5 &middot; Mounting a specimen</h2>
<div class="two">
<div>{fig('holder', 'The holder in the head: pin through the nose, the clamp screw pinching it from the side.')}</div>
<div>{steps([
    "<b>Loosen</b> the clamp screw half a turn (2 mm key; turn the head if it faces away). The holder "
    "stays in the head; you only swap pins.",
    "<b>Pin.</b> Push the specimen's pin down through the hole in the nose tip.",
    "<b>Height.</b> Stand the height gauge on the nose tip, the pin in its slot. Slide the pin until the "
    "<i>middle of the insect</i> is level with the 19 mm step: that is the tilt axis height. The 17, 18, 20 "
    "and 21 steps show how far off you are.",
    "<b>Clamp.</b> Tighten the clamp screw gently. Its tip pushes the pin against the far side of the "
    "hole; the nut is trapped, so one key is enough. It only has to stop the pin moving.",
])}</div></div>
<h2>6 &middot; Centring</h2>
<div class="two">
<div>{fig('hex_access', 'Yaw 180&deg;: the screws point away from the lens, where the hex key reaches them.')}</div>
<div><p>The app's wizard photographs the insect at four yaw angles, fits a circle to how it drifts, and
says how far to turn each screw. It turns the head so that screw faces you.</p>
<p>An M3 screw moves 0.5 mm per turn: an eighth of a turn is about 60 &micro;m. Turning a screw in
pushes the holder away from it; backing it out lets the spring push the holder back. &plusmn;2.5 mm
covers any reasonably straight pin. Centre once per specimen.</p></div>
</div>
{fig('tilted', 'Tilt +60&deg;, yaw 40&deg;. Working limits: &minus;33&deg; to +90&deg;.', 'small')}
</section>"""


def build():
    body = (page_cover() + page_parts() + page_tests() + page_fork() + page_head() + page_join()
            + page_homing() + page_use())
    out = os.path.join(HERE, "scan-module-guide.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html><head><meta charset="utf-8"><title>MacroRail scan module'
                f'</title><style>{CSS}</style></head><body>{body}</body></html>')
    print(out)


if __name__ == "__main__":
    build()
