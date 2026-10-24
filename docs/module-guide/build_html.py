"""Generates the MacroRail scan-module wiring guide as HTML (module-guide.html); see README.md to make the PDF."""

import html
import os

HERE = os.path.dirname(os.path.abspath(__file__))

TEAL = "#0f8a8a"
INK = "#1d2127"
MUTED = "#6b7280"
ORANGE_CAP = "#e8590c"

# One colour per signal, used by the Nano rings, legend, wiring picture and checklist.
# IN1..IN4 have the same colour on both driver boards, so "IN1 is always orange".
COL = {
    "in1": "#f08c00",
    "in2": "#e0b000",
    "in3": "#2f9e44",
    "in4": "#1c7ed6",
    "sw": "#e64980",     # tilt switch (D10)
    "hall": "#7c3aed",   # KY-024 analog out (A0)
    "mv": "#e03131",     # motor 5 V, from the separate supply
    "nv": "#a61e4d",     # the Nano's own 5 V, for the hall sensor only
    "gnd": "#25262b",
    "usb": "#495057",
}
TXT = dict(COL, in2="#a78400")  # darker yellow for text

# 28BYJ-48 lead colours, plug order
MOTOR_LEADS = ["#1c7ed6", "#f06595", "#fcc419", "#fd7e14", "#e03131"]


def esc(s):
    return html.escape(s, quote=True)


def t(x, y, s, size=10, fill=INK, anchor="start", weight="normal", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}" {extra}>{esc(s)}</text>')


HALO = 'stroke="#fff" stroke-width="4" stroke-linejoin="round" paint-order="stroke"'


def rpath(pts, r=7):
    """Polyline with rounded corners."""
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]

        def toward(ax, ay, bx, by, dist):
            dx, dy = bx - ax, by - ay
            ln = (dx * dx + dy * dy) ** 0.5 or 1
            dist = min(dist, ln / 2)
            return ax + dx / ln * dist, ay + dy / ln * dist

        ax, ay = toward(x1, y1, x0, y0, r)
        bx, by = toward(x1, y1, x2, y2, r)
        d += f" L{ax:.1f},{ay:.1f} Q{x1:.1f},{y1:.1f} {bx:.1f},{by:.1f}"
    d += f" L{pts[-1][0]:.1f},{pts[-1][1]:.1f}"
    return d


def wire(pts, color, width=4.6, dots=True, r=7):
    d = rpath(pts, r)
    out = (f'<path d="{d}" fill="none" stroke="#000" stroke-opacity="0.35" stroke-width="{width + 2.2}" '
           f'stroke-linecap="round" stroke-linejoin="round"/>'
           f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
           f'stroke-linejoin="round"/>')
    if dots:
        for (x, y) in (pts[0], pts[-1]):
            out += f'<circle cx="{x}" cy="{y}" r="4.3" fill="{color}" stroke="#111" stroke-width="1"/>'
    return out


def tag(x, y, s, color, size=9):
    w = len(s) * size * 0.56 + 10
    h = size + 5
    return (f'<rect x="{x - w / 2:.1f}" y="{y - h / 2:.1f}" width="{w:.1f}" height="{h}" rx="{h / 2}" '
            f'fill="#fff" stroke="{color}" stroke-width="1.4"/>'
            + t(x, y + size * 0.36, s, size, color, "middle", "bold"))


def arrow_defs(colors):
    return "<defs>" + "".join(
        f'<marker id="arr-{c[1:]}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" '
        f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>' for c in colors) + "</defs>"


# ---------------------------------------------------------------- Arduino Nano

NANO_TOP = ["D12", "D11", "D10", "D9", "D8", "D7", "D6", "D5", "D4", "D3", "D2", "GND", "RST", "RX0", "TX1"]
NANO_BOT = ["D13", "3V3", "REF", "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "5V", "RST", "GND", "VIN"]
NANO_RING_TOP = {1: COL["in4"], 2: COL["sw"], 3: COL["in3"], 5: COL["in2"], 6: COL["in1"],
                 7: COL["in4"], 8: COL["in3"], 9: COL["in2"], 10: COL["in1"], 11: COL["gnd"]}
NANO_RING_BOT = {3: COL["hall"], 11: COL["nv"], 13: COL["gnd"]}


def nano(x0, pitch, ytop, ybot, usb_label=True, name="NANO"):
    """Nano top view, USB on the left. x0 = x of the first (D12/D13) pin."""
    x1 = x0 + 14 * pitch
    out = []
    my = (ytop + ybot) / 2
    out.append(f'<rect x="{x0 - pitch * 2.05:.1f}" y="{my - 21}" width="{pitch * 1.9:.1f}" height="42" rx="3" '
               f'fill="#c9ced6" stroke="#8a9099" stroke-width="1"/>')
    if usb_label:
        out.append(t(x0 - pitch * 1.15, my + 3.5, "USB", 9.5, "#333", "middle", "bold"))
    out.append(f'<rect x="{x0 - pitch * 0.62:.1f}" y="{ytop - 15}" width="{x1 - x0 + pitch * 1.24:.1f}" '
               f'height="{ybot - ytop + 30}" rx="5" fill="#1f5fa8" stroke="#163f73" stroke-width="1.2"/>')
    out.append(f'<rect x="-15" y="-15" width="30" height="30" fill="#1b1f24" '
               f'transform="translate({x0 + pitch * 7.6:.1f},{my:.1f}) rotate(45)"/>')
    out.append(t(x0 + pitch * 11.6, my + 4.5, name, 13, "#fff", "middle", "bold"))
    for names, rings, y, top in ((NANO_TOP, NANO_RING_TOP, ytop, True), (NANO_BOT, NANO_RING_BOT, ybot, False)):
        for i, pin in enumerate(names):
            x = x0 + i * pitch
            used = i in rings
            if used:
                out.append(f'<circle cx="{x}" cy="{y}" r="9.2" fill="#fff" stroke="{rings[i]}" stroke-width="3"/>')
            out.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#e6b325" stroke="#9c7a12" stroke-width="0.8"/>')
            ly = y + 13 if top else y - 13
            anchor = "end" if top else "start"
            out.append(f'<text x="{x + 3.3:.1f}" y="{ly:.1f}" font-size="{8.2 if used else 7.6}" '
                       f'fill="{"#fff" if used else "#c9dcf2"}" font-weight="{"bold" if used else "normal"}" '
                       f'text-anchor="{anchor}" transform="rotate(-90 {x + 3.3:.1f} {ly:.1f})">{pin}</text>')
    return "".join(out)


def nano_figure():
    return f'<svg viewBox="0 0 450 182" width="100%">{nano(75, 25, 30, 150, name="MODULE")}</svg>'


# ---------------------------------------------------------------- parts drawings

def uln_board(x, y, w, h, pins, scale_text=1.0, socket=True, jumper_side="left"):
    """Stylised ULN2003 board. pins = [(x, label), ...] along the bottom edge at y + h - 14.
    Returns svg; the socket is centred on the top edge."""
    o = []
    o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#2f6f4f" stroke="#1e4a34" stroke-width="1.2"/>')
    # ULN2003 chip
    cx0 = x + w / 2
    o.append(f'<rect x="{cx0 - 34}" y="{y + 40}" width="68" height="24" rx="2" fill="#1b1f24"/>')
    o.append(t(cx0, y + 56, "ULN2003", 8.5 * scale_text, "#ced4da", "middle", "bold"))
    # LEDs A..D
    for i, s in enumerate("ABCD"):
        lx = cx0 - 33 + i * 22
        o.append(f'<circle cx="{lx}" cy="{y + 78}" r="4.2" fill="#ff6b6b" stroke="#c92a2a" stroke-width="0.8"/>')
        o.append(t(lx + 7, y + 81, s, 6.5, "#d3f9d8", "start"))
    # motor socket (white, 5 pins), on the top edge
    if socket:
        o.append(f'<rect x="{cx0 - 30}" y="{y - 6}" width="60" height="22" rx="2" fill="#f8f9fa" stroke="#adb5bd"/>')
        for i in range(5):
            o.append(f'<rect x="{cx0 - 24 + i * 11}" y="{y + 1}" width="5" height="8" fill="#868e96"/>')
    # header
    py = y + h - 14
    for px, label in pins:
        o.append(f'<rect x="{px - 5}" y="{py - 5}" width="10" height="10" fill="#e6b325" stroke="#9c7a12" stroke-width="0.8"/>')
        o.append(t(px, py - 10, label, 7.6 * scale_text, "#fff", "middle", "bold"))
    return "".join(o)


def jumper_cap(x, y):
    """Two-pin power jumper (ON/OFF) with a black cap; x, y = centre."""
    return (f'<rect x="{x - 12}" y="{y - 6}" width="24" height="12" rx="2" fill="#1b1f24"/>'
            + t(x, y + 3, "ON", 6.5, "#adb5bd", "middle", "bold"))


def uln_figure():
    o = []
    bx, by, bw, bh = 200, 60, 240, 200
    pins = [(bx + 40 + i * 26, f"IN{i + 1}") for i in range(4)] + [(bx + 170, "−"), (bx + 196, "+")]
    o.append(uln_board(bx, by, bw, bh, pins, 1.15))
    o.append(jumper_cap(bx + 183, by + bh - 50))
    # callouts
    def note(x1, y1, x2, y2, lines, color=INK, anchor="start"):
        o.append(f'<path d="M{x1},{y1} L{x2},{y2}" stroke="#868e96" stroke-width="1" fill="none"/>')
        o.append(f'<circle cx="{x1}" cy="{y1}" r="2.2" fill="#868e96"/>')
        for i, s in enumerate(lines):
            o.append(t(x2 + (4 if anchor == "start" else -4), y2 + 4 + i * 12, s, 9.5 if i == 0 else 8.8,
                       color if i == 0 else MUTED, anchor, "bold" if i == 0 else "normal"))

    note(bx + 150, by + 2, 470, 34, ["Motor socket", "white, 5 pins, keyed"])
    note(bx + 153, by + 78, 470, 104, ["LEDs A–D", "blink while the motor steps"])
    note(bx + 183, by + bh - 50, 470, 166, ["Power jumper", "must be fitted (ON)"], ORANGE_CAP)
    note(bx + 183, by + bh - 14, 470, 222, ["Power − / +", "to the separate 5 V supply"], COL["mv"])
    note(bx + 79, by + bh - 14, 170, 222, ["IN1 IN2 IN3 IN4", "signals from the Nano"], TEAL, "end")
    note(bx + 86, by + 52, 170, 100, ["The ULN2003 chip", "switches the motor coils"], INK, "end")
    o.append(t(320, 280, "Typical layout. Go by the labels printed next to the pins on your board.", 9, MUTED, "middle"))
    return f'<svg viewBox="0 0 640 288" width="100%">{"".join(o)}</svg>'


def motor_drawing(cxm, cym, r=34, label=True):
    """28BYJ-48 seen from the shaft side. Returns svg; the cable leaves at the bottom."""
    o = []
    for sx in (-1, 1):
        ex = cxm + sx * (r + 9)
        o.append(f'<path d="M{cxm + sx * (r - 6)},{cym - 9} L{ex},{cym - 7} A7,7 0 0 {1 if sx > 0 else 0} {ex},{cym + 7} '
                 f'L{cxm + sx * (r - 6)},{cym + 9} Z" fill="#ced4da" stroke="#868e96" stroke-width="1"/>')
        o.append(f'<circle cx="{ex}" cy="{cym}" r="2.8" fill="#fff" stroke="#868e96"/>')
    o.append(f'<rect x="{cxm - 15}" y="{cym + r - 10}" width="30" height="18" rx="2" fill="#4dabf7" stroke="#1c7ed6"/>')
    o.append(f'<circle cx="{cxm}" cy="{cym}" r="{r}" fill="#dee2e6" stroke="#868e96" stroke-width="1.4"/>')
    o.append(f'<circle cx="{cxm}" cy="{cym - 8}" r="8" fill="#adb5bd" stroke="#868e96"/>')
    o.append(f'<rect x="{cxm - 2.5}" y="{cym - 13}" width="5" height="10" fill="#495057"/>')
    if label:
        o.append(t(cxm, cym + 17, "5VDC", 7.5, "#495057", "middle", "bold"))
    return "".join(o)


def motor_figure():
    o = [motor_drawing(70, 50, 38)]
    # cable to plug
    for i, c in enumerate(MOTOR_LEADS):
        x = 62 + i * 4
        o.append(f'<path d="M{x},96 C{x},118 {54 + i * 8},118 {54 + i * 8},140" stroke="{c}" stroke-width="2.6" fill="none"/>')
    o.append('<rect x="44" y="138" width="52" height="18" rx="2" fill="#f8f9fa" stroke="#868e96"/>')
    o.append(t(70, 174, "white 5-pin plug", 8.5, MUTED, "middle"))
    o.append(t(130, 44, "Check the label:", 9, INK, "start", "bold"))
    o.append(t(130, 57, "5VDC version", 9, INK, "start"))
    o.append(t(130, 84, "Shaft is off-centre", 9, INK, "start", "bold"))
    o.append(t(130, 97, "(the module is designed", 8.5, MUTED, "start"))
    o.append(t(130, 109, "for that)", 8.5, MUTED, "start"))
    o.append(t(130, 140, "Red lead = common 5 V", 8.5, MUTED, "start"))
    return f'<svg viewBox="0 0 250 180" width="100%">{"".join(o)}</svg>'


def ky024_drawing(x, y, pitch=24, labels=True):
    """KY-024 with its 4 header pins (AO, G, +, DO) along the top edge at x, x+p, x+2p, x+3p, y.
    The board hangs below the pins; the hall element is at the far end."""
    o = []
    bx0, bx1 = x - 22, x + 3 * pitch + 22
    o.append(f'<rect x="{bx0}" y="{y - 10}" width="{bx1 - bx0}" height="70" rx="5" fill="#c92a2a" stroke="#8f1d1d"/>')
    # pot, LEDs, comparator
    o.append(f'<rect x="{x + 8}" y="{y + 16}" width="22" height="22" rx="2" fill="#1c7ed6" stroke="#1864ab"/>')
    o.append(f'<circle cx="{x + 19}" cy="{y + 27}" r="5" fill="#e9ecef"/>')
    o.append(f'<rect x="{x + 40}" y="{y + 18}" width="20" height="16" fill="#1b1f24"/>')
    o.append(f'<circle cx="{x + 3 * pitch - 2}" cy="{y + 24}" r="3.2" fill="#ffd43b" stroke="#b08900"/>')
    # hall element (TO-92), bent flat, legs into the board
    hx = (bx0 + bx1) / 2
    for dx in (-5, 0, 5):
        o.append(f'<line x1="{hx + dx}" y1="{y + 56}" x2="{hx + dx}" y2="{y + 72}" stroke="#9aa0a6" stroke-width="1.6"/>')
    o.append(f'<path d="M{hx - 9},{y + 72} h18 v12 a9,6 0 0 1 -18,0 z" fill="#1b1f24"/>')
    for i, name in enumerate(["AO", "G", "+", "DO"]):
        px = x + i * pitch
        o.append(f'<rect x="{px - 5}" y="{y - 5}" width="10" height="10" fill="#e6b325" stroke="#9c7a12" stroke-width="0.8"/>')
        if labels:
            o.append(t(px, y + 12, name, 7.8, "#fff", "middle", "bold"))
    return "".join(o)


def ky024_figure():
    o = [ky024_drawing(70, 50, 24)]
    o.append(wire([(70, 45), (70, 14)], COL["hall"], 3.6, dots=False))
    o.append(wire([(94, 45), (94, 14)], COL["gnd"], 3.6, dots=False))
    o.append(wire([(118, 45), (118, 14)], COL["nv"], 3.6, dots=False))
    o.append(t(70, 8, "→ A0", 8.5, TXT["hall"], "middle", "bold"))
    o.append(t(94, 8, "GND", 8.5, INK, "middle", "bold"))
    o.append(t(124, 8, "Nano 5V", 8.5, COL["nv"], "middle", "bold"))
    o.append(t(200, 46, "DO: empty", 8.5, MUTED, "start"))
    o.append(t(36, 82, "pot:", 8, MUTED, "end"))
    o.append(t(36, 92, "unused", 8, MUTED, "end"))
    o.append(t(132, 140, "hall sensor, bent flat", 8.5, INK, "start", "bold"))
    o.append(t(132, 152, "into the cradle floor pocket", 8.5, MUTED, "start"))
    return f'<svg viewBox="0 0 280 160" width="100%">{"".join(o)}</svg>'


def switch_drawing(x, y, s=1.0, order=("C", "NO", "NC"), labels=True, roller_left=True):
    """Roller microswitch; terminals at x+20s, x+50s, x+80s named by order; bottom at y+52s."""
    o = [f'<g transform="translate({x},{y}) scale({s})">']
    if roller_left:
        o.append('<path d="M92,12 L18,-8" stroke="#adb5bd" stroke-width="4" stroke-linecap="round"/>')
        o.append('<circle cx="14" cy="-9" r="8" fill="#ced4da" stroke="#868e96" stroke-width="1.5"/>')
    else:
        o.append('<path d="M8,12 L82,-8" stroke="#adb5bd" stroke-width="4" stroke-linecap="round"/>')
        o.append('<circle cx="86" cy="-9" r="8" fill="#ced4da" stroke="#868e96" stroke-width="1.5"/>')
    o.append('<rect x="0" y="10" width="100" height="32" rx="4" fill="#3a3f47"/>')
    for tx, name in zip((20, 50, 80), order):
        o.append(f'<rect x="{tx - 4}" y="42" width="8" height="10" fill="#d4d8dd" stroke="#868e96" stroke-width="0.8"/>')
        if labels:
            o.append(t(tx, 33, name, 9.5, "#fff", "middle", "bold"))
    o.append("</g>")
    return "".join(o)


def switch_figure():
    o = [switch_drawing(30, 26, 1.25)]
    o.append(wire([(55, 92), (55, 140)], COL["gnd"], dots=False))
    o.append(wire([(92.5, 92), (92.5, 140)], COL["sw"], dots=False))
    o.append(t(48, 156, "C → GND", 10, INK, "middle", "bold"))
    o.append(t(120, 156, "NO → D10", 10, TXT["sw"], "middle", "bold"))
    o.append(t(150, 114, "NC:", 9, MUTED, "middle"))
    o.append(t(150, 125, "empty", 9, MUTED, "middle"))
    return f'<svg viewBox="0 0 190 164" width="100%">{"".join(o)}</svg>'


# ---------------------------------------------------------------- overview block diagram

def overview_figure():
    o = []

    def box(x, y, w, h, title, sub=None, fill="#fff", stroke="#c4cad2", dashed=False):
        dash = ' stroke-dasharray="5 3"' if dashed else ""
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.4"{dash}/>')
        o.append(t(x + w / 2, y + (h / 2 + 4 if not sub else h / 2 - 2), title, 11.5, INK, "middle", "bold"))
        if sub:
            o.append(t(x + w / 2, y + h / 2 + 12, sub, 8.8, MUTED, "middle"))

    def link(pts, color, label=None, lx=None, ly=None, anchor="middle", arrow=True, width=2.4):
        mk = f' marker-end="url(#arr-{color[1:]})"' if arrow else ""
        o.append(f'<path d="{rpath(pts, 6)}" fill="none" stroke="{color}" stroke-width="{width}"{mk}/>')
        if label:
            o.append(t(lx, ly, label, 9, color, anchor, "bold"))

    o.append(arrow_defs(["#495057", COL["in1"], COL["sw"], COL["hall"], COL["mv"], "#5c7cfa", "#adb5bd"]))
    box(0, 128, 112, 52, "Phone / laptop", "web browser")
    box(150, 128, 120, 52, "Raspberry Pi", "runs the web app", fill="#eef8f8", stroke=TEAL)
    # unchanged rail
    box(310, 6, 120, 50, "Sony A6400", "camera", dashed=True, stroke="#adb5bd")
    box(310, 66, 120, 50, "Rail Nano", "unchanged", dashed=True, stroke="#adb5bd")
    box(470, 66, 210, 50, "TMC2209 + NEMA 17 + switch", "the focus rail, as it is today", dashed=True, stroke="#adb5bd")
    # module
    box(310, 140, 120, 90, "Module Nano", "its own USB cable", fill="#eef4fc", stroke="#1f5fa8")
    box(470, 140, 92, 40, "ULN2003", "yaw", fill="#ebfbee", stroke="#2f6f4f")
    box(470, 190, 92, 40, "ULN2003", "tilt", fill="#ebfbee", stroke="#2f6f4f")
    box(600, 140, 80, 40, "28BYJ-48", "yaw motor")
    box(600, 190, 80, 40, "28BYJ-48", "tilt motor")
    box(300, 270, 84, 36, "Tilt switch", None)
    box(394, 270, 70, 36, "KY-024", None)
    box(490, 270, 120, 36, "5 V supply ≥ 1 A", None, fill="#fff5f5", stroke=COL["mv"])
    link([(112, 154), (148, 154)], "#495057", "Wi-Fi", 130, 147)
    link([(270, 146), (290, 146), (290, 31), (308, 31)], "#adb5bd")
    link([(270, 150), (294, 150), (294, 91), (308, 91)], "#adb5bd")
    link([(270, 166), (294, 166), (294, 185), (308, 185)], "#495057", "USB × 3", 278, 122, "start")
    link([(430, 91), (468, 91)], "#adb5bd")
    link([(430, 170), (450, 170), (450, 160), (468, 160)], COL["in1"], "D2–D5", 449, 134, "middle")
    link([(430, 200), (450, 200), (450, 210), (468, 210)], COL["in1"], "D6–D11", 449, 246, "middle")
    link([(562, 160), (598, 160)], "#5c7cfa")
    link([(562, 210), (598, 210)], "#5c7cfa")
    link([(342, 270), (342, 232)], COL["sw"], "D10", 348, 258, "start")
    link([(420, 270), (420, 232)], COL["hall"], "A0", 404, 258, "end")
    link([(530, 270), (530, 232)], COL["mv"], "+5 V", 536, 258, "start")
    o.append(t(550, 322, "only the ground is shared with the Nano", 8.5, MUTED, "middle"))
    o.append(t(560, 26, "2D: nothing here changes", 9.5, MUTED, "middle", "bold"))
    return f'<svg viewBox="0 0 690 330" width="100%">{"".join(o)}</svg>'


# ---------------------------------------------------------------- the complete build

P = 24
X0 = 120          # x of column 1
B = 410           # top edge of the breadboard
TOP_PLUS, TOP_MINUS = B + 20, B + 44
BOT_PLUS, BOT_MINUS = B + 388, B + 412
ROW_IDX = {r: i for i, r in enumerate("abcde")}
ROW_IDX.update({r: i + 7 for i, r in enumerate("fghij")})
NANO_C0 = 7       # D12 / D13 column


def cx(c):
    return X0 + (c - 1) * P


def ry(r):
    return B + 84 + ROW_IDX[r] * P


def hole(h):
    """'c13' -> (x, y)."""
    return cx(int(h[1:])), ry(h[0])


HY = B - 86       # y of the ULN2003 header pins
LANES = [B - 14, B - 30, B - 46, B - 62]
IN_COL = {"in1": COL["in1"], "in2": COL["in2"], "in3": COL["in3"], "in4": COL["in4"]}


def build_figure():
    o = []
    W, H = 950, 990
    left, right = cx(1) - 30, cx(30) + 30
    # ---- breadboard
    o.append(f'<rect x="{left}" y="{B}" width="{right - left}" height="432" rx="10" fill="#f6f1e6" stroke="#d9cfba" stroke-width="1.5"/>')
    o.append(f'<rect x="{left + 2}" y="{(ry("e") + ry("f")) / 2 - 9}" width="{right - left - 4}" height="18" fill="#e5dece"/>')
    for y, col in ((B + 8, "#e03131"), (B + 56, "#1c7ed6"), (B + 376, "#e03131"), (B + 424, "#1c7ed6")):
        o.append(f'<line x1="{left + 14}" y1="{y}" x2="{right - 14}" y2="{y}" stroke="{col}" stroke-width="1.3"/>')
    for y, s, col in ((TOP_PLUS, "+", "#e03131"), (TOP_MINUS, "−", "#1c7ed6"),
                      (BOT_PLUS, "+", "#e03131"), (BOT_MINUS, "−", "#1c7ed6")):
        o.append(t(left + 8, y + 4, s, 12, col, "middle", "bold"))
        o.append(t(right - 8, y + 4, s, 12, col, "middle", "bold"))
    for y, s, col in ((TOP_PLUS, "motor 5 V", COL["mv"]), (TOP_MINUS, "GND", INK),
                      (BOT_PLUS, "Nano 5 V", COL["nv"]), (BOT_MINUS, "GND", INK)):
        o.append(t(right + 6, y + 4, s, 10, col, "start", "bold"))
    for c in range(1, 31):
        x = cx(c)
        for y in (TOP_PLUS, TOP_MINUS, BOT_PLUS, BOT_MINUS):
            o.append(f'<rect x="{x - 2.6}" y="{y - 2.6}" width="5.2" height="5.2" fill="#6b6b6b"/>')
        for r in "abcdefghij":
            o.append(f'<rect x="{x - 2.6}" y="{ry(r) - 2.6}" width="5.2" height="5.2" fill="#6b6b6b"/>')
    for c in (1, 5, 10, 15, 20, 25, 30):
        o.append(t(cx(c), B + 70, str(c), 8.5, "#8a8170", "middle"))
        o.append(t(cx(c), B + 366, str(c), 8.5, "#8a8170", "middle"))
    for r in "abcdefghij":
        o.append(t(left + 14, ry(r) + 3.5, r, 9, "#8a8170", "middle"))
        o.append(t(right - 14, ry(r) + 3.5, r, 9, "#8a8170", "middle"))

    # ---- module Nano
    o.append(nano(cx(NANO_C0), P, ry("d"), ry("h"), name="MODULE"))

    # ---- short jumpers on the board
    def jumper(h, y_rail, color, label, lx=None, ly=None):
        x, y = hole(h)
        o.append(wire([(x, y), (x, y_rail)], color))
        o.append(tag(lx if lx is not None else x, ly if ly is not None else (y + y_rail) / 2, label, color, 8))

    jumper("a18", TOP_MINUS, COL["gnd"], "W1", ly=(ry("a") + TOP_MINUS) / 2 + 2)
    jumper("j18", BOT_PLUS, COL["nv"], "W2", ly=ry("j") + 22)
    jumper("j20", BOT_MINUS, COL["gnd"], "W3", ly=ry("j") + 34)

    # ---- ULN2003 boards above the breadboard
    board_top = B - 228

    def uln(in_cols, pwr, pwr_side, title, motor_label):
        # in_cols: x of IN4, IN3, IN2, IN1 (left to right); pwr: [(x, '+'|'−'), ...]
        xs = [x for x in in_cols] + [x for x, _ in pwr]
        bx0, bx1 = min(xs) - 24, max(xs) + 24
        pins = [(x, f"IN{4 - i}") for i, x in enumerate(in_cols)] + pwr
        o.append(uln_board(bx0, board_top, bx1 - bx0, HY - board_top + 14, pins))
        jx = pwr[0][0] if pwr_side == "left" else pwr[-1][0]
        jx = (pwr[0][0] + pwr[1][0]) / 2
        o.append(jumper_cap(jx, HY - 34))
        o.append(t((bx0 + bx1) / 2, board_top + 30, title, 10, "#fff", "middle", "bold"))
        # motor above, cable into the socket
        mcx = (bx0 + bx1) / 2
        mcy = board_top - 92
        o.append(motor_drawing(mcx, mcy, 32))
        for i, c in enumerate(MOTOR_LEADS):
            x0 = mcx - 8 + i * 4
            x1 = mcx - 22 + i * 11
            o.append(f'<path d="M{x0},{mcy + 48} C{x0},{mcy + 70} {x1 + 2.5},{mcy + 66} {x1 + 2.5},{board_top - 6}" '
                     f'stroke="{c}" stroke-width="2.6" fill="none"/>')
        o.append(f'<rect x="{mcx - 30}" y="{board_top - 12}" width="60" height="9" rx="1.5" fill="#f8f9fa" stroke="#868e96"/>')
        o.append(t(mcx + 48, mcy - 4, motor_label, 10.5, INK, "start", "bold"))
        o.append(t(mcx + 48, mcy + 9, "28BYJ-48, 5 V", 9, MUTED, "start"))
        return bx0, bx1, mcx, mcy

    # tilt: IN4..IN1 at c3..c6, + at c1, − at c2; yaw: IN4..IN1 at c19..c22, − at c24, + at c25
    tilt_in = [cx(3), cx(4), cx(5), cx(6)]
    yaw_in = [cx(19), cx(20), cx(21), cx(22)]
    tb = uln(tilt_in, [(cx(1), "+"), (cx(2), "−")], "left", "TILT driver", "tilt motor")
    yb = uln(yaw_in, [(cx(24), "−"), (cx(25), "+")], "right", "YAW driver", "yaw motor")
    o.append(tag(tb[2] + 42, tb[3] + 66, "M2", "#495057", 8.5))
    o.append(tag(yb[2] + 42, yb[3] + 66, "M1", "#495057", 8.5))

    # ---- signal wires: Nano top row up to the boards, fanned out in lanes
    names = ["in4", "in3", "in2", "in1"]
    # tilt: D11 (c8) → IN4, D9 (c10) → IN3, D7 (c12) → IN2, D6 (c13) → IN1, fanning left (D10, the
    # switch, and the free D8 sit between them); the leftmost runs lowest
    tilt_cols = (8, 10, 12, 13)
    for i, c in enumerate(tilt_cols):
        x, y = hole(f"a{c}")
        lane = LANES[i]
        px = tilt_in[i]
        o.append(wire([(x, y), (x, lane), (px, lane), (px, HY)], IN_COL[names[i]], r=6))
    # yaw: D5 (c14) → IN4 ... D2 (c17) → IN1, fanning right; the rightmost runs lowest
    yaw_cols = (14, 15, 16, 17)
    for i, c in enumerate(yaw_cols):
        x, y = hole(f"a{c}")
        lane = LANES[3 - i]
        px = yaw_in[i]
        o.append(wire([(x, y), (x, lane), (px, lane), (px, HY)], IN_COL[names[i]], r=6))
    tilt_ids = ["W11  D11 → IN4", "W10  D9 → IN3", "W9  D7 → IN2", "W8  D6 → IN1"]
    yaw_ids = ["W7  D5 → IN4", "W6  D4 → IN3", "W5  D3 → IN2", "W4  D2 → IN1"]
    for i, c in enumerate(tilt_cols):
        o.append(tag((cx(c) + tilt_in[i]) / 2 + 2, LANES[i], tilt_ids[i], TXT[names[i]], 8))
    for i, c in enumerate(yaw_cols):
        o.append(tag((cx(c) + yaw_in[i]) / 2 - 2, LANES[3 - i], yaw_ids[i], TXT[names[i]], 8))

    # ---- driver power: straight down to the top rails
    o.append(wire([(cx(1), HY), (cx(1), TOP_PLUS)], COL["mv"]))
    o.append(wire([(cx(2), HY), (cx(2), TOP_MINUS)], COL["gnd"]))
    o.append(wire([(cx(24), HY), (cx(24), TOP_MINUS)], COL["gnd"]))
    o.append(wire([(cx(25), HY), (cx(25), TOP_PLUS)], COL["mv"]))
    o.append(tag(cx(1), B - 50, "W18", COL["mv"], 8))
    o.append(tag(cx(2), B - 30, "W17", COL["gnd"], 8))
    o.append(tag(cx(24), B - 30, "W19", COL["gnd"], 8))
    o.append(tag(cx(25), B - 50, "W20", COL["mv"], 8))

    # ---- 5 V supply, top right; leads straight down to the top rails
    sx0, sy0 = cx(27) + 2, B - 190
    o.append(f'<rect x="{sx0}" y="{sy0}" width="132" height="84" rx="8" fill="#e9ecef" stroke="#868e96" stroke-width="1.5"/>')
    o.append(f'<rect x="{sx0 + 12}" y="{sy0 + 12}" width="108" height="22" rx="3" fill="#1b4332"/>')
    o.append(t(sx0 + 66, sy0 + 27, "5.0 V   1.0 A", 10, "#69db7c", "middle", "bold", 'font-family="Consolas, monospace"'))
    o.append(t(sx0 + 66, sy0 + 50, "5 V supply", 10, INK, "middle", "bold"))
    o.append(t(sx0 + 66, sy0 + 63, "≥ 1 A, separate", 8.5, MUTED, "middle"))
    gx, vx = cx(28), cx(29)
    o.append(f'<circle cx="{gx}" cy="{sy0 + 84}" r="6" fill="#25262b"/><circle cx="{vx}" cy="{sy0 + 84}" r="6" fill="#e03131"/>')
    o.append(wire([(gx, sy0 + 90), (gx, TOP_MINUS)], "#25262b", width=5.5))
    o.append(wire([(vx, sy0 + 90), (vx, TOP_PLUS)], "#c92a2a", width=5.5))
    o.append(tag(gx - 4, B - 50, "V1 −", "#25262b", 8))
    o.append(tag(vx + 6, B - 30, "V2 +", "#c92a2a", 8))

    # ---- tilt switch, top left. NO → b9 (D10) along a lane between rows a and b; C → top GND rail
    sw_x, sw_y, ss = 6, B - 186, 0.75   # terminals NC, NO, C at x = 21, 43.5, 66
    o.append(switch_drawing(sw_x, sw_y, ss, order=("NC", "NO", "C"), roller_left=False))
    no_x, c_x = sw_x + 50 * ss, sw_x + 80 * ss
    sb = sw_y + 52 * ss
    lane_ab = ry("a") + 12
    o.append(wire([(no_x, sb), (no_x, lane_ab), (cx(9), lane_ab), (cx(9), ry("b"))], COL["sw"], r=6))
    o.append(wire([(c_x, sb), (c_x, TOP_MINUS), (cx(1), TOP_MINUS)], COL["gnd"], r=6))
    o.append(t(sw_x + 50 * ss, sw_y - 24, "tilt switch", 10, INK, "middle", "bold"))
    o.append(tag(no_x, B - 60, "W12", TXT["sw"], 8))
    o.append(tag(c_x, B - 30, "W13", COL["gnd"], 8))
    o.append(tag(cx(4.6), lane_ab, "W12  D10 → NO", TXT["sw"], 8))

    # ---- KY-024 below the board: AO → j10 (A0), G → bottom GND rail, + → bottom Nano-5 V rail
    ky_y = B + 478
    o.append(ky024_drawing(cx(10), ky_y, P))
    o.append(wire([(cx(10), ry("j")), (cx(10), ky_y)], COL["hall"]))
    o.append(wire([(cx(11), BOT_MINUS), (cx(11), ky_y)], COL["gnd"]))
    o.append(wire([(cx(12), BOT_PLUS), (cx(12), ky_y)], COL["nv"]))
    o.append(tag(cx(10) - 32, ky_y - 22, "W14  A0 → AO", TXT["hall"], 8))
    o.append(tag(cx(13) + 26, ky_y - 30, "W15  G", COL["gnd"], 8))
    o.append(tag(cx(13) + 30, ky_y - 14, "W16  +", COL["nv"], 8))
    o.append(t(cx(14) + 6, ky_y + 30, "KY-024", 10.5, INK, "start", "bold"))
    o.append(t(cx(14) + 6, ky_y + 43, "DO and pot unused", 9, MUTED, "start"))

    # ---- USB to the Pi
    usb_y = (ry("d") + ry("h")) / 2
    ux = cx(NANO_C0) - P * 2.05
    o.append(f'<path d="{rpath([(ux, usb_y), (24, usb_y), (24, H - 72)], 10)}" fill="none" stroke="#495057" '
             f'stroke-width="6" stroke-linecap="round"/>')
    o.append(t(32, usb_y - 8, "USB (module Nano)", 9.5, "#495057", "start", "bold"))
    o.append(f'<rect x="6" y="{H - 72}" width="196" height="64" rx="8" fill="#eef8f8" stroke="{TEAL}" stroke-width="1.5"/>')
    o.append(t(104, H - 48, "Raspberry Pi", 12, INK, "middle", "bold"))
    o.append(t(104, H - 33, "USB: camera, rail Nano,", 9, MUTED, "middle"))
    o.append(t(104, H - 21, "module Nano (3 of 4 ports)", 9, MUTED, "middle"))

    # ---- warning on the board
    o.append(t(right, B + 452, "The top and bottom + rails are never joined.", 9.5, COL["mv"], "end", "bold"))
    return f'<svg viewBox="0 44 {W} {H - 44}" width="100%">{"".join(o)}</svg>'


# ---------------------------------------------------------------- cable routing (front view)

def routing_figure():
    """Front view from the camera: −Y (tilt motor) left, +Y (bearing, switch) right."""
    o = []
    ax, ay = 300, 120        # tilt axis centre (between the uprights)
    # base
    o.append('<rect x="120" y="300" width="360" height="16" rx="2" fill="#3b4a8a"/>')
    o.append('<rect x="90" y="316" width="420" height="10" rx="2" fill="#ced4da"/>')
    o.append(t(300, 342, "carriage", 9, MUTED, "middle"))
    # uprights
    for x0, w in ((150, 18), (432, 22)):
        o.append(f'<path d="M{x0},300 L{x0},{ay - 10} A{w / 2},{w / 2} 0 0 1 {x0 + w},{ay - 10} L{x0 + w},300 Z" fill="#4c5fb0" stroke="#2f3d7a"/>')
    # tilt motor outside the −Y upright
    o.append(f'<rect x="112" y="{ay - 30}" width="38" height="60" rx="6" fill="#dee2e6" stroke="#868e96"/>')
    o.append(t(131, ay + 4, "tilt", 8.5, INK, "middle", "bold"))
    # switch bracket + switch outside the +Y upright
    o.append(f'<rect x="454" y="{ay + 30}" width="8" height="40" fill="#4c5fb0"/>')
    o.append(f'<rect x="462" y="{ay + 36}" width="26" height="30" rx="3" fill="#3a3f47"/>')
    o.append(t(500, ay + 54, "switch", 8.5, INK, "start", "bold"))
    # cradle: arms + floor, hangs below the axis
    o.append(f'<rect x="176" y="{ay - 46}" width="14" height="196" rx="5" fill="#6b7fd7" stroke="#2f3d7a"/>')
    o.append(f'<rect x="410" y="{ay - 46}" width="14" height="196" rx="5" fill="#6b7fd7" stroke="#2f3d7a"/>')
    o.append(f'<rect x="176" y="{ay + 136}" width="248" height="14" rx="3" fill="#6b7fd7" stroke="#2f3d7a"/>')
    # flag bolt on the +Y arm, and its keep-clear zone
    o.append(f'<rect x="424" y="{ay - 34}" width="22" height="5" fill="#adb5bd"/>')
    o.append(f'<path d="M424,{ay - 60} h40 v40 h-40 z" fill="{COL["sw"]}" fill-opacity="0.12" stroke="{COL["sw"]}" stroke-dasharray="3 2"/>')
    # yaw motor + KY-024 under the floor, head on top
    o.append(f'<rect x="268" y="{ay + 150}" width="64" height="30" rx="6" fill="#dee2e6" stroke="#868e96"/>')
    o.append(t(300, ay + 169, "yaw", 8.5, INK, "middle", "bold"))
    o.append(f'<rect x="214" y="{ay + 150}" width="40" height="8" fill="#c92a2a"/>')
    o.append(t(196, ay + 161, "KY-024", 8, INK, "end", "bold"))
    o.append(f'<rect x="270" y="{ay + 100}" width="60" height="36" rx="5" fill="#4c5fb0"/>')
    o.append(f'<path d="M292,{ay + 100} L300,{ay + 60} L308,{ay + 100} Z" fill="#4c5fb0"/>')
    o.append(f'<line x1="300" y1="{ay + 60}" x2="300" y2="{ay + 6}" stroke="#868e96" stroke-width="1.4"/>')
    o.append(f'<circle cx="300" cy="{ay}" r="5" fill="#495057"/>')
    # tilt axis
    o.append(f'<line x1="96" y1="{ay}" x2="520" y2="{ay}" stroke="{TEAL}" stroke-width="1.2" stroke-dasharray="7 4"/>')
    o.append(t(526, ay + 4, "tilt axis", 9, TEAL, "start", "bold"))
    # cables: yaw + KY-024 along the floor to the −Y arm, up the arm, slack loop near the axis, down the upright
    cab = "#ff922b"
    o.append(wire([(268, ay + 168), (200, ay + 168), (200, ay - 6)], cab, 3.4, dots=False, r=8))
    o.append(wire([(234, ay + 158), (234, ay + 162), (204, ay + 162)], cab, 2.4, dots=False, r=4))
    loop = (f'M200,{ay - 6} C200,{ay - 80} 120,{ay - 84} 104,{ay - 50} C98,{ay - 38} 100,{ay - 20} 100,{ay + 20} '
            f'L100,300')
    o.append(f'<path d="{loop}" fill="none" stroke="#000" stroke-opacity="0.35" stroke-width="5.6"/>')
    o.append(f'<path d="{loop}" fill="none" stroke="{cab}" stroke-width="3.4"/>')
    # ties
    for y in (ay + 40, ay + 100):
        o.append(f'<rect x="194" y="{y}" width="12" height="4" rx="1" fill="#212529"/>')
    o.append(f'<rect x="94" y="{ay + 60}" width="12" height="4" rx="1" fill="#212529"/>')
    # tilt motor + switch cables (fixed parts)
    o.append(wire([(122, ay + 30), (122, 300)], "#868e96", 3, dots=False))
    o.append(wire([(488, ay + 60), (500, ay + 80), (500, 300)], "#868e96", 3, dots=False, r=6))
    # labels
    o.append(t(214, ay - 74, "slack loop over the axis", 9.5, cab, "start", "bold"))
    o.append(t(214, ay - 62, "(the cradle swings −33° to +97°)", 9, MUTED, "start"))
    o.append(t(88, ay + 66, "tie", 9, INK, "end", "bold"))
    o.append(t(214, ay + 74, "tied to", 9, INK, "start", "bold"))
    o.append(t(214, ay + 86, "the −Y arm", 9, INK, "start", "bold"))
    o.append(t(470, ay - 66, "keep clear:", 9, TXT["sw"], "start", "bold"))
    o.append(t(470, ay - 54, "flag bolt", 9, TXT["sw"], "start", "bold"))
    o.append(t(150, 364, "−Y: tilt motor side", 10, INK, "middle", "bold"))
    o.append(t(450, 364, "+Y: bearing and switch", 10, INK, "middle", "bold"))
    o.append(t(300, 382, "Seen from the camera. Cables to the breadboard leave at the back (−X).", 9, MUTED, "middle"))
    return f'<svg viewBox="40 30 560 360" width="100%">{"".join(o)}</svg>'


# ---------------------------------------------------------------- page content

def swatch(color):
    return f'<span class="sw" style="background:{color}"></span>'


def ring(color):
    return f'<span class="ring" style="border-color:{color}"></span>'


def sec(n, title):
    return f'<h1 class="sec"><span class="num">{n}</span>{esc(title)}</h1>'


LEGEND = [
    ("D2–D5", "yaw driver IN1–IN4", None),
    ("D6–D11", "tilt driver: D6, D7, D9, D11", None),
    ("IN1", "D2 and D6", COL["in1"]),
    ("IN2", "D3 and D7", COL["in2"]),
    ("IN3", "D4 and D9", COL["in3"]),
    ("IN4", "D5 and D11", COL["in4"]),
    ("D10", "tilt switch NO", COL["sw"]),
    ("A0", "KY-024 AO (hall signal)", COL["hall"]),
    ("5V", "KY-024 + only", COL["nv"]),
    ("GND", "common ground (both pins)", COL["gnd"]),
]

CHECKLIST = [
    ("W1", COL["gnd"], "a18 (Nano GND, top row)", "top GND rail", "common ground with the motors"),
    ("W2", COL["nv"], "j18 (Nano 5V)", "bottom + rail", "Nano 5 V, sensor only"),
    ("W3", COL["gnd"], "j20 (Nano GND, bottom row)", "bottom GND rail", ""),
    ("W4", COL["in1"], "a17 (D2)", "yaw IN1", ""),
    ("W5", COL["in2"], "a16 (D3)", "yaw IN2", ""),
    ("W6", COL["in3"], "a15 (D4)", "yaw IN3", ""),
    ("W7", COL["in4"], "a14 (D5)", "yaw IN4", ""),
    ("W8", COL["in1"], "a13 (D6)", "tilt IN1", ""),
    ("W9", COL["in2"], "a12 (D7)", "tilt IN2", ""),
    ("W10", COL["in3"], "a10 (D9)", "tilt IN3", "D8 stays free"),
    ("W11", COL["in4"], "a8 (D11)", "tilt IN4", "D10 between is the switch"),
    ("W12", COL["sw"], "b9 (D10)", "tilt switch NO", "runs between rows a and b"),
    ("W13", COL["gnd"], "top GND rail (column 1)", "tilt switch C", "NC stays empty"),
    ("W14", COL["hall"], "j10 (A0)", "KY-024 AO", "the analog pin, not DO"),
    ("W15", COL["gnd"], "bottom GND rail", "KY-024 G", ""),
    ("W16", COL["nv"], "bottom + rail (Nano 5 V)", "KY-024 +", ""),
    ("W17", COL["gnd"], "tilt driver −", "top GND rail (column 2)", ""),
    ("W18", COL["mv"], "tilt driver +", "top + rail (column 1)", "motor 5 V"),
    ("W19", COL["gnd"], "yaw driver −", "top GND rail (column 24)", ""),
    ("W20", COL["mv"], "yaw driver +", "top + rail (column 25)", "motor 5 V"),
    ("U1", COL["usb"], "module Nano USB", "Raspberry Pi", "a data cable, not charge-only"),
]

PLACE = [
    ("P1", "Module Nano", "rows <b>d</b> and <b>h</b>, columns <b>7–21</b>",
     "D12/D13 in column 7, USB left"),
    ("P2", "Power jumpers", "on both ULN2003 boards", "the ON/OFF jumper by − +"),
]

LAST = [
    ("M1", "#495057", "yaw motor plug", "yaw driver socket", "keyed: fits one way"),
    ("M2", "#495057", "tilt motor plug", "tilt driver socket", "keyed: fits one way"),
    ("V1", "#25262b", "5 V supply −", "top GND rail (column 28)", "supply unplugged"),
    ("V2", "#c92a2a", "5 V supply +", "top + rail (column 29)", "supply unplugged"),
]


def checklist_html():
    rows = ['<colgroup><col style="width:6mm"><col style="width:10mm"><col style="width:7mm"><col style="width:52mm">'
            '<col style="width:5mm"><col style="width:46mm"><col></colgroup>'
            '<tr class="grp"><td colspan="7">1 · Board and jumpers</td></tr>']
    for pid, part, where, note in PLACE:
        rows.append(f'<tr><td class="box"></td><td class="wid">{pid}</td><td></td><td><b>{part}</b></td>'
                    f'<td class="arrow"></td><td>{where}</td><td class="note">{note}</td></tr>')
    rows.append('<tr class="grp"><td colspan="7">2 · Wires</td></tr>')
    for wid, colr, a, b, note in CHECKLIST:
        rows.append(f'<tr><td class="box"></td><td class="wid">{wid}</td><td>{swatch(colr)}</td><td>{a}</td>'
                    f'<td class="arrow">→</td><td>{b}</td><td class="note">{note}</td></tr>')
    rows.append('<tr class="grp warnrow"><td colspan="7">3 · Last: motors and supply, with the supply unplugged</td></tr>')
    for wid, colr, a, b, note in LAST:
        rows.append(f'<tr><td class="box"></td><td class="wid">{wid}</td><td>{swatch(colr)}</td><td>{a}</td>'
                    f'<td class="arrow">→</td><td>{b}</td><td class="note">{note}</td></tr>')
    return '<table class="check">' + "".join(rows) + "</table>"


def page(n, body):
    return f'<section class="page">{body}<div class="foot">MacroRail scan module wiring guide · {n}</div></section>'


IMG = "../../hardware/scan-module/guide/img"


def build_html():
    pages = []

    # ---------------- page 1: overview
    pages.append(page(1, f"""
<div class="kicker">MacroRail · 3D scan module</div>
<div class="title">Scan module wiring</div>
<p class="lead">Wire the scan module's two motors, its tilt switch and its hall sensor to their own Arduino Nano,
and get both axes moving.</p>
{sec(1, "Overview")}
<p>The scan module has its <b>own Arduino Nano</b>, the <b>module Nano</b>, on its own USB cable to the Pi.
It drives the <b>yaw</b> and <b>tilt</b> motors (two 28BYJ-48s, each through a ULN2003 driver board), reads the
<b>tilt switch</b> and the <b>KY-024 hall sensor</b>, and talks to the app over USB. The motors get their power from a
<b>separate 5 V supply</b>.</p>
<p><b>The rail stays exactly as it is.</b> The rail Nano, its firmware and its wiring don't change at all.
Unplug the module and you have today's rig.</p>
<div class="fig">{overview_figure()}</div>
<h2>What's in this guide</h2>
<table class="toc">
<tr><td class="n">2</td><td><b>Meet the parts</b></td><td>Driver boards, motors, hall sensor, switch, and the shopping list.</td></tr>
<tr><td class="n">3</td><td><b>Build the circuit</b></td><td>The module Nano's pins, the complete wiring picture and a numbered checklist.</td></tr>
<tr><td class="n">4</td><td><b>Cables on the module</b></td><td>Slack for the tilt, and what to keep clear of.</td></tr>
<tr><td class="n">5</td><td><b>Flash &amp; configure</b></td><td>Module firmware, and how the app tells the two Nanos apart.</td></tr>
<tr><td class="n">6</td><td><b>First power-up checks</b></td><td>Directions, switch, hall signal, then homing.</td></tr>
<tr><td class="n">7</td><td><b>Troubleshooting</b></td><td>What a symptom usually means.</td></tr>
</table>
"""))

    # ---------------- page 2: parts
    pages.append(page(2, f"""
{sec(2, "Meet the parts")}
<h2 class="first">The ULN2003 driver board (×2)</h2>
<div class="fig" style="width:88%;margin:1mm auto 0">{uln_figure()}</div>
<p>One board per motor. The Nano's pins can't drive a motor coil, so the board's ULN2003 chip switches each coil for
it: <b>IN1–IN4</b> come from the Nano, the motor plugs into the <b>white socket</b>, and <b>− +</b> take the
separate 5 V supply. The four LEDs show which coils are on. They blink while the motor moves, and they are dark when
it stands still, because the firmware switches the coils off 300 ms after every move.</p>
<div class="two parts-row">
  <div>
    <h3>28BYJ-48 motor (×2)</h3>
    <div class="fig small2">{motor_figure()}</div>
    <p>Buy the <b>5 V</b> version (<i>5VDC</i> on the label); the 12 V one is too weak at 5 V. Its gearbox holds the
    load with the power off. The plug goes into the board's white socket, and fits only one way.</p>
  </div>
  <div>
    <h3>KY-024 hall sensor</h3>
    <div class="fig small2">{ky024_figure()}</div>
    <p>It reads the magnet in the yaw head. Only its <b>analog output AO</b> is used: the app finds the peak of
    the field, which repeats far better than the board's on/off output (DO). So DO, its LED and its potentiometer are
    unused. It reads about 512 with no magnet near.</p>
  </div>
</div>
<div class="two sw-row">
  <div class="fig swfig">{switch_figure()}</div>
  <div>
    <h3>Tilt switch (roller microswitch)</h3>
    <p>Wired like the rail's home switch: <b>C to GND, NO to D10</b>, NC empty. Pressing it pulls D10 low.
    The firmware watches it during every move, so the first contact stops the tilt at once.</p>
    <p class="muted">Wiring it normally-closed (C + NC) instead? Set <code>SWITCH_ACTIVE_LEVEL</code> to <code>HIGH</code>
    in <code>firmware-module/src/config.h</code>.</p>
  </div>
</div>
"""))

    # ---------------- page 3: shopping list, supply, Nano pins
    legend = "".join(
        f'<li>{ring(c) if c else "<span class=ringgap></span>"}<b>{p}</b><span>{d}</span></li>' for p, d, c in LEGEND)
    pages.append(page(3, f"""
<h2 class="first">What you need</h2>
<table class="parts">
<tr><th>Part</th><th>Notes</th></tr>
<tr><td>Arduino Nano: the module Nano</td><td>A CH340 clone is fine. A second one, next to the rail's.</td></tr>
<tr><td>2 × ULN2003 driver board</td><td>Usually sold with the motor.</td></tr>
<tr><td>2 × 28BYJ-48, 5 V version</td><td>Yaw (under the cradle floor) and tilt (on the −Y upright).</td></tr>
<tr><td>KY-024 linear hall board</td><td>Bolted under the cradle floor, sensor bent flat into its pocket.</td></tr>
<tr><td>Roller microswitch</td><td>On the printed bracket on the +Y upright.</td></tr>
<tr><td>5 V supply, at least 1 A</td><td>For the motors only. A bench supply set to 5.0 V works well.</td></tr>
<tr><td>Small breadboard (optional)</td><td>Half size, 30 columns. A terminal block works too: same connections.</td></tr>
<tr><td>Jumper wires (Dupont)</td><td>Male-female for the boards, male-male on the breadboard, long enough for the module.</td></tr>
<tr><td>USB cable (Mini-B for most Nanos)</td><td>A data cable: a charge-only cable powers the Nano but the Pi can't see it.</td></tr>
<tr><td>Cable ties, multimeter</td><td>Ties for the cradle cables; the meter for the checks in section 6.</td></tr>
</table>
<div class="callout warn"><b>Why a separate 5 V supply?</b><br>
Each 28BYJ-48 draws about 240 mA while it moves. The Nano's 5 V comes from the Pi's USB port, which also feeds the
camera link and the rail Nano; motor current there causes resets and USB drop-outs. So the motors get their own supply,
and only its <b>ground</b> is joined to the Nano's.
<b>Never join the supply's + to the Nano's 5V pin.</b> Two supplies would fight each other.</div>

{sec(3, "Build the circuit")}
<h2 class="first">The module Nano</h2>
<div class="nano-row">
  <div class="fig">{nano_figure()}<p class="cap">As it sits on the breadboard: USB on the left.</p></div>
  <div class="legend"><div class="lh">Pins this module uses</div><ul>{legend}</ul></div>
</div>
<p>The yaw driver takes D2–D5 and the tilt driver D6, D7, D9, D11 (D8 stays free, D10 is the switch), both in the
order IN1, IN2, IN3, IN4. IN1 has the same colour on both boards, and so on, so a swapped pair is easy to spot.</p>
"""))

    # ---------------- page 4: complete build
    pages.append(page(4, f"""
<h2 class="first">The complete build</h2>
<div class="fig">{build_figure()}</div>
<p class="cap">Holes a–e of one column are one strip, f–j another; each rail runs the full length. The <b>top rails</b>
carry the motor supply, the <b>bottom rails</b> the Nano's own 5 V for the hall sensor. The GND rails are joined through
the Nano's GND pins; the two + rails never touch. Motors, switch and sensor sit on the module.</p>
<h2>Quick reference</h2>
<table class="parts qr">
<tr><th>Nano</th><th>Goes to</th><th>Why</th></tr>
<tr><td>D2, D3, D4, D5</td><td>Yaw ULN2003 IN1, IN2, IN3, IN4</td><td>Yaw motor coils, half-stepped.</td></tr>
<tr><td>D6, D7, D9, D11</td><td>Tilt ULN2003 IN1, IN2, IN3, IN4</td><td>Tilt motor coils, half-stepped.</td></tr>
<tr><td>{swatch(COL['sw'])}D10</td><td>Switch NO (switch C → GND)</td><td>Low when pressed. Internal pull-up; watched during every move.</td></tr>
<tr><td>{swatch(COL['hall'])}A0</td><td>KY-024 AO</td><td>The magnet's field, 0–1023, about 512 with no magnet near.</td></tr>
<tr><td>{swatch(COL['nv'])}5V</td><td>KY-024 +</td><td>The sensor only. Never the drivers, never the supply.</td></tr>
<tr><td>{swatch(COL['gnd'])}GND</td><td>Both GND rails</td><td>Common ground with the motor supply: required.</td></tr>
</table>
"""))

    # ---------------- page 5: checklist + quick reference
    pages.append(page(5, f"""
<h2 class="first">Wire it in this order</h2>
<p>Tick off one line at a time and compare with the picture. “Top rails” are above row a, “bottom rails” below row j.
Holes are named row + column, like <code>a17</code>. On the driver boards, go by the labels printed next to the pins.</p>
<div class="callout warn" style="margin-top:0"><b>Reusing a Nano from another project?</b> Take off any capacitor between <b>RST</b> and GND
(often 10 µF, fitted to stop the Nano resetting when its port opens). The app relies on that reset: the Nano then
says which controller it is, and uploading firmware needs it too. A capacitor across 5V and GND can stay.</div>
{checklist_html()}
"""))

    # ---------------- page 6: cable routing
    pages.append(page(6, f"""
{sec(4, "Cables on the module")}
<p>The <b>tilt motor</b> and the <b>switch</b> sit on the fixed fork, so their cables just run down the uprights. The
<b>yaw motor</b> and the <b>KY-024</b> ride on the cradle, which swings from −33° (belly towards the lens) to +97°
(where the switch clicks, past the top view). Their cables must follow that swing without pulling, rubbing or
catching anything.</p>
<div class="fig" style="width:86%;margin:2mm auto 0">{routing_figure()}</div>
<ul class="boxes">
<li><b>Take the cradle's cables to the −Y side</b> (the tilt motor side), along the underside of the floor and up the
−Y arm. Tie them to the arm with two small cable ties.</li>
<li><b>Leave a loose loop near the tilt axis,</b> where the arm moves least. Then run the cables down the
<i>back</i> (−X) of the −Y upright, next to the tilt motor's cable, and tie them there. The loop must allow the full
130° swing.</li>
<li><b>Keep the +Y side clear.</b> The flag bolt on the +Y arm swings past the switch. Nothing may hang there, or it
could press the switch or stop the flag.</li>
<li><b>Keep the camera's side clear.</b> The lens looks between the uprights from the +X side, so all cables leave
the module at the back.</li>
<li><b>The yaw head turns without limit.</b> Nothing electrical turns with it, so no cable may touch the head or the
centring screws.</li>
<li><b>Check it before scanning:</b> after homing (section 6), go to the lowest tilt the app allows, then to +90°, slowly, and watch the loop.</li>
</ul>
<div class="two crop" style="margin-top:1mm">
  <div class="fig"><img src="{IMG}/tilted.png"><p class="cap">The module seen from the front: tilt motor on the −Y
  upright (left), switch bracket on the +Y upright (right).</p></div>
  <div class="fig"><img src="{IMG}/cradle_sub.png"><p class="cap">Under the cradle floor: the yaw motor and the KY-024
  board. Their leads go to the −Y arm.</p></div>
</div>
"""))

    # ---------------- page 7: flash & configure
    pages.append(page(7, f"""
{sec(5, "Flash & configure")}
<h2 class="first">Plug in</h2>
<p>Plug the camera, the rail Nano and the module Nano into the Pi's USB ports (3 of its 4). The module Nano gets its
power from USB; the motors from their own supply.</p>
<h2>Flash the module firmware</h2>
<p>The app owns the serial ports, so stop it first. On the Pi:</p>
<pre>sudo systemctl stop macrorail
ls /dev/serial/by-path/      # unplug and replug the module Nano: its entry comes back
~/.local/bin/pio run -d ~/macrorail/firmware-module -e nano -t upload \\
    --upload-port /dev/serial/by-path/&lt;the module's entry&gt;
sudo systemctl start macrorail</pre>
<p>From your PC over SSH: <code>ssh -t pi sudo systemctl stop macrorail</code>, flash, then
<code>ssh -t pi sudo systemctl start macrorail</code>. Any computer with PlatformIO can flash it too:
<code>pio run -d firmware-module -e nano -t upload --upload-port &lt;port&gt;</code>.</p>
<p class="muted">Use <code>-e nano_new</code> if the upload fails on a genuine or new-bootloader Nano.
Be sure to pick the module's port: flashing the module firmware onto the rail Nano would stop the rail working until
you reflash it with <code>firmware/</code>.</p>
<h2>Tell the app where the Nanos are</h2>
<p>Both Nanos are CH340 clones with no serial number, so their <code>/dev/serial/by-id</code> names are identical and
can't tell them apart. In <code>~/.config/macrorail/config.toml</code>:</p>
<pre>[rail]
port = "auto"

[module]
port = "auto"</pre>
<p>With <code>"auto"</code> the app asks each Nano what it is: the module firmware says so in its first line
(<code>role=module</code>), the rail's doesn't. If you'd rather fix them, give each its USB socket's path from
<code>ls /dev/serial/by-path/</code> instead; that path stays the same as long as the cable stays in the same socket.
<b>An old by-id path under <code>[rail]</code> must go:</b> with two Nanos plugged in, it can point at either.</p>
<p>Then restart the app: <code>sudo systemctl restart macrorail</code>.</p>
"""))

    # ---------------- page 8: first power-up checks
    pages.append(page(8, f"""
{sec(6, "First power-up checks")}
<p>Do these in order, <b>before any homing</b>, with no specimen in the holder. Move the rail so the module is well
clear of the objective: until tilt is homed, the angle is unknown and no limits apply.</p>
<ol class="steps">
<li><b>Supply polarity.</b> Supply off, measure first: set the supply to <b>5.0 V</b>; + goes to the top + rail, − to the
top GND rail. With a meter on beep, the top GND rail beeps to the Nano's GND; the two + rails <b>don't</b> beep to each
other or to GND.</li>
<li><b>Power on.</b> Supply on, Nano on the Pi. Open the app, switch to <b>3D</b>, and check the <b>Scan module</b>
card on the System tab: it shows <i>connected</i>. The Rig tab shows tilt and yaw as not homed. Nothing moves yet,
and all driver LEDs are dark.</li>
<li><b>Tilt direction.</b> On the Rig tab, jog tilt by <b>−1°</b>, a few times. The tilt driver's LEDs blink, and the
cradle must tip the insect's <b>belly towards the lens</b> (the tilt angle goes down; the flag bolt moves away from the
switch). If it turns the other way, set <code>TILT_INVERT = true</code> in <code>firmware-module/src/config.h</code> and
reflash (section 5).</li>
<li><b>Yaw direction.</b> Jog yaw by <b>+10°</b>. The head must turn <b>counter-clockwise seen from above</b>. If it
turns clockwise, set <code>YAW_INVERT = true</code> in the same file and reflash.</li>
<li><b>Switch.</b> Press it by hand. The app shows it <i>pressed</i>, and released when you let go.</li>
<li><b>Hall sensor.</b> Watch the hall reading on the Scan module card and turn the head slowly past the sensor, by
hand (the coils are off when idle) or by jogging yaw 10° at a time. Away from the magnet it reads about 512; near it,
the reading must move at least <b>40</b> away from that, up or down. If it hardly moves, check that the sensor is bent
flat in its pocket and that the magnet is in the head.</li>
<li><b>Home tilt.</b> It turns slowly away from the lens until the flag presses the switch at about +97°, backs off until
the switch releases, and touches it again slowly. That contact is the tilt reference. Watch the first time, ready to
press Stop.</li>
<li><b>Home yaw.</b> It turns counter-clockwise for up to about 1.3 turns, finds the magnet's peak, comes round again and
stops on it from the same side. At <b>yaw 0</b> the magnet is over the hall sensor and centring screw X points at the
camera.</li>
<li><b>Cables.</b> Go to the lowest tilt the app allows and to +90°, slowly, and check the loop (section 4).</li>
</ol>
<div class="callout teal"><b>Then:</b> the Rig tab's quick poses (Level, Top view, Screw X to you…) work, and the
calibration and centring steps follow in the scan module's assembly and usage guide.</div>
"""))

    # ---------------- page 9: troubleshooting
    pages.append(page(9, f"""
{sec(7, "Troubleshooting")}
<table class="parts trouble">
<tr><th>Symptom</th><th>Likely cause and fix</th></tr>
<tr><td>Motor hums or twitches but doesn't turn</td><td>IN wires in the wrong order (IN1–IN4 must be D2–D5, or D6, D7, D9,
D11, in that order), or a wire loose. Or no 5 V on the driver: check the supply, the driver's − + wires and its power jumper. LEDs
that blink while the motor stays still point at the motor plug or the supply.</td></tr>
<tr><td>Nothing moves, LEDs dark</td><td>The IN wires don't reach the board, or the module isn't connected (see below).</td></tr>
<tr><td>Turns the wrong way</td><td>Set <code>TILT_INVERT</code> or <code>YAW_INVERT</code> in
<code>firmware-module/src/config.h</code> and reflash. Don't rewire the motor plug.</td></tr>
<tr><td>Tilt homing fails: <b>NO_SWITCH</b></td><td>The tilt turned all the way without the switch closing. Check the
switch wiring (C → GND, NO → D10, not NC) and press it by hand: the app must show it pressed. Check that the flag bolt
reaches the roller. If the tilt turned towards the lens instead, the direction is wrong (TILT_INVERT).</td></tr>
<tr><td>Tilt homing fails: <b>SWITCH_STUCK</b></td><td>The switch stayed pressed after backing off. The switch is wired
C + NC (reads pressed when open), the flag bolt is set too far out, or the bracket sits too close.</td></tr>
<tr><td>The tilt stops with <b>ENDSTOP</b> during a move</td><td>Something pressed the switch: a cable on the +Y side, or
a loose switch wire picking up noise. Reroute or resolder.</td></tr>
<tr><td>Yaw homing fails: <b>NO_MAGNET</b></td><td>The field peak was under 40 counts. Check the AO wire goes to A0 (not
DO), the sensor's + and G, that the sensor is bent flat under the magnet, and that the magnet is in the head.</td></tr>
<tr><td>Tilt loses steps near +90°</td><td>The cradle is heavy there. Homing on the switch shows any loss. Add the
counterweight: an 8 mm rod with nuts through the holes at the top of the arms.</td></tr>
<tr><td>The module isn't found</td><td>Check <code>port = "auto"</code> under <code>[module]</code>, that the module firmware
is flashed, that no capacitor sits between RST and GND, and that the USB cable carries data (try another). <code>ls /dev/serial/by-path/</code> must show it.</td></tr>
<tr><td>The rail stopped being found after plugging the module in</td><td>Its config still names a by-id path, which now
points at either Nano. Set <code>port = "auto"</code> under <code>[rail]</code> (or its by-path socket) and restart the
app.</td></tr>
<tr><td>The Pi or the Nano resets when a motor starts</td><td>The motors are fed from the Nano's 5 V. Move the drivers' +
to the separate supply; only the grounds are joined.</td></tr>
<tr><td><b>LINK</b> errors, motion stops</td><td>The module lost contact with the Pi for 2 s: a loose USB cable, or the Pi
under-powered. Use the Pi's proper supply.</td></tr>
</table>
<p class="muted" style="margin-top:4mm">The full message list is in <code>docs/protocol-module.md</code>; the pin
constants are in <code>firmware-module/src/config.h</code>.</p>
"""))
    return pages


CSS = """
@page { size: A4; margin: 0; }
* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
html, body { margin: 0; padding: 0; }
body { font-family: "Segoe UI", Arial, sans-serif; color: #1d2127; font-size: 10.2pt; line-height: 1.42; }
svg text { font-family: "Segoe UI", Arial, sans-serif; }
.page { width: 210mm; height: 297mm; padding: 15mm 17mm 16mm; box-sizing: border-box; position: relative;
        overflow: hidden; break-after: page; }
.page:last-child { break-after: auto; }
.foot { position: absolute; bottom: 8mm; left: 0; right: 0; text-align: center; color: #8a8f98; font-size: 8.5pt; }
.kicker { color: #0f8a8a; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; font-size: 10pt; }
.title { font-size: 28pt; font-weight: 700; line-height: 1.1; margin: 1mm 0 2mm; }
.lead { font-size: 11.5pt; color: #4b5563; margin: 0 0 7mm; }
h1.sec { display: flex; align-items: center; gap: 12px; font-size: 21pt; margin: 0 0 3mm; font-weight: 700; }
* + h1.sec { margin-top: 8mm; }
h1.sec .num { background: #0f8a8a; color: #fff; border-radius: 9px; width: 36px; height: 36px; display: inline-flex;
              align-items: center; justify-content: center; font-size: 15pt; flex: none; }
h2 { color: #0f8a8a; font-size: 14pt; margin: 6mm 0 1.5mm; }
h2.first { margin-top: 1mm; }
h3 { font-size: 11pt; margin: 0 0 1.5mm; }
p { margin: 0 0 2.2mm; }
ul, ol { margin: 0 0 2.5mm; padding-left: 5.5mm; }
li { margin-bottom: 1.2mm; }
code, pre { font-family: Consolas, "Cascadia Mono", monospace; }
code { background: #eef1f4; border-radius: 3px; padding: 0 3px; font-size: 9.2pt; }
pre { background: #f3f5f7; border-left: 3px solid #0f8a8a; padding: 2.2mm 3.5mm; margin: 1mm 0 3mm; font-size: 9pt;
      white-space: pre-wrap; }
.fig { margin: 2mm 0 1mm; }
.fig svg, .fig img { display: block; }
.fig img { width: 100%; border-radius: 2mm; }
.crop img { height: 46mm; object-fit: cover; }
.cap { text-align: center; color: #6b7280; font-size: 8.8pt; margin: 1mm 0 3mm; }
.muted { color: #6b7280; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 7mm; align-items: start; }
.callout { border-radius: 6px; padding: 3mm 4mm; margin: 4mm 0 3mm; border-left: 4px solid; }
.callout.warn { background: #fff4e6; border-color: #e8590c; }
.callout.teal { background: #eef8f8; border-color: #0f8a8a; }
ul.boxes { list-style: none; padding-left: 0; }
ul.boxes li { position: relative; padding-left: 7mm; margin-bottom: 1.6mm; }
ul.boxes li::before { content: ""; position: absolute; left: 0; top: 1.2mm; width: 3.4mm; height: 3.4mm;
                      border: 1.4px solid #1d2127; border-radius: 2px; }
table { border-collapse: collapse; width: 100%; }
table.toc td { padding: 1.3mm 2mm; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
table.toc td:nth-child(2) { white-space: nowrap; width: 44mm; }
table.toc td.n { width: 7mm; color: #fff; background: #0f8a8a; text-align: center; font-weight: 700;
                 border-bottom: 2px solid #fff; border-radius: 4px; }
table.parts th { text-align: left; background: #f1f3f5; border-bottom: 1.4px solid #1d2127; padding: 1.5mm 2mm; font-size: 9.6pt; }
table.parts td { border-bottom: 1px solid #e5e7eb; padding: 1.4mm 2mm; vertical-align: top; font-size: 9.6pt; }
table.parts td:first-child { white-space: nowrap; }
table.qr td:first-child { font-weight: 700; }
table.qr td:nth-child(2) { white-space: nowrap; }
table.qr td { padding: 0.9mm 2mm; font-size: 9.3pt; }
table.trouble td:first-child { white-space: normal; width: 52mm; font-weight: 600; }
table.trouble td { padding: 2mm 2mm; }
.sw { display: inline-block; width: 16px; height: 6px; border-radius: 3px; margin-right: 5px; vertical-align: middle;
      box-shadow: 0 0 0 1px rgba(0,0,0,.35); }
.ring { display: inline-block; width: 10px; height: 10px; border-radius: 50%; border: 3px solid; margin-right: 7px;
        vertical-align: middle; flex: none; }
.ringgap { display: inline-block; width: 16px; margin-right: 7px; flex: none; }
.nano-row { display: grid; grid-template-columns: 1.45fr 1fr; gap: 5mm; align-items: center; }
.legend .lh { font-weight: 700; font-size: 9.5pt; margin-bottom: 1.5mm; }
.legend ul { list-style: none; padding: 0; margin: 0; }
.legend li { font-size: 9.2pt; margin-bottom: 1.1mm; display: flex; align-items: center; }
.legend li b { width: 13mm; flex: none; }
.legend li span { color: #6b7280; }
.sw-row { grid-template-columns: 50mm 1fr; margin-top: 2mm; }
.parts-row { margin-top: 2mm; }
.small2 { width: 82%; margin: 0 auto 1mm; }
table.check tr.grp td { font-weight: 700; color: #0f8a8a; padding-top: 2.4mm; border-bottom: 1.4px solid #0f8a8a; }
table.check tr.warnrow td { color: #e8590c; border-bottom-color: #e8590c; }
table.check td { padding: 0.75mm 1.6mm; border-bottom: 1px solid #e5e7eb; font-size: 9.4pt; vertical-align: middle; }
table.check td.box::before { content: ""; display: inline-block; width: 3.4mm; height: 3.4mm; border: 1.4px solid #1d2127;
                             border-radius: 2px; vertical-align: middle; }
table.check { table-layout: fixed; }
table.check td.wid { font-weight: 700; }
table.check td.arrow { color: #9aa0a6; }
table.check td.note { color: #6b7280; font-size: 8.6pt; }
ol.steps { padding-left: 6mm; }
ol.steps li { margin-bottom: 2.2mm; }
"""


def main():
    pages = build_html()
    doc = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
           "<title>MacroRail scan module wiring</title>"
           f"<style>{CSS}</style></head><body>{''.join(pages)}</body></html>")
    with open(os.path.join(HERE, "module-guide.html"), "w", encoding="utf-8") as f:
        f.write(doc)


if __name__ == "__main__":
    main()
