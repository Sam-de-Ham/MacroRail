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
    ("Fork", "1", "Base underside", "Bolts to the rail carriage; holds the tilt motor and the 608."),
    ("Cradle", "1", "Floor underside", "Swings on the tilt axis; carries the yaw motor and the head."),
    ("Yaw Head", "1", "Bell underside", "No supports. Snap off the thin fin under the spring housing."),
    ("Centring Plate", "1", "Underside", "Domes up."),
    ("Puck", "1 per specimen", "Underside (V-grooves)", "Nose up."),
    ("Pin Pad", "1", "Any flat face", ""),
    ("Spring Plunger", "1", "Spigot end", "Tiny: use a brim."),
    ("Tilt Axle", "1", "Flange", "Shank vertical, so it comes out round."),
    ("Axle Spacer", "1", "Flat", ""),
    ("Carriage Washer", "4", "Flat", ""),
    ("Height Gauge", "1", "Underside", "A tool, not mounted."),
]

HARDWARE = [
    ("28BYJ-48 + ULN2003 board", "2", "Tilt (outside the &minus;Y upright), yaw (under the cradle floor)"),
    ("608 bearing", "1", "+Y upright"),
    ("KY-024 hall board", "1", "Under the cradle floor"),
    ("Magnet &Oslash;5.7 &times; 1.8", "1 + 3 + 3 per puck", "Hub underside, plate top, puck underside"),
    ("Pen spring &Oslash;4.6 &times; 19", "1", "Spring housing, behind the plunger"),
    ("M3 &times; 17.5 + nut", "5", "Base to carriage (4, with printed washers), tilt home flag (1)"),
    ("M3 &times; 11.8 + nut", "9", "Tilt motor (2), yaw motor (2), KY-024 (1), centring screws (2), pad screw (1), set screw (1)"),
    ("M3 &times; 27.7 + nut", "1", "Tilt axle"),
    ("Printer endstop (microswitch)", "1", "Tilt home, on a bracket on the +Y upright (bracket follows)"),
    ("Pin size 00, 0 or 1", "", "Specimen pin"),
]

TESTS = [
    ("tp-bearing-seat", "The 608 presses in (hand or vice) and doesn't fall out; the lip stops it."),
    ("tp-motor-seat", "The tilt motor boss drops into the recess, both ear bolts line up, the counterbored heads sit flush."),
    ("tp-base-holes", "A 2.5 mm slice of the fork base: lay it on the carriage, all four bolts line up, it lies flat over the carriage's screw heads."),
    ("tp-tilt-d-bore", "Slides onto the motor shaft with no play and no force."),
    ("tp-axle-socket", "The axle's spigot fits; the nut presses into its pocket."),
    ("tp-cradle-floor", "Yaw motor boss and ear bolts, KY-024 bolt and board seat, sensor pocket and lead slot."),
    ("Yaw Head (whole part)", "Fits the yaw shaft; nuts, magnet and spring go in; the fin snaps off cleanly."),
    ("Centring Plate + Puck", "The puck clicks onto the domes in all three positions, doesn't rock, and the magnets hold."),
    ("Tilt Axle + Spacer", "The axle slips through the 608; the spacer slides over it."),
    ("Pin Pad + Plunger", "The pad slides into its pocket and clamps pins 00 to 1; the plunger slides freely in its bore."),
]


def page_cover():
    return f"""<section class="page">
<h1>MacroRail scan module</h1>
<div class="sub">Assembly and use &middot; v1 &middot; 2026-10-21</div>
{fig('assembled', 'The module on the rail carriage, with the objective for scale.')}
<div class="two">
<div class="box"><b>Tilt</b> &mdash; the cradle swings between the fork's uprights. A 28BYJ-48 drives it
directly on the &minus;Y side; the +Y side turns in a 608 bearing. Range &minus;33&deg; (belly towards
the lens) to +90&deg; (looking straight down on the back). Home: a microswitch.</div>
<div class="box"><b>Yaw</b> &mdash; the head sits straight on the shaft of a second 28BYJ-48 under the
cradle floor and turns all the way round. Home: a magnet in the head passes a hall sensor.</div>
<div class="box"><b>Centring</b> &mdash; the insect has to sit where the two axes cross. Two M3 screws
push the centring plate in X and Y, a spring pushes it back. &plusmn;2.5 mm each way. Done once per
specimen, with the app's wizard.</div>
<div class="box"><b>Puck</b> &mdash; each specimen lives on its own puck. Three V-grooves on three domes,
held by magnets, put it back in the same place to a few &micro;m.</div>
</div>
</section>"""


def page_parts():
    return f"""<section class="page">
<h2>1 &middot; Parts</h2>
<h3>Printed (PLA, 0.2 mm layers, no supports)</h3>
{table(('Part', 'Qty', 'Face on the bed', 'Notes'), PRINTED)}
<p>The STLs are in model coordinates: use <i>Place on face</i> in the slicer.
Files: <code>exports/final/</code>.</p>
<h3>Hardware</h3>
{table(('Item', 'Qty', 'Where'), HARDWARE)}
<p>All screws are M3 button heads, turned with a <b>2 mm hex key</b>. Socket-head caps also fit
(2.5 mm key). Lengths are under the head.</p>
</section>"""


def page_tests():
    return f"""<section class="page">
<h2>2 &middot; Test pieces first</h2>
<p>Print these before the big parts. Each is a thin slice of the real part, so a failed fit costs
minutes, not hours. Files: <code>exports/test-pieces/</code>.</p>
{fig('test_pieces', 'The six slices: motor seat and D-bore (left), bearing seat and axle socket (right), cradle floor and base holes.', 'half')}
{table(('Piece', 'It passes when'), TESTS)}
<div class="note">If a fit is off, change the matching parameter in Fusion and re-export:
<code>fit_press</code> (608 seat), <code>fit_D</code> (D-bores), <code>fit_slide</code>,
<code>boss_clr</code>, <code>m3_pocketAF</code> (nut pockets), <code>magPocketD</code>,
<code>pinHoleD</code>. Everything else follows.</div>
</section>"""


def page_assembly():
    head = steps([
        "<b>Nuts.</b> Press an M3 nut into each slot in the ring wall (X and Y screws) and one into "
        "the hub slot (set screw).",
        "<b>Hub magnet.</b> Glue one magnet into the pocket in the bell's underside. Any pole.",
        "<b>Spring.</b> Snap off the fin under the spring housing. Drop the spring in, then the plunger, "
        "cone first.",
        "<b>Centring screws.</b> Turn the X and Y screws in from outside until they just show inside.",
        "<b>Plate.</b> Glue three magnets into the plate, all with the <i>same</i> pole up. Lay the plate "
        "in the ring, domes up, between the two screw tips and the plunger.",
    ])
    cradle = steps([
        "<b>KY-024.</b> Bend the hall sensor (the small black TO-92) flat, sensing face up. Bolt the board "
        "under the floor with one M3 &times; 11.8; the sensor lies in the floor pocket, its legs in the slot.",
        "<b>Yaw motor.</b> Push its shaft up through the floor and bolt the two ears (M3 &times; 11.8, heads in "
        "the counterbores on top).",
        "<b>Head.</b> Slide the head onto the shaft, the D-flat to the set screw. Leave the 1 mm gap to the "
        "floor and tighten the set screw.",
    ])
    return f"""<section class="page">
<h2>3 &middot; Assembly</h2>
{fig('exploded', 'Everything in its place, pulled apart along the direction it goes on.')}
<div class="two"><div><h3>Yaw head</h3>{head}</div><div><h3>Cradle</h3>{cradle}</div></div>
</section>
<section class="page">
{fig('head_exploded', 'Yaw stack, top to bottom: puck with pin and pad screw, centring plate, head with screws, nuts and plunger, hub magnet, hall sensor, yaw motor, KY-024.', 'half')}
<h3>Fork and tilt</h3>
{steps([
    "<b>Bearing.</b> Press the 608 into the +Y upright from the inside until it hits the lip.",
    "<b>Tilt motor.</b> Fit it on the outside of the &minus;Y upright, boss in the recess. Bolt the ears with "
    "two M3 &times; 11.8 from the inside (heads in the counterbores), nuts on the ears.",
    "<b>Cradle.</b> Lower the cradle between the uprights and push the &minus;Y hub onto the tilt shaft.",
    "<b>Axle.</b> Spacer between the cradle and the bearing; push the axle through the 608 from outside into "
    "the +Y hub. M3 &times; 27.7 through the axle into the nut in the hub. Snug, not tight: the cradle must "
    "swing freely.",
    "<b>Flag.</b> M3 &times; 17.5 through the hole near the top of the +Y arm, head inside, nut outside. "
    "This is what presses the home switch.",
    "<b>Carriage.</b> Set the fork on the carriage over its screw heads. Four M3 &times; 17.5 down through "
    "base and carriage, a printed washer and a nut underneath.",
])}
<div class="note">Bolt stack under the carriage: base 6 + carriage 6 + washer 1.5 + nut 2.2 = 15.7 mm, so
the 17.5 mm bolt shows 1.8 mm past the nut. The nuts sit at X &plusmn;30, Y &plusmn;10, clear of the lead
nut, the bearing blocks and the screw.</div>
</section>"""


def page_homing():
    return f"""<section class="page">
<h2>4 &middot; Homing</h2>
{fig('endstop', 'Tilt at +95&deg;: the flag bolt on the +Y arm reaches the switch position on the upright (bracket holes below the bearing).', 'half')}
<h3>Tilt: a microswitch</h3>
<p>The switch is a normal printer endstop, on a small printed bracket bolted to the outside of the +Y
upright with two M3 screws (the two holes under the bearing; nuts in the pockets on the inside). The flag
is the M3 bolt through the +Y arm. Homing tilts the cradle slowly <i>away</i> from the lens, past +90&deg;;
at about +95&deg; the flag presses the lever and the motor stops. That position is the zero for every tilt
after it. Homing away from the lens means a missed switch can never drive the insect into the objective.</p>
<div class="note">The bracket isn't drawn yet: it needs the endstop board's size, hole spacing and lever
position. The holes and flag in the fork and cradle are already in place.</div>
<h3>Yaw: magnet and hall sensor</h3>
<p>The magnet in the head's hub passes 0.8 mm over the hall sensor once per turn. Homing turns the head
until the KY-024's digital output switches; that is yaw zero. Set its threshold with the board's
potentiometer so the LED lights only when the magnet is right above.</p>
<h3>The holes at the top of the arms</h3>
<p>The &Oslash;8.3 holes 38 mm above the axis are for an optional counterweight. The cradle hangs below
the axis, so tilting it to 90&deg; pulls with about 40 mN&middot;m. The 28BYJ-48's gearbox holds that,
but if it ever skips steps, push an 8 mm rod through both holes and add nuts until the cradle balances.</p>
</section>"""


def page_use():
    return f"""<section class="page">
<h2>5 &middot; Mounting a specimen</h2>
<div class="two">
<div>{fig('puck', 'Puck on the plate: pin through the nose, pad screw clamping it from the side.')}</div>
<div>{steps([
    "<b>Pad.</b> Slide the pin pad into the puck's side pocket, the pad nut into its slot, and turn the "
    "pad screw in until it just touches.",
    "<b>Pin.</b> Push the specimen's pin down through the hole in the nose tip.",
    "<b>Height.</b> Stand the height gauge on the nose tip, the pin in its slot. Slide the pin until the "
    "<i>middle of the insect</i> is level with the 19 mm step: that is the tilt axis height. The 17, 18, 20 "
    "and 21 steps show how far off you are.",
    "<b>Clamp.</b> Tighten the pad screw: the nut is captive inside the puck, the pad presses the pin "
    "against the wall.",
    "<b>Seat.</b> Set the puck on the plate. It clicks onto the three domes; the magnets hold it.",
])}</div></div>
<h2>6 &middot; Centring</h2>
<div class="two">
<div>{fig('hex_access', 'Yaw 180&deg;: the screws point away from the lens, where the hex key reaches them.')}</div>
<div><p>The app's wizard shoots the insect at four yaw angles, fits a circle to where it drifts, and
tells you how many turns to give each screw. It then turns the head so the screw faces you.</p>
<p>An M3 screw moves 0.5 mm per turn, so an eighth of a turn with the hex key is about 60 &micro;m.
That's finer than the wizard needs. Turn a screw in to push the plate away from it; the spring follows
when you back it out. &plusmn;2.5 mm of travel covers any pin that's reasonably straight.</p>
<p>Centre once per specimen. Taking the puck off and putting it back keeps the centring.</p></div>
</div>
{fig('tilted', 'Tilt +60&deg;, yaw 40&deg;: the head turns towards the lens. Limits: &minus;33&deg; to +90&deg;.', 'small')}
</section>"""


def build():
    body = page_cover() + page_parts() + page_tests() + page_assembly() + page_homing() + page_use()
    out = os.path.join(HERE, "scan-module-guide.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html><head><meta charset="utf-8"><title>MacroRail scan module'
                f'</title><style>{CSS}</style></head><body>{body}</body></html>')
    print(out)


if __name__ == "__main__":
    build()
