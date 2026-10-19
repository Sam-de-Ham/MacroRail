"""Generates the MacroRail setup guide as HTML (setup-guide.html); see README.md to make the PDF."""

import html
import os

HERE = os.path.dirname(os.path.abspath(__file__))

TEAL = "#0f8a8a"
INK = "#1d2127"
MUTED = "#6b7280"
ORANGE_CAP = "#e8590c"

# One colour per signal; used by the Nano rings, legend, breadboard wires and checklist.
COL = {
    "step": "#f08c00",  # D3
    "dir": "#e0b000",  # D4
    "en": "#7c3aed",  # D5
    "home": "#e64980",  # D2
    "rx": "#2f9e44",  # D7
    "tx": "#1c7ed6",  # D8
    "v5": "#e03131",
    "gnd": "#25262b",
}
TXT = dict(COL, dir="#a78400")  # darker yellow for text


def esc(s):
    return html.escape(s, quote=True)


def t(x, y, s, size=10, fill=INK, anchor="start", weight="normal", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}" {extra}>{esc(s)}</text>')


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


def resistor(x1, y1, x2, y2, bands, label=None):
    """Resistor between two points, body centred, colour bands."""
    import math
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
    ln = math.hypot(x2 - x1, y2 - y1)
    bl = min(36, ln - 10)
    out = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9aa0a6" stroke-width="2"/>'
    for (x, y) in ((x1, y1), (x2, y2)):
        out += f'<circle cx="{x}" cy="{y}" r="3" fill="#9aa0a6"/>'
    out += f'<g transform="translate({cx:.1f},{cy:.1f}) rotate({ang:.1f})">'
    out += f'<rect x="{-bl / 2}" y="-6" width="{bl}" height="12" rx="5" fill="#e9d3a6" stroke="#a88b55" stroke-width="0.8"/>'
    n = len(bands)
    for i, c in enumerate(bands):
        bx = -bl / 2 + 6 + i * (bl - 14) / max(1, n - 1) if i < n - 1 else bl / 2 - 7
        if i < n - 1:
            bx = -bl / 2 + 6 + i * 5
        out += f'<rect x="{bx:.1f}" y="-6" width="3" height="12" fill="{c}"/>'
    out += "</g>"
    return out


BAND = {"brown": "#7b4a1e", "black": "#111", "red": "#d22", "orange": "#f08c00", "gold": "#c9a227"}
R1K = [BAND["brown"], BAND["black"], BAND["red"], BAND["gold"]]
R10K = [BAND["brown"], BAND["black"], BAND["orange"], BAND["gold"]]


# ---------------------------------------------------------------- Arduino Nano

NANO_TOP = ["D12", "D11", "D10", "D9", "D8", "D7", "D6", "D5", "D4", "D3", "D2", "GND", "RST", "RX0", "TX1"]
NANO_BOT = ["D13", "3V3", "REF", "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "5V", "RST", "GND", "VIN"]
NANO_RING_TOP = {4: COL["tx"], 5: COL["rx"], 10: COL["home"], 7: COL["en"], 8: COL["dir"], 9: COL["step"],
                 11: COL["gnd"]}
NANO_RING_BOT = {11: COL["v5"], 13: COL["gnd"]}


def nano(x0, pitch, ytop, ybot, usb_label=True):
    """Nano top view, USB on the left. x0 = x of the first (D12/D13) pin."""
    x1 = x0 + 14 * pitch
    out = []
    # USB stub
    my = (ytop + ybot) / 2
    out.append(f'<rect x="{x0 - pitch * 2.05:.1f}" y="{my - 21}" width="{pitch * 1.9:.1f}" height="42" rx="3" '
               f'fill="#c9ced6" stroke="#8a9099" stroke-width="1"/>')
    if usb_label:
        out.append(t(x0 - pitch * 1.15, my + 3.5, "USB", 9.5, "#333", "middle", "bold"))
    out.append(f'<rect x="{x0 - pitch * 0.62:.1f}" y="{ytop - 15}" width="{x1 - x0 + pitch * 1.24:.1f}" '
               f'height="{ybot - ytop + 30}" rx="5" fill="#1f5fa8" stroke="#163f73" stroke-width="1.2"/>')
    # chip + name
    out.append(f'<rect x="-15" y="-15" width="30" height="30" fill="#1b1f24" '
               f'transform="translate({x0 + pitch * 7.6:.1f},{my:.1f}) rotate(45)"/>')
    out.append(t(x0 + pitch * 11.6, my + 4.5, "NANO", 13, "#fff", "middle", "bold"))
    for row, names, rings, y, top in ((0, NANO_TOP, NANO_RING_TOP, ytop, True),
                                       (1, NANO_BOT, NANO_RING_BOT, ybot, False)):
        for i, name in enumerate(names):
            x = x0 + i * pitch
            used = i in rings
            if used:
                out.append(f'<circle cx="{x}" cy="{y}" r="9.2" fill="#fff" stroke="{rings[i]}" stroke-width="3"/>')
            out.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#e6b325" stroke="#9c7a12" stroke-width="0.8"/>')
            ly = y + 13 if top else y - 13
            anchor = "end" if top else "start"
            out.append(f'<text x="{x + 3.3:.1f}" y="{ly:.1f}" font-size="{8.2 if used else 7.6}" '
                       f'fill="{"#fff" if used else "#c9dcf2"}" font-weight="{"bold" if used else "normal"}" '
                       f'text-anchor="{anchor}" transform="rotate(-90 {x + 3.3:.1f} {ly:.1f})">{name}</text>')
    return "".join(out)


def nano_figure():
    pitch = 25
    x0 = 75
    svg = nano(x0, pitch, 30, 150)
    return f'<svg viewBox="0 0 450 182" width="100%">{svg}</svg>'


# ---------------------------------------------------------------- TMC2209 (parts page)

TMC_LEFT = [("EN", "enable"), ("MS1", "address"), ("MS2", "address"), ("PDN", "UART ← use this one"),
            ("PDN", "(spare)"), ("CLK", "clock"), ("STEP", "step"), ("DIR", "direction")]
TMC_RIGHT = [("VM", "motor + (12 V)"), ("GND", "motor −"), ("A2", "coil A"), ("A1", "coil A"),
             ("B1", "coil B"), ("B2", "coil B"), ("VDD / VIO", "logic 5 V"), ("GND", "logic GND")]


def tmc_figure():
    bx, by, bw, bh = 262, 44, 150, 262
    o = []
    o.append(t(150, 22, "LOGIC SIDE → Arduino", 10, TEAL, "middle", "bold"))
    o.append(t(550, 22, "POWER SIDE → motor + supply", 10, ORANGE_CAP, "middle", "bold"))
    o.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="9" fill="#1e2430"/>')
    # potentiometer
    o.append(f'<circle cx="{bx + bw / 2}" cy="{by + 40}" r="14" fill="#e9ecef" stroke="#adb5bd" stroke-width="2"/>')
    o.append(f'<path d="M{bx + bw / 2 - 8},{by + 40} h16 M{bx + bw / 2},{by + 32} v16" stroke="#495057" stroke-width="3"/>')
    o.append(t(bx + bw / 2, by + 68, "potentiometer", 8.5, "#ced4da", "middle"))
    # cooling pad
    o.append(f'<rect x="{bx + 32}" y="{by + 84}" width="{bw - 64}" height="96" rx="3" fill="#c99a2e" stroke="#a37c1f"/>')
    o.append(t(bx + bw / 2, by + 128, "cooling pad", 10, "#3b2a05", "middle", "bold"))
    o.append(t(bx + bw / 2, by + 143, "(chip is underneath)", 8, "#3b2a05", "middle"))
    for i in range(8):
        y = by + 26 + i * 30
        for side, (name, desc) in ((0, TMC_LEFT[i]), (1, TMC_RIGHT[i])):
            x = bx + 16 if side == 0 else bx + bw - 16
            if i == 0:
                o.append(f'<rect x="{x - 7}" y="{y - 7}" width="14" height="14" fill="#e6b325" stroke="#9c7a12"/>')
            else:
                o.append(f'<circle cx="{x}" cy="{y}" r="7" fill="#e6b325" stroke="#9c7a12"/>')
            if side == 0:
                o.append(t(bx - 12, y + 4.5, name, 12, INK, "end", "bold"))
                hl = i == 3
                o.append(t(bx - 62, y + 4, desc, 9, TEAL if hl else MUTED, "end", "bold" if hl else "normal"))
            else:
                o.append(t(bx + bw + 12, y + 4.5, name, 12, INK, "start", "bold"))
                o.append(t(bx + bw + 92, y + 4, desc, 9, ORANGE_CAP if i == 0 else MUTED, "start"))
    o.append(t(337, 326, "Top view: potentiometer facing you, pins pointing away (into the breadboard).",
               9.5, MUTED, "middle"))
    return f'<svg viewBox="0 0 680 334" width="100%">{"".join(o)}</svg>'


def tmc_side_figure():
    o = []
    o.append(f'<rect x="20" y="100" width="230" height="16" fill="#efe9dc" stroke="#cfc6b2"/>')
    o.append(t(135, 112, "breadboard", 8, "#8a8170", "middle"))
    for x in (45, 225):
        o.append(f'<rect x="{x - 2.5}" y="58" width="5" height="50" fill="#c99a2e"/>')
    o.append(f'<rect x="30" y="50" width="210" height="9" rx="2" fill="#1e2430"/>')
    o.append(f'<rect x="90" y="59" width="50" height="7" fill="#33393f"/>')
    o.append(f'<rect x="140" y="38" width="20" height="12" rx="2" fill="#dee2e6" stroke="#868e96"/>')
    o.append(t(150, 30, "potentiometer: up", 8.5, INK, "middle"))
    o.append(t(80, 80, "chip (bottom)", 8, MUTED, "middle"))
    o.append(t(250, 57, "← board", 8, MUTED))
    o.append(t(250, 82, "← pins go down", 8, MUTED))
    o.append(t(135, 136, "Side view", 8.5, MUTED, "middle"))
    return f'<svg viewBox="0 0 320 142" width="100%">{"".join(o)}</svg>'


# ---------------------------------------------------------------- overview block diagram

def overview_figure():
    o = []

    def box(x, y, w, h, title, sub=None, fill="#fff", stroke="#c4cad2"):
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
        o.append(t(x + w / 2, y + (h / 2 + 4 if not sub else h / 2 - 2), title, 12, INK, "middle", "bold"))
        if sub:
            o.append(t(x + w / 2, y + h / 2 + 13, sub, 9, MUTED, "middle"))

    def link(pts, color, label=None, lx=None, ly=None, anchor="middle", arrow=True, width=2.6):
        d = rpath(pts, 6)
        o.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
                 f'{"marker-end=" + chr(34) + "url(#arr-" + color[1:] + ")" + chr(34) if arrow else ""}/>')
        if label:
            o.append(t(lx, ly, label, 9.5, color, anchor, "bold"))

    colors = ["#495057", COL["step"], COL["rx"], COL["home"], COL["v5"], "#5c7cfa"]
    defs = "".join(
        f'<marker id="arr-{c[1:]}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" '
        f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>' for c in colors)
    o.append(f"<defs>{defs}</defs>")
    box(0, 40, 118, 56, "Phone / laptop", "web browser")
    box(170, 40, 130, 56, "Raspberry Pi", "runs the web app", fill="#eef8f8", stroke=TEAL)
    box(340, 40, 130, 56, "Arduino Nano", "real-time control", fill="#eef4fc", stroke="#1f5fa8")
    box(540, 40, 140, 56, "TMC2209", "stepper driver", fill="#f1f3f5", stroke="#1e2430")
    box(170, 176, 130, 50, "Sony A6400", "camera")
    box(340, 176, 130, 50, "Home switch", "roller microswitch")
    box(540, 176, 64, 50, "NEMA 17", None)
    box(616, 176, 64, 50, "12 V", None)
    link([(118, 68), (168, 68)], "#495057", "Wi-Fi", 143, 61)
    link([(300, 68), (338, 68)], "#495057", "USB", 319, 61)
    link([(235, 98), (235, 174)], "#495057", "USB", 243, 140, "start")
    link([(470, 60), (538, 60)], COL["step"], "STEP DIR EN", 504, 53)
    link([(538, 80), (472, 80)], COL["rx"], "UART", 504, 94, arrow=True)
    o.append(f'<path d="M472,80 L538,80" stroke="{COL["rx"]}" stroke-width="2.6" marker-end="url(#arr-{COL["rx"][1:]})"/>')
    link([(405, 174), (405, 98)], COL["home"], "D2", 413, 140, "start")
    link([(572, 98), (572, 174)], "#5c7cfa", "coils A, B", 566, 140, "end")
    link([(648, 174), (648, 98)], COL["v5"], "VM", 655, 140, "start")
    return f'<svg viewBox="0 0 690 232" width="100%">{"".join(o)}</svg>'


# ---------------------------------------------------------------- breadboard explainer

def breadboard_explainer():
    o = []
    P = 22
    X0, Y0 = 40, 20
    ncol = 12
    o.append(f'<rect x="10" y="4" width="{X0 + (ncol - 1) * P + 30}" height="262" rx="10" fill="#f6f1e6" stroke="#ddd3bf"/>')
    rail_y = Y0 + 10
    rows = {}
    for i, r in enumerate("abcde"):
        rows[r] = Y0 + 50 + i * 18
    for i, r in enumerate("fghij"):
        rows[r] = Y0 + 50 + (i + 6) * 18
    # highlights
    o.append(f'<rect x="{X0 - 12}" y="{rail_y - 8}" width="{(ncol - 1) * P + 24}" height="16" rx="8" fill="#e03131" fill-opacity="0.22"/>')
    hx = X0 + 2 * P
    o.append(f'<rect x="{hx - 9}" y="{rows["a"] - 9}" width="18" height="{rows["e"] - rows["a"] + 18}" rx="6" fill="{TEAL}" fill-opacity="0.25"/>')
    o.append(f'<rect x="{hx - 9}" y="{rows["f"] - 9}" width="18" height="{rows["j"] - rows["f"] + 18}" rx="6" fill="#1c7ed6" fill-opacity="0.18"/>')
    gap_y = (rows["e"] + rows["f"]) / 2
    o.append(f'<rect x="12" y="{gap_y - 7}" width="{X0 + (ncol - 1) * P + 26}" height="14" fill="#e3dccb"/>')
    for c in range(ncol):
        x = X0 + c * P
        o.append(f'<rect x="{x - 2.5}" y="{rail_y - 2.5}" width="5" height="5" fill="#555"/>')
        for r, y in rows.items():
            o.append(f'<rect x="{x - 2.5}" y="{y - 2.5}" width="5" height="5" fill="#555"/>')
    for r, y in rows.items():
        o.append(t(24, y + 3.5, r, 9, MUTED, "middle"))
    for c in (1, 5, 10):
        o.append(t(X0 + (c - 1) * P, rows["a"] - 12, str(c), 8, MUTED, "middle"))
    ax = X0 + (ncol - 1) * P + 50
    o.append(t(ax, rail_y + 4, "a rail: the whole row is one connection", 10, "#c92a2a"))
    o.append(t(ax, (rows["a"] + rows["e"]) / 2 + 4, "a–e of one column = 1 strip", 10, TEAL))
    o.append(t(ax, gap_y - 2, "the gap: left and right halves", 10, "#555"))
    o.append(t(ax, gap_y + 11, "are NOT connected", 10, "#555"))
    o.append(t(ax, (rows["f"] + rows["j"]) / 2 + 4, "f–j of one column = another strip", 10, "#1c7ed6"))
    return f'<svg viewBox="0 0 640 270" width="100%">{"".join(o)}</svg>'


# ---------------------------------------------------------------- parts: resistors, capacitor, switch

def resistor_figure(bands, title, sub):
    o = [f'<g transform="scale(1.6)">{resistor(10, 18, 146, 18, bands)}</g>']
    return (f'<svg viewBox="0 0 250 56" width="100%">{"".join(o)}</svg>'
            f'<div class="figcap"><b>{title}</b><br>{sub}</div>')


def cap_figure():
    o = []
    o.append('<rect x="30" y="10" width="46" height="76" rx="6" fill="#26353f"/>')
    o.append('<rect x="30" y="10" width="13" height="76" rx="4" fill="#c6ccd2"/>')
    for y in (28, 50, 72):
        o.append(f'<rect x="33" y="{y}" width="7" height="2.2" fill="#26353f"/>')
    o.append('<line x1="43" y1="86" x2="43" y2="122" stroke="#9aa0a6" stroke-width="2.4"/>')
    o.append('<line x1="64" y1="86" x2="64" y2="134" stroke="#9aa0a6" stroke-width="2.4"/>')
    o.append(t(38, 140, "−", 12, INK, "middle", "bold"))
    o.append(t(66, 148, "+", 12, INK, "middle", "bold"))
    o.append(t(53, 160, "side view", 8.5, MUTED, "middle"))
    o.append('<circle cx="150" cy="62" r="26" fill="#26353f"/>')
    o.append('<path d="M150,36 A26,26 0 0 0 150,88 Z" fill="#c6ccd2"/>')
    o.append(t(141, 66, "−", 13, INK, "middle", "bold"))
    o.append(t(161, 67, "+", 13, "#fff", "middle", "bold"))
    o.append(t(150, 110, "top view (as drawn", 8.5, MUTED, "middle"))
    o.append(t(150, 121, "on the breadboard)", 8.5, MUTED, "middle"))
    return f'<svg viewBox="0 0 200 166" width="100%">{"".join(o)}</svg>'


def switch_drawing(x, y, s=1.0, labels=True):
    """Roller microswitch; terminals C, NO, NC at x+20, x+50, x+80 (scaled), bottom at y+48*s."""
    o = [f'<g transform="translate({x},{y}) scale({s})">']
    o.append('<path d="M92,12 L18,-8" stroke="#adb5bd" stroke-width="4" stroke-linecap="round"/>')
    o.append('<circle cx="14" cy="-9" r="8" fill="#ced4da" stroke="#868e96" stroke-width="1.5"/>')
    o.append('<rect x="0" y="10" width="100" height="32" rx="4" fill="#3a3f47"/>')
    o.append('<rect x="76" y="4" width="8" height="8" fill="#e03131"/>')
    for tx, name in ((20, "C"), (50, "NO"), (80, "NC")):
        o.append(f'<rect x="{tx - 4}" y="42" width="8" height="10" fill="#d4d8dd" stroke="#868e96" stroke-width="0.8"/>')
        if labels:
            o.append(t(tx, 33, name, 9.5, "#fff", "middle", "bold"))
    o.append("</g>")
    return "".join(o)


def switch_figure():
    o = [switch_drawing(30, 26, 1.25)]
    # wires from C (x=30+25) and NC (x=30+100)
    o.append(wire([(55, 92), (55, 140)], COL["gnd"], dots=False))
    o.append(wire([(92.5, 92), (92.5, 140)], COL["home"], dots=False))
    o.append(t(48, 156, "C → GND", 10, INK, "middle", "bold"))
    o.append(t(118, 156, "NO → D2", 10, TXT["home"], "middle", "bold"))
    o.append(t(150, 114, "NC:", 9, MUTED, "middle"))
    o.append(t(150, 125, "empty", 9, MUTED, "middle"))
    return f'<svg viewBox="0 0 190 164" width="100%">{"".join(o)}</svg>'


def coil_figure():
    o = []
    leads = ["#1c7ed6", "#e03131", "#25262b", "#2f9e44"]

    def panel(x0, pair, reading, verdict, good):
        o.append(f'<rect x="{x0}" y="20" width="70" height="64" rx="7" fill="#5c636b"/>')
        o.append(f'<circle cx="{x0 + 35}" cy="52" r="13" fill="#dee2e6" stroke="#adb5bd" stroke-width="2"/>')
        o.append(t(x0 + 35, 14, "NEMA 17", 9, MUTED, "middle", "bold"))
        ends = []
        for i, c in enumerate(leads):
            x = x0 + 14 + i * 14
            o.append(f'<path d="M{x},84 L{x},130" stroke="{c}" stroke-width="3.4" fill="none"/>')
            ends.append(x)
        mx, my = x0 + 160, 52
        o.append(f'<rect x="{mx - 34}" y="{my - 40}" width="68" height="92" rx="9" fill="#f8c33c" stroke="#b48a12"/>')
        o.append(f'<rect x="{mx - 26}" y="{my - 32}" width="52" height="24" rx="3" fill="#dfe8d8" stroke="#7c8a73"/>')
        o.append(t(mx, my - 15, reading, 12, "#1d2127", "middle", "bold", 'font-family="Consolas, monospace"'))
        o.append(f'<circle cx="{mx}" cy="{my + 22}" r="13" fill="#3a3f47"/>')
        o.append(t(mx, my + 26, "Ω", 11, "#fff", "middle", "bold"))
        for k, idx in enumerate(pair):
            px = ends[idx]
            col = "#e03131" if k == 0 else "#25262b"
            o.append(f'<path d="M{px},130 C{px},150 {mx - 10 + k * 20},150 {mx - 10 + k * 20},{my + 52}" '
                     f'stroke="{col}" stroke-width="2" fill="none"/>')
            o.append(f'<circle cx="{px}" cy="130" r="3.5" fill="{col}"/>')
        o.append(t(x0 + 100, 172, verdict, 10, "#2f9e44" if good else "#c92a2a", "middle", "bold"))

    panel(10, (0, 1), "2.4 Ω", "a few ohms: same coil (a pair)", True)
    panel(290, (1, 2), "OL", "open: different coils", False)
    return f'<svg viewBox="0 0 560 180" width="100%">{"".join(o)}</svg>'


# ---------------------------------------------------------------- the big breadboard build

P = 24
X0 = 120          # x of column 1
B = 120           # top edge of the breadboard
TOP_PLUS, TOP_MINUS = B + 20, B + 44
BOT_PLUS, BOT_MINUS = B + 388, B + 412
ROW_IDX = {r: i for i, r in enumerate("abcde")}
ROW_IDX.update({r: i + 7 for i, r in enumerate("fghij")})

NANO_C0 = 2       # D12 / D13 column
TMC_C0 = 19       # DIR / GND column

TMC_TOP = ["DIR", "STEP", "CLK", "PDN", "PDN", "MS2", "MS1", "EN"]
TMC_BOT = ["GND", "VIO", "B2", "B1", "A1", "A2", "GND", "VM"]


def cx(c):
    return X0 + (c - 1) * P


def ry(r):
    return B + 84 + ROW_IDX[r] * P


def hole(h):
    """'c13' -> (x, y)."""
    return cx(int(h[1:])), ry(h[0])


def build_figure():
    o = []
    W, H = 880, 752
    left, right = cx(1) - 30, cx(30) + 30
    # board
    o.append(f'<rect x="{left}" y="{B}" width="{right - left}" height="432" rx="10" fill="#f6f1e6" stroke="#d9cfba" stroke-width="1.5"/>')
    o.append(f'<rect x="{left + 2}" y="{(ry("e") + ry("f")) / 2 - 9}" width="{right - left - 4}" height="18" fill="#e5dece"/>')
    # rail lines + labels
    for y, col in ((B + 8, "#e03131"), (B + 56, "#1c7ed6"), (B + 376, "#e03131"), (B + 424, "#1c7ed6")):
        o.append(f'<line x1="{left + 14}" y1="{y}" x2="{right - 14}" y2="{y}" stroke="{col}" stroke-width="1.3"/>')
    for y, s, col in ((TOP_PLUS, "+", "#e03131"), (TOP_MINUS, "−", "#1c7ed6"),
                      (BOT_PLUS, "+", "#e03131"), (BOT_MINUS, "−", "#1c7ed6")):
        o.append(t(left + 8, y + 4, s, 12, col, "middle", "bold"))
        o.append(t(right - 8, y + 4, s, 12, col, "middle", "bold"))
    for y, s, col in ((TOP_PLUS, "5 V (+)", "#e03131"), (TOP_MINUS, "GND (−)", "#1c7ed6"),
                      (BOT_PLUS, "5 V (+)", "#e03131"), (BOT_MINUS, "GND (−)", "#1c7ed6")):
        o.append(t(left - 6, y + 4, s, 10, col, "end", "bold"))
    # holes
    for c in range(1, 31):
        x = cx(c)
        for y in (TOP_PLUS, TOP_MINUS, BOT_PLUS, BOT_MINUS):
            o.append(f'<rect x="{x - 2.6}" y="{y - 2.6}" width="5.2" height="5.2" fill="#6b6b6b"/>')
        for r in "abcdefghij":
            o.append(f'<rect x="{x - 2.6}" y="{ry(r) - 2.6}" width="5.2" height="5.2" fill="#6b6b6b"/>')
    for c in (1, 5, 10, 15, 20, 25, 30):
        o.append(t(cx(c), B + 68, str(c), 8.5, "#8a8170", "middle"))
        o.append(t(cx(c), B + 372 - 6, str(c), 8.5, "#8a8170", "middle"))
    for r in "abcdefghij":
        o.append(t(left + 14, ry(r) + 3.5, r, 9, "#8a8170", "middle"))
        o.append(t(right - 14, ry(r) + 3.5, r, 9, "#8a8170", "middle"))

    # Nano
    o.append(nano(cx(NANO_C0), P, ry("d"), ry("h")))

    # TMC2209 (rotated a quarter turn clockwise: logic pins along the top)
    tx0, tx1 = cx(TMC_C0), cx(TMC_C0 + 7)
    o.append(f'<rect x="{tx0 - 14}" y="{ry("d") - 13}" width="{tx1 - tx0 + 28}" height="{ry("g") - ry("d") + 26}" rx="5" fill="#1e2430"/>')
    o.append(f'<rect x="{cx(TMC_C0 + 1.6)}" y="{(ry("d") + ry("g")) / 2 - 12}" width="70" height="24" rx="2" fill="#c99a2e"/>')
    o.append(t(cx(TMC_C0 + 1.6) + 35, (ry("d") + ry("g")) / 2 + 4, "TMC2209", 10, "#3b2a05", "middle", "bold"))
    pcx, pcy = cx(TMC_C0 + 6.2), (ry("d") + ry("g")) / 2
    o.append(f'<circle cx="{pcx}" cy="{pcy}" r="11" fill="#e9ecef" stroke="#adb5bd" stroke-width="1.5"/>')
    o.append(f'<path d="M{pcx - 6},{pcy} h12 M{pcx},{pcy - 6} v12" stroke="#495057" stroke-width="2.4"/>')
    tmc_ring_top = {1: COL["step"], 0: COL["dir"], 4: COL["rx"], 5: COL["gnd"], 6: COL["gnd"], 7: COL["en"]}
    tmc_ring_bot = {0: COL["gnd"], 1: COL["v5"]}
    for i in range(8):
        x = cx(TMC_C0 + i)
        for y, names, rings, ly in ((ry("d"), TMC_TOP, tmc_ring_top, ry("d") + 18),
                                     (ry("g"), TMC_BOT, tmc_ring_bot, ry("g") - 11)):
            if i in rings:
                o.append(f'<circle cx="{x}" cy="{y}" r="8.6" fill="#fff" stroke="{rings[i]}" stroke-width="2.6"/>')
            if i == 7:
                o.append(f'<rect x="{x - 5}" y="{y - 5}" width="10" height="10" fill="#e6b325" stroke="#9c7a12" stroke-width="0.8"/>')
            else:
                o.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#e6b325" stroke="#9c7a12" stroke-width="0.8"/>')
            o.append(t(x, ly, names[i], 7.4, "#e9ecef", "middle", "bold"))

    # ---- 100 uF capacitor, top view, legs in h25 (-) and h26 (+)
    ccx, ccy = (cx(25) + cx(26)) / 2, ry("h") + 12
    o.append(f'<circle cx="{ccx}" cy="{ccy}" r="17" fill="#26353f" stroke="#111" stroke-width="0.8"/>')
    o.append(f'<path d="M{ccx},{ccy - 17} A17,17 0 0 0 {ccx},{ccy + 17} Z" fill="#c6ccd2"/>')
    o.append(t(ccx - 7, ccy + 4.5, "−", 12, INK, "middle", "bold"))
    o.append(t(ccx + 7, ccy + 4.5, "+", 12, "#fff", "middle", "bold"))

    # ---- short power jumpers
    def jumper(h, y_rail, color, label, lx=None, ly=None):
        x, y = hole(h)
        o.append(wire([(x, y), (x, y_rail)], color))
        mid = (y + y_rail) / 2
        o.append(tag(lx if lx is not None else x, ly if ly is not None else mid, label, color, 8))

    jumper("a13", TOP_MINUS, COL["gnd"], "W1")
    jumper("j15", BOT_MINUS, COL["gnd"], "W2", ly=ry("j") + 33)
    jumper("j13", BOT_PLUS, COL["v5"], "W3", ly=ry("j") + 24)
    # W4 rail link at column 30
    o.append(wire([(cx(30), BOT_PLUS), (cx(30), TOP_PLUS)], COL["v5"]))
    o.append(tag(cx(30), (ry("e") + ry("f")) / 2, "W4", COL["v5"], 8))
    jumper("j19", BOT_MINUS, COL["gnd"], "W5", ly=ry("j") + 33)
    jumper("j20", BOT_PLUS, COL["v5"], "W6", ly=ry("j") + 24)
    jumper("a24", TOP_MINUS, COL["gnd"], "W7", ly=TOP_MINUS + 23)
    jumper("a25", TOP_MINUS, COL["gnd"], "W8", ly=TOP_MINUS + 23)
    # R1: 10k pull-up EN (a26) -> top 5 V rail
    x26, ya = hole("a26")
    o.append(resistor(x26, ya, x26, TOP_PLUS, R10K))
    o.append(t(x26 - 4, B - 8, "R1 10 kΩ", 9.5, INK, "end", "bold"))
    o.append(f'<path d="M{x26 - 3},{B - 11} Q{x26},{B - 11} {x26},{B - 2} L{x26},{TOP_PLUS - 6}" fill="none" stroke="#868e96" stroke-width="0.8" stroke-dasharray="2 2"/>')

    # ---- flat signal wires (lie on the board, under the arches)
    def flat(h1, h2, color, label, tag_x):
        (x1, y1), (x2, y2) = hole(h1), hole(h2)
        o.append(wire([(x1, y1), (x2, y2)], color))
        o.append(tag(tag_x, y1, label, color if color != COL["dir"] else TXT["dir"], 8.5))

    flat("c9", "c26", COL["en"], "W9  D5 → EN", cx(17.2))
    flat("b10", "b19", COL["dir"], "W10  D4 → DIR", cx(15.4))

    # ---- R2: 1k from b23 (PDN) to b27
    (rx1, ryy), (rx2, _) = hole("b23"), hole("b27")
    o.append(resistor(rx1, ryy, rx2, ryy, R1K))
    o.append(t(cx(27) + 8, ryy + 3.5, "R2 1 kΩ", 9, INK, "start", "bold",
               'stroke="#f6f1e6" stroke-width="6" stroke-linejoin="round" paint-order="stroke"'))

    # ---- arches above the board
    def arch(h1, h2, lane, color, label, tcolor=None):
        (x1, y1), (x2, y2) = hole(h1), hole(h2)
        o.append(wire([(x1, y1), (x1, lane), (x2, lane), (x2, y2)], color, r=9))
        o.append(tag((x1 + x2) / 2, lane, label, tcolor or color, 9))

    arch("a6", "a27", 26, COL["tx"], "W13  D8 → 1 kΩ (R2)")
    arch("a7", "a23", 54, COL["rx"], "W12  D7 → PDN")
    arch("a11", "a20", 82, COL["step"], "W11  D3 → STEP")

    # ---- home switch, top right; NO -> a12 (D2) along a lane between rows a and b
    ss = 0.9
    sx, sy = cx(28) - 20 * ss, 34
    o.append(switch_drawing(sx, sy, ss, labels=True))
    c_x, no_x = sx + 20 * ss, sx + 50 * ss
    sb = sy + 52 * ss
    lane = ry("a") + 11
    o.append(wire([(c_x, sb), (c_x, TOP_MINUS)], COL["gnd"], r=6))
    jog_x = (cx(29) + cx(30)) / 2
    o.append(wire([(no_x, sb), (no_x, B - 8), (jog_x, B - 8), (jog_x, lane), (cx(12), lane), (cx(12), ry("a"))],
                  COL["home"], r=6))
    o.append(tag(c_x, B - 22, "W15", COL["gnd"], 8))
    o.append(tag(cx(15.2), lane, "W14  D2 → switch NO", COL["home"], 8.5))
    o.append(t(sx + 50 * ss, sy - 18, "home switch", 10, INK, "middle", "bold"))

    # ---- USB to the Pi, camera
    usb_y = (ry("d") + ry("h")) / 2
    ux = cx(NANO_C0) - P * 2.05
    o.append(f'<path d="{rpath([(ux, usb_y), (30, usb_y), (30, 612)], 10)}" fill="none" stroke="#495057" stroke-width="6" stroke-linecap="round"/>')
    o.append(f'<rect x="8" y="612" width="150" height="58" rx="8" fill="#eef8f8" stroke="{TEAL}" stroke-width="1.5"/>')
    o.append(t(83, 637, "Raspberry Pi", 12, INK, "middle", "bold"))
    o.append(t(83, 653, "USB ports", 9.5, MUTED, "middle"))
    o.append(t(36, 596, "USB (Nano)", 9.5, "#495057", "start", "bold"))
    o.append(f'<rect x="230" y="612" width="150" height="58" rx="8" fill="#fff" stroke="#adb5bd" stroke-width="1.5"/>')
    o.append(t(305, 637, "Sony A6400", 12, INK, "middle", "bold"))
    o.append(t(305, 653, "camera", 9.5, MUTED, "middle"))
    o.append(f'<path d="M230,641 L158,641" stroke="#495057" stroke-width="6" stroke-linecap="round"/>')
    o.append(t(194, 633, "USB", 9.5, "#495057", "middle", "bold"))

    # ---- motor
    motor_cols = [(21, "#1c7ed6", "B2"), (22, "#e03131", "B1"), (23, "#25262b", "A1"), (24, "#2f9e44", "A2")]
    plug_y = 610
    for c, colr, name in motor_cols:
        x = cx(c)
        o.append(wire([(x, ry("j")), (x, plug_y)], colr, width=4))
    o.append(f'<rect x="{cx(21) - 16}" y="{plug_y - 2}" width="{3 * P + 32}" height="14" rx="2" fill="#f1f3f5" stroke="#868e96"/>')
    o.append(t(cx(21) - 22, plug_y + 9, "motor plug", 9, MUTED, "end"))
    mx = (cx(21) + cx(24)) / 2
    for i, (c, colr, name) in enumerate(motor_cols):
        x = cx(c)
        o.append(f'<path d="M{x},{plug_y + 12} C{x},{plug_y + 30} {mx - 12 + i * 8},{plug_y + 24} {mx - 12 + i * 8},{plug_y + 40}" '
                 f'fill="none" stroke="{colr}" stroke-width="3.2"/>')
    o.append(f'<rect x="{mx - 40}" y="{plug_y + 40}" width="80" height="72" rx="8" fill="#5c636b"/>')
    o.append(f'<circle cx="{mx}" cy="{plug_y + 76}" r="15" fill="#dee2e6" stroke="#adb5bd" stroke-width="2"/>')
    o.append(f'<circle cx="{mx}" cy="{plug_y + 76}" r="5" fill="#868e96"/>')
    o.append(t(mx, plug_y + 128, "NEMA 17 motor", 10.5, INK, "middle", "bold"))
    o.append(t(cx(21) - 22, plug_y + 30, "coil B", 9, MUTED, "end", "bold"))
    o.append(t(cx(24) + 22, plug_y + 30, "coil A", 9, MUTED, "start", "bold"))

    # ---- 12 V supply (leads go straight to VM / GND, never onto the rails)
    gx, vx = cx(25), cx(26)
    o.append(wire([(gx, ry("j")), (gx, 590), (790, 590), (790, 624)], "#25262b", width=6, r=8))
    o.append(wire([(vx, ry("j")), (vx, 574), (838, 574), (838, 624)], "#c92a2a", width=6, r=8))
    o.append(f'<rect x="756" y="618" width="116" height="80" rx="8" fill="#e9ecef" stroke="#868e96" stroke-width="1.5"/>')
    o.append(f'<circle cx="790" cy="632" r="7" fill="#25262b"/><circle cx="838" cy="632" r="7" fill="#e03131"/>')
    o.append(t(803, 636, "−", 11, INK, "middle", "bold"))
    o.append(t(852, 636, "+", 11, "#c92a2a", "middle", "bold"))
    o.append(f'<rect x="768" y="645" width="92" height="22" rx="3" fill="#1b4332"/>')
    o.append(t(814, 660, "12.0 V  0.50 A", 10, "#69db7c", "middle", "bold", 'font-family="Consolas, monospace"'))
    o.append(t(814, 688, "12 V supply", 9.5, INK, "middle", "bold"))
    return f'<svg viewBox="0 0 {W} {H}" width="100%">{"".join(o)}</svg>'


# ---------------------------------------------------------------- page content

def swatch(color):
    return f'<span class="sw" style="background:{color}"></span>'


def ring(color):
    return f'<span class="ring" style="border-color:{color}"></span>'


def sec(n, title):
    return f'<h1 class="sec"><span class="num">{n}</span>{esc(title)}</h1>'


LEGEND = [
    ("D2", "home switch (interrupt INT0)", COL["home"]),
    ("D3", "STEP", COL["step"]),
    ("D4", "DIR", COL["dir"]),
    ("D5", "EN (enable)", COL["en"]),
    ("D7", "UART in (direct)", COL["rx"]),
    ("D8", "UART out (through 1 kΩ)", COL["tx"]),
    ("5V", "logic power", COL["v5"]),
    ("GND", "ground (both GND pins are used)", COL["gnd"]),
]

CHECKLIST = [
    # (id, colour or None, from, to, note)
    ("W1", COL["gnd"], "a13 (Nano GND, top row)", "top GND rail", ""),
    ("W2", COL["gnd"], "j15 (Nano GND, bottom row)", "bottom GND rail", ""),
    ("W3", COL["v5"], "j13 (Nano 5V)", "bottom 5 V rail", ""),
    ("W4", COL["v5"], "bottom 5 V rail", "top 5 V rail", "column 30, links the rails"),
    ("W5", COL["gnd"], "j19 (TMC GND)", "bottom GND rail", "logic ground"),
    ("W6", COL["v5"], "j20 (TMC VIO)", "bottom 5 V rail", "logic power"),
    ("W7", COL["gnd"], "a24 (TMC MS2)", "top GND rail", "UART address 0"),
    ("W8", COL["gnd"], "a25 (TMC MS1)", "top GND rail", "UART address 0"),
    ("R1", None, "a26 (TMC EN)", "top 5 V rail", "10 kΩ pull-up"),
    ("W9", COL["en"], "c9 (D5)", "c26 (EN)", "lies flat on the board"),
    ("W10", COL["dir"], "b10 (D4)", "b19 (DIR)", "lies flat on the board"),
    ("W11", COL["step"], "a11 (D3)", "a20 (STEP)", ""),
    ("W12", COL["rx"], "a7 (D7)", "a23 (PDN)", "UART, direct"),
    ("R2", None, "b23 (PDN)", "b27", "1 kΩ"),
    ("W13", COL["tx"], "a6 (D8)", "a27", "UART, through R2"),
    ("W14", COL["home"], "switch NO", "a12 (D2)", "runs between rows a and b"),
    ("W15", COL["gnd"], "switch C", "top GND rail", "column 28; NC stays empty"),
    ("C1", None, "100 µF: − stripe in h25 (GND)", "+ in h26 (VM)", "polarity!"),
    ("U1", "#495057", "Nano USB", "Raspberry Pi", ""),
    ("U2", "#495057", "camera USB", "Raspberry Pi", ""),
]


PLACE = [
    ("P1", "Arduino Nano", "pins in rows <b>d</b> and <b>h</b>, columns <b>2–16</b>",
     "D12/D13 in column 2, USB sticking out to the left"),
    ("P2", "TMC2209", "pins in rows <b>d</b> and <b>g</b>, columns <b>19–26</b>",
     "DIR in d19, EN in d26, VM in g26; potentiometer on the right"),
]
LAST = [
    ("M1", "#1c7ed6", "motor coil B", "j21 (B2) + j22 (B1)", "12 V supply OFF"),
    ("M2", "#2f9e44", "motor coil A", "j23 (A1) + j24 (A2)", "12 V supply OFF"),
    ("V1", "#25262b", "12 V supply −", "j25 (TMC GND)", "straight to the pin, not a rail"),
    ("V2", "#c92a2a", "12 V supply +", "j26 (TMC VM)", "straight to the pin, not a rail"),
]


def checklist_html():
    rows = ['<colgroup><col style="width:6mm"><col style="width:10mm"><col style="width:7mm"><col style="width:50mm"><col style="width:5mm"><col style="width:44mm"><col></colgroup><tr class="grp"><td colspan="7">1 · Push the boards in</td></tr>']
    for pid, part, where, note in PLACE:
        rows.append(f'<tr><td class="box"></td><td class="wid">{pid}</td><td></td><td><b>{part}</b></td>'
                    f'<td class="arrow"></td><td>{where}</td><td class="note">{note}</td></tr>')
    rows.append('<tr class="grp"><td colspan="7">2 · Wires and parts</td></tr>')
    for wid, colr, a, b, note in CHECKLIST:
        if colr:
            mark = swatch(colr)
        elif wid.startswith("R"):
            mark = '<span class="sw res"></span>'
        else:
            mark = '<span class="sw cap"></span>'
        rows.append(f'<tr><td class="box"></td><td class="wid">{wid}</td><td>{mark}</td><td>{a}</td>'
                    f'<td class="arrow">→</td><td>{b}</td><td class="note">{note}</td></tr>')
    rows.append('<tr class="grp warnrow"><td colspan="7">3 · Last, with the 12 V supply OFF '
                '(during first power-up, section 7)</td></tr>')
    for wid, colr, a, b, note in LAST:
        rows.append(f'<tr><td class="box"></td><td class="wid">{wid}</td><td>{swatch(colr)}</td><td>{a}</td>'
                    f'<td class="arrow">→</td><td>{b}</td><td class="note">{note}</td></tr>')
    return ('<table class="check">' + "".join(rows) + "</table>"
            '<p class="muted" style="margin-top:3mm">Done with part 2? Hold the board next to the picture and check every wire '
            'once more against the quick reference, then continue with section 4.</p>')


def page(n, body):
    return f'<section class="page">{body}<div class="foot">MacroRail setup guide · {n}</div></section>'


def build_html():
    pages = []

    # ---------------- page 1: overview
    pages.append(page(1, f"""
<div class="kicker">MacroRail</div>
<div class="title">Hardware quick start</div>
<p class="lead">Wire the Arduino Nano, the TMC2209 driver and the stepper motor on a breadboard, then get the rail moving.</p>
{sec(1, "Overview")}
<p>The <b>Raspberry Pi</b> runs the web app. It talks to two things over USB: the <b>Sony camera</b> (to take the
pictures) and an <b>Arduino Nano</b>. The Nano does the real-time work: it sends step pulses to the
<b>TMC2209 driver</b>, which drives the <b>NEMA 17 motor</b> from a <b>12 V supply</b>, and it watches the
<b>home switch</b> so the rail always knows where zero is.</p>
<div class="fig">{overview_figure()}</div>
<h2>What's in this guide</h2>
<table class="toc">
<tr><td class="n">2</td><td><b>Meet the parts</b></td><td>The driver, the Nano, resistors, capacitor, switch, and the shopping list.</td></tr>
<tr><td class="n">3</td><td><b>Build the circuit</b></td><td>How a breadboard works, the complete wiring picture, and a numbered checklist.</td></tr>
<tr><td class="n">4</td><td><b>Before you power up</b></td><td>Coil pairs, the UART pin, the switch and the common ground.</td></tr>
<tr><td class="n">5</td><td><b>Flash &amp; install</b></td><td>Firmware onto the Nano, app onto the Pi.</td></tr>
<tr><td class="n">6</td><td><b>Camera</b></td><td>A6400 settings.</td></tr>
<tr><td class="n">7</td><td><b>First power-up checks</b></td><td>Driver, switch, direction, homing, travel.</td></tr>
</table>
<div class="callout warn"><b>The one rule that protects the driver</b><br>
Never plug or unplug the motor while the 12 V supply is on. That can destroy the TMC2209.</div>
"""))

    # ---------------- page 2: TMC2209
    pages.append(page(2, f"""
{sec(2, "Meet the parts")}
<h2 class="first">The TMC2209 driver</h2>
<p>The driver turns small logic signals from the Nano into the strong currents that move the motor. It has two sides:
the <b>logic side</b> talks to the Nano, and the <b>power side</b> connects to the motor and the 12 V supply.</p>
<div class="fig">{tmc_figure()}</div>
<p class="cap">The usual TMC2209 layout (BIGTREETECH V1.2/V1.3 and most clones). Check the labels printed on your board's underside.</p>
<div class="two">
  <div>
    <div class="fig small">{tmc_side_figure()}</div>
    <p class="cap">Pins go into the breadboard; the potentiometer faces up.</p>
  </div>
  <div>
    <h3>Check your board now</h3>
    <ul class="boxes">
      <li>Flip it over and find the labels printed next to the pins.</li>
      <li>Compare them with the picture: EN, MS1, MS2, PDN, PDN, CLK, STEP, DIR on one side; VM, GND, A2, A1, B1, B2, VDD/VIO, GND on the other.</li>
      <li>Find the <b>UART pin</b>: labelled PDN, PDN_UART or UART. On some BTT modules you must bridge a solder jumper to bring it out to the header pin.</li>
      <li>Names may differ: <i>OA1/OA2</i> or <i>1A/1B</i> instead of A1/A2, <i>VIO</i> or <i>VCC</i> instead of VDD.</li>
    </ul>
    <p><b>The potentiometer</b> (the little screw, VREF) sets current the old-fashioned way. MacroRail sets current over UART from the web app, so <b>leave it alone</b>.</p>
    <p><b>Sense resistor:</b> usually 0.11 Ω (marked R100 or R110). If yours differs, change <code>DRIVER_RSENSE_OHM</code> in <code>firmware/src/config.h</code>.</p>
    <p><b>Heatsink?</b> Stick it on the cooling pad on top. It must not touch any pins.</p>
  </div>
</div>
"""))

    # ---------------- page 3: Nano, resistors, capacitor
    legend = "".join(f'<li>{ring(c)}<b>{p}</b><span>{d}</span></li>' for p, d, c in LEGEND)
    pages.append(page(3, f"""
<h2 class="first">The Arduino Nano</h2>
<div class="nano-row">
  <div class="fig">{nano_figure()}<p class="cap">Shown the way it sits on the breadboard: USB on the left.</p></div>
  <div class="legend"><div class="lh">Pins this project uses</div><ul>{legend}</ul></div>
</div>
<p>MacroRail uses six signal pins (D2–D5, D7, D8), plus 5V and both GND pins. The pin names are printed on the Nano next to each pin. D2 is the hardware-interrupt pin, so the home switch stops the motor the instant it closes. D6 is unused and D9 stays free for a future shutter-cable relay. A CH340 clone is fine; it is powered by the Pi's USB.</p>
<p>The same colours are used for every wire in this guide, so you can match picture, checklist and board at a glance.</p>

<h2>The resistors and the capacitor</h2>
<div class="three">
  <div>{resistor_figure(R1K, "1 kΩ (R2): brown · black · red · gold",
                         "5-band: brown · black · black · brown · brown<br>UART: D8 talks through it")}</div>
  <div>{resistor_figure(R10K, "10 kΩ (R1): brown · black · orange · gold",
                         "5-band: brown · black · black · red · brown<br>EN pull-up: keeps the motor off while the Nano boots")}</div>
</div>
<p class="cap" style="text-align:left;margin-top:0">Resistors have no direction. Not sure about the colours? Measure: a multimeter on Ω reads about 1.0 k or 10 k.</p>
<div class="two cap-row">
  <div class="fig capfig">{cap_figure()}</div>
  <div>
    <h3>100 µF electrolytic capacitor (C1)</h3>
    <p><b>Stripe side = minus (−)</b>, <b>longer leg = plus (+)</b>.<br>
    It goes across VM and GND right next to the driver and soaks up voltage spikes from the motor.</p>
    <p class="red">Backwards it can pop, so check twice: − to GND, + to VM.</p>
    <p>Rating: 25 V or higher.</p>
  </div>
</div>
<h2>The home switch</h2>
<div class="two sw-row">
  <div class="fig swfig">{switch_figure()}</div>
  <div>
    <p>A roller microswitch has three terminals: <b>C</b> (common), <b>NO</b> (normally open) and <b>NC</b> (normally closed).
    Wire <b>C and NO</b>: the switch closes when pressed and pulls D2 to GND. NC stays empty.</p>
    <p>D2 is the Nano's hardware-interrupt pin (INT0), so the firmware stops any motion <b>the instant the switch
    closes</b>, in either direction.</p>
    <p class="muted">If you ever rewire it NC, set <code>ENDSTOP_ACTIVE_LEVEL</code> to <code>HIGH</code> in <code>firmware/src/config.h</code>.</p>
  </div>
</div>

"""))

    # ---------------- page 4: switch, motor, parts list
    pages.append(page(4, f"""
<h2 class="first">The motor</h2>
<p>The NEMA 17 (from the Anet A8) has 4 wires: two coils. With a multimeter on Ω, the two wires of one coil read a few
ohms; wires from different coils read open. One pair goes to A1/A2, the other to B1/B2. Wire colours vary between motors,
so measure rather than trust them.</p>
<div class="fig" style="width:82%;margin:3mm auto 1mm">{coil_figure()}</div>
<p class="cap">Multimeter on Ω: touch two wires at a time until you find the two pairs. Mark them (tape, a pen) before wiring.</p>

<h2>What you need</h2>
<table class="parts">
<tr><th>Part</th><th>Notes</th></tr>
<tr><td>Arduino Nano (CH340 clone is fine)</td><td>USB to the Pi, which also powers it.</td></tr>
<tr><td>TMC2209 module (BTT / FYSETC style)</td><td>Must expose the PDN_UART pin. Sense resistor usually 0.11 Ω (R100/R110).</td></tr>
<tr><td>NEMA 17 stepper (from the Anet A8)</td><td>4 wires = two coils.</td></tr>
<tr><td>12 V supply</td><td>Powers the motor (VM) only. Its ground is shared with the Nano's.</td></tr>
<tr><td>Roller microswitch</td><td>Wired C + NO, to D2.</td></tr>
<tr><td>Resistors: 1 kΩ and 10 kΩ</td><td>UART (R2) and EN pull-up (R1).</td></tr>
<tr><td>Capacitor: 100 µF, 25 V or more</td><td>Across VM and GND at the driver (C1).</td></tr>
<tr><td>Breadboard + jumper wires</td><td>Half-size (30 columns) is enough. Male-male jumpers in several colours.</td></tr>
<tr><td>Raspberry Pi + proper 5.1 V / 2.5 A supply</td><td>The Pi powers the Nano and the camera's USB link. Under-voltage causes USB drop-outs.</td></tr>
<tr><td>Sony A6400 + USB cable</td><td>Plugs into the Pi.</td></tr>
<tr><td>Multimeter</td><td>For coil pairs and the checks in section 4.</td></tr>
</table>
"""))

    # ---------------- page 5: breadboard explainer
    pages.append(page(5, f"""
{sec(3, "Build the circuit")}
<h2 class="first">The breadboard</h2>
<p>Inside a breadboard, metal strips join certain holes together. Knowing which holes are joined is the whole trick:</p>
<div class="fig">{breadboard_explainer()}</div>
<p class="cap">Each column has two separate 5-hole strips, one above and one below the gap. The rails run the full length.</p>
<ul>
<li>Columns are numbered (1–30) and rows are lettered (a–j). A hole is named like <code>c13</code>: row c, column 13.</li>
<li>Two parts are connected when their legs are in the <b>same strip</b>.</li>
<li>Chips straddle the gap so that each pin gets its own strip.</li>
<li>Follow your board's <b style="color:#e03131">red +</b> and <b style="color:#1c7ed6">blue −</b> markings for the rails;
their order varies between brands. On a full-size board, long rails are sometimes split in the middle (a break in the
red/blue line). This build only uses columns 1–30, so it stays on one side of the split.</li>
</ul>
<h2>How to read the wiring picture</h2>
<ul>
<li>Every wire has a tag like <span class="inl" style="border-color:{COL['rx']};color:{COL['rx']}">W12 D7 → PDN</span>: its number in the checklist, where it starts and where it ends.</li>
<li>Most signal wires arch <b>above</b> the board so they don't cross. W9 and W10 lie flat on the board in rows c and b, and the switch lead W14 runs flat between rows a and b, underneath the arches.</li>
<li>Wire colours don't matter electrically, but using the same colours as the pictures makes checking much easier:
<b>black = ground</b>, <b style="color:#e03131">red = 5 V</b>, and one colour per signal.</li>
<li>The 12 V leads go <b>straight</b> to the driver's VM and GND pins. They never touch the rails, which carry 5 V for the Nano.</li>
</ul>
<div class="callout red"><b>Before you start building</b><br>USB unplugged, 12 V supply off and disconnected.</div>
"""))

    # ---------------- page 6: complete build
    pages.append(page(6, f"""
<h2 class="first">The complete build</h2>
<div class="fig">{build_figure()}</div>
<p class="cap">Complete wiring. The motor and the 12 V leads go on last, with the supply off (section 7).
The TMC2209 is the same board as in section 2, turned a quarter-turn clockwise: logic pins along the top, power pins along the bottom.</p>
<h2>Quick reference</h2>
<table class="parts qr">
<tr><th>Nano</th><th>Goes to</th><th>Why</th></tr>
<tr><td>{swatch(COL['home'])}D2</td><td>Switch NO (switch C → GND)</td><td>Closes (LOW) when pressed. Interrupt pin: motion stops instantly.</td></tr>
<tr><td>{swatch(COL['step'])}D3</td><td>TMC STEP</td><td>One pulse = one 1/16 microstep = 2.5 µm.</td></tr>
<tr><td>{swatch(COL['dir'])}D4</td><td>TMC DIR</td><td>Positive = away from the switch.</td></tr>
<tr><td>{swatch(COL['en'])}D5</td><td>TMC EN, plus 10 kΩ to 5 V</td><td>Low = motor on. The pull-up keeps the motor off while the Nano boots or is unplugged.</td></tr>
<tr><td>{swatch(COL['rx'])}D7</td><td>TMC PDN_UART, direct</td><td>UART receive.</td></tr>
<tr><td>{swatch(COL['tx'])}D8</td><td>TMC PDN_UART through 1 kΩ</td><td>UART transmit. Single-wire UART needs this resistor.</td></tr>
<tr><td>{swatch(COL['v5'])}5V / {swatch(COL['gnd'])}GND</td><td>TMC VIO / GND</td><td>Logic supply and common ground.</td></tr>
<tr><td>—</td><td>TMC MS1, MS2 → GND</td><td>UART address 0.</td></tr>
<tr><td>—</td><td>12 V → VM, 12 V − → GND</td><td>Motor power. 100 µF across VM–GND at the module.</td></tr>
<tr><td>D9</td><td>nothing yet</td><td>Reserved for the shutter-cable relay.</td></tr>
</table>
"""))

    # ---------------- page 7: checklist + quick reference
    pages.append(page(7, f"""
<h2 class="first">Wire it in this order</h2>
<p>Tick off one line at a time and compare with the picture on the previous page. “Top rails” are above row a,
“bottom rails” below row j. Holes are named row + column, like <code>c13</code>.</p>
{checklist_html()}


"""))

    # ---------------- page 8: before power up + flash/install
    pages.append(page(8, f"""
{sec(4, "Before you power up")}
<ul class="boxes">
<li><b>Coil pairs found.</b> Few ohms between the two wires of a pair, open between pairs. One pair on A1/A2, the other on B1/B2.</li>
<li><b>UART pin right.</b> W12 and R2 land on the PDN pin marked <i>use this one</i> (PDN / PDN_UART / UART), solder jumper bridged if your module needs it.</li>
<li><b>Switch on C + NO</b> (closes when pressed): C to the GND rail, NO to D2, NC empty. The firmware stops any motion
the instant the switch closes, in either direction. If you ever rewire it NC, set <code>ENDSTOP_ACTIVE_LEVEL</code> to
<code>HIGH</code> in <code>firmware/src/config.h</code>.</li>
<li><b>Motor direction</b> is set by <code>INVERT_DIRECTION</code> in <code>firmware/src/config.h</code>, already set for this rail.</li>
<li><b>Common ground.</b> 12 V −, TMC GND and Nano GND must all connect. The TMC's two GND pins are joined on the module:
a multimeter on beep between j25 and the bottom GND rail should beep.</li>
<li><b>No short.</b> Between the 5 V rail and the GND rail the multimeter must <b>not</b> beep.</li>
<li><b>C1 the right way round:</b> stripe (−) in h25, + in h26.</li>
</ul>
<div class="callout warn slim">Never plug or unplug the motor while 12 V is on. Ignore the VREF potentiometer: current is set
over UART from the web app (Settings → Motor current).</div>

{sec(5, "Flash & install")}
<h2 class="first">Flash the Nano</h2>
<p>Once the app is installed (below), plug the Nano into the Pi and flash it there. Stop the app
first, because it owns the serial port:</p>
<pre>uv tool install platformio
sudo systemctl stop macrorail
pio run -d ~/macrorail/firmware -e nano -t upload</pre>
<p>Or flash from any computer with PlatformIO: <code>pio run -d firmware -e nano -t upload</code>.</p>
<p class="muted">Use <code>-e nano_new</code> if the upload fails with a genuine or new-bootloader Nano.</p>
<h2>Install the app on the Pi</h2>
<p>On the Pi, clone the repository and run the install script (it asks for your sudo password):</p>
<pre>git clone https://github.com/Sam-de-Ham/MacroRail.git ~/macrorail
~/macrorail/deploy/install.sh</pre>
<p>Then find the Nano's port and put it in the config if it differs from the default:</p>
<pre>ls /dev/serial/by-id/
nano ~/.config/macrorail/config.toml    # [rail] port = "/dev/serial/by-id/..."
sudo systemctl restart macrorail</pre>
<p>Open <b>http://pi.local:8000</b> on your phone or laptop. Logs: <code>journalctl -u macrorail -f</code>.
Autostart off: <code>sudo systemctl disable --now macrorail</code>.</p>
"""))

    # ---------------- page 9: camera + first power-up
    pages.append(page(9, f"""
{sec(6, "Camera")}
<h2 class="first">Sony A6400 settings</h2>
<ul>
<li>Menu → USB Connection: <b>PC Remote</b>. Still Img. Save Dest.: <b>Camera Only</b> (images stay on the card).</li>
<li><b>Manual focus, manual exposure.</b> Silent shooting (electronic shutter) avoids shutter shock.</li>
<li>Turn <b>auto power-off off</b>; use a dummy battery or a full one for long stacks.</li>
<li>Connect the camera's USB to the Pi. The camera pill in the app turns green.</li>
</ul>

{sec(7, "First power-up checks")}
<ol class="steps">
<li><b>Motor unplugged</b>, 12 V on, Nano on the Pi. The rail pill shows <i>Not homed</i>.
<span class="muted"><i>No driver power</i> means the TMC isn't answering: check 12 V, the PDN_UART wiring (W12, W13, R2) and MS1/MS2 (W7, W8).
The TMC2209 only answers on UART when VM has power.</span></li>
<li><b>Switch:</b> press it by hand. The Position card shows <i>Home switch pressed</i> immediately.</li>
<li><b>12 V off</b>, plug in the motor, 12 V on. Jog <b>Away</b> 1 mm: the carriage must move <b>away from the switch</b>.
If it moves toward it, swap the two wires of one coil (12 V off!) or flip <code>INVERT_DIRECTION</code> in
<code>firmware/src/config.h</code> and reflash.</li>
<li><b>Home.</b> The rail seeks the switch at 1 mm/s and stops the instant it closes. It backs off until the switch
opens again, plus 0.5 mm, then re-approaches very slowly (0.2 mm/s: it looks almost stationary for a few seconds) and
parks just clear of the switch. The activity log shows how far your switch travels between closing and opening. Keep a
finger near the 12 V switch the first time.</li>
<li><b>Measure travel.</b> Jog to the far end of the usable travel and note the position: that becomes
<code>travel_mm</code> in the config (default 140).</li>
</ol>
<div class="callout teal"><b>Then:</b> set a start and end on the live view, preview the range, and run a short test stack.<br>
<span class="muted">Defaults: 600 mA run / 200 mA hold, 2 mm/s travel, 0.8 s settle, 10 µm step.</span></div>
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
pre { background: #f3f5f7; border-left: 3px solid #0f8a8a; padding: 2.2mm 3.5mm; margin: 1mm 0 3mm; font-size: 9.4pt;
      white-space: pre-wrap; }
.fig { margin: 2mm 0 1mm; }
.fig svg { display: block; }
.cap { text-align: center; color: #6b7280; font-size: 8.8pt; margin: 1mm 0 3mm; }
.muted { color: #6b7280; }
.red { color: #c92a2a; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 7mm; align-items: start; }
.three { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; }
.three { margin-bottom: 3mm; }
.figcap { text-align: center; font-size: 9pt; color: #6b7280; line-height: 1.35; }
.figcap b { color: #1d2127; }
.callout { border-radius: 6px; padding: 3mm 4mm; margin: 4mm 0 3mm; border-left: 4px solid; }
.callout.red { background: #fdf1f1; border-color: #c92a2a; color: #1d2127; }
.callout.warn { background: #fff4e6; border-color: #e8590c; }
.callout.teal { background: #eef8f8; border-color: #0f8a8a; }
.callout.slim { padding: 2.2mm 3.5mm; margin: 3mm 0; }
ul.boxes { list-style: none; padding-left: 0; }
ul.boxes li { position: relative; padding-left: 7mm; margin-bottom: 2mm; }
ul.boxes li::before { content: ""; position: absolute; left: 0; top: 1.2mm; width: 3.4mm; height: 3.4mm;
                      border: 1.4px solid #1d2127; border-radius: 2px; }
table { border-collapse: collapse; width: 100%; }
table.toc td { padding: 1.3mm 2mm; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
table.toc td.n { width: 7mm; color: #fff; }
table.toc td:nth-child(2) { white-space: nowrap; width: 44mm; }
table.toc td.n { background: #0f8a8a; text-align: center; font-weight: 700; border-bottom: 2px solid #fff; border-radius: 4px; }
table.parts th { text-align: left; background: #f1f3f5; border-bottom: 1.4px solid #1d2127; padding: 1.5mm 2mm; font-size: 9.6pt; }
table.parts td { border-bottom: 1px solid #e5e7eb; padding: 1.4mm 2mm; vertical-align: top; font-size: 9.6pt; }
table.parts td:first-child { white-space: nowrap; }
table.qr td:first-child { font-weight: 700; }
table.qr td:nth-child(2) { white-space: nowrap; }
table.qr td { padding: 0.9mm 2mm; font-size: 9.3pt; }
.sw { display: inline-block; width: 16px; height: 6px; border-radius: 3px; margin-right: 5px; vertical-align: middle;
      box-shadow: 0 0 0 1px rgba(0,0,0,.35); }
.sw.res { background: linear-gradient(90deg, #e9d3a6 0 30%, #7b4a1e 30% 42%, #e9d3a6 42% 58%, #111 58% 70%, #e9d3a6 70%); height: 8px; }
.sw.cap { background: linear-gradient(90deg, #c6ccd2 0 35%, #26353f 35%); height: 9px; width: 12px; border-radius: 4px; }
.ring { display: inline-block; width: 10px; height: 10px; border-radius: 50%; border: 3px solid; margin-right: 7px;
        vertical-align: middle; }
.nano-row { display: grid; grid-template-columns: 1.55fr 1fr; gap: 5mm; align-items: center; }
.legend .lh { font-weight: 700; font-size: 9.5pt; margin-bottom: 1.5mm; }
.legend ul { list-style: none; padding: 0; margin: 0; }
.legend li { font-size: 9.2pt; margin-bottom: 1.3mm; display: flex; align-items: center; }
.legend li b { width: 9mm; flex: none; }
.legend li span { color: #6b7280; }
.cap-row { grid-template-columns: 50mm 1fr; margin-top: 3mm; }
.sw-row { grid-template-columns: 55mm 1fr; }
.inl { border: 1.3px solid; border-radius: 9px; padding: 0 6px; font-weight: 700; font-size: 8.6pt; white-space: nowrap; }
table.check tr.grp td { font-weight: 700; color: #0f8a8a; padding-top: 3mm; border-bottom: 1.4px solid #0f8a8a; }
table.check tr.warnrow td { color: #e8590c; border-bottom-color: #e8590c; }
table.check td { padding: 0.9mm 1.6mm; border-bottom: 1px solid #e5e7eb; font-size: 9.6pt; vertical-align: middle; }
table.check td.box { width: 4mm; }
table.check td.box::before { content: ""; display: inline-block; width: 3.4mm; height: 3.4mm; border: 1.4px solid #1d2127;
                             border-radius: 2px; vertical-align: middle; }
table.check { table-layout: fixed; }
table.check td.wid { font-weight: 700; width: 10mm; }
table.check td:nth-child(3) { width: 7mm; }
table.check td:nth-child(4) { width: 50mm; }
table.check td:nth-child(6) { width: 44mm; }
table.check td.arrow { color: #9aa0a6; width: 4mm; }
table.check td.note { color: #6b7280; font-size: 8.8pt; }
.place { margin-top: 2mm; }
.place h3 { color: #0f8a8a; }
ol.steps { padding-left: 6mm; }
ol.steps li { margin-bottom: 2.4mm; }
"""


def main():
    pages = build_html()
    doc = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
           "<title>MacroRail hardware quick start</title>"
           f"<style>{CSS}</style></head><body>{''.join(pages)}</body></html>")
    with open(os.path.join(HERE, "setup-guide.html"), "w", encoding="utf-8") as f:
        f.write(doc)


if __name__ == "__main__":
    main()
