"""Builds the MacroRail guides as A4 PDFs.

    uv run python docs/guides/build.py           # both guides
    uv run python docs/guides/build.py rail      # MacroRail-build-guide.pdf only
    uv run python docs/guides/build.py module    # MacroRail-scan-module-guide.pdf only

The text of each guide is in `rail.html` and `module.html` next to this file, and the look in
`style.css`. This script adds the section numbers, the contents, the wiring drawings (SVG) and
the wire tables, copies the pictures into `build/` at print size, writes `build/<guide>.html`
and prints it with headless Edge or Chrome. It prints twice: the first PDF shows on which page
each section starts, for the contents. That step needs `pdftotext` (poppler); without it the
contents are printed without page numbers.

In the sources, `{{name}}` inserts the drawing or table that `PARTS[name]` returns. Pictures are
`<img src="img/...">` or `<img src="../images/...">` (relative to this folder), and app
screenshots `<img src="shot:<name>">`, cropped as listed in `SHOTS`.
"""

from __future__ import annotations

import html
import math
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
APP_SHOTS = HERE.parent / "images" / "app"


@dataclass(frozen=True)
class Guide:
    source: str
    pdf: str
    footer: str


GUIDES = {
    "rail": Guide("rail.html", "MacroRail-build-guide.pdf", "MacroRail build guide"),
    "module": Guide(
        "module.html", "MacroRail-scan-module-guide.pdf", "MacroRail scan module guide"
    ),
}

# App screenshots (1440 x 960): crop box (left, top, right, bottom) of the part that matters.
SHOTS = {
    "shoot": ("shoot.png", (816, 78, 1324, 960)),
    "camera": ("camera.png", (816, 78, 1324, 700)),
    "review": ("review.png", (816, 78, 1324, 960)),
    "depth": ("depth.png", (816, 78, 1324, 960)),
    "rig": ("rig.png", (816, 78, 1324, 960)),
    "centre": ("centre.png", (816, 78, 1324, 960)),
    "scan": ("scan.png", (816, 78, 1324, 960)),
    "scan-review": ("scan-review.png", (816, 78, 1324, 700)),
}

MAX_IMAGE_PX = 1500

INK = "#1b1d20"
MUTED = "#5d636b"
ACCENT = "#1d5c80"
WARN = "#9a3412"

# ------------------------------------------------------------------------------------------
# SVG helpers. Text is written by this script, so it is inserted as is: use entities
# (&minus; &times; &rarr; &Omega; &micro;) for anything beyond ASCII.


def vlen(s: str) -> int:
    """Visible length of a text with entities."""
    return len(re.sub(r"&#?\w+;", "x", s))


def t(
    x: float,
    y: float,
    s: str,
    size: float = 10,
    fill: str = INK,
    anchor: str = "start",
    weight: str = "normal",
    extra: str = "",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}" {extra}>{s}</text>'
    )


def rpath(pts: list[tuple[float, float]], r: float = 7) -> str:
    """A polyline with rounded corners."""

    def toward(ax: float, ay: float, bx: float, by: float, dist: float) -> tuple[float, float]:
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy) or 1
        dist = min(dist, ln / 2)
        return ax + dx / ln * dist, ay + dy / ln * dist

    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        ax, ay = toward(x1, y1, x0, y0, r)
        bx, by = toward(x1, y1, x2, y2, r)
        d += f" L{ax:.1f},{ay:.1f} Q{x1:.1f},{y1:.1f} {bx:.1f},{by:.1f}"
    return d + f" L{pts[-1][0]:.1f},{pts[-1][1]:.1f}"


def wire(
    pts: list[tuple[float, float]],
    color: str,
    width: float = 4.2,
    dots: bool = True,
    r: float = 7,
) -> str:
    d = rpath(pts, r)
    out = (
        f'<path d="{d}" fill="none" stroke="#000" stroke-opacity="0.3" '
        f'stroke-width="{width + 2}" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
    )
    if dots:
        for x, y in (pts[0], pts[-1]):
            out += (
                f'<circle cx="{x}" cy="{y}" r="4" fill="{color}" stroke="#111" stroke-width="1"/>'
            )
    return out


def tag(x: float, y: float, s: str, color: str, size: float = 9) -> str:
    """A wire label: white pill with a coloured outline."""
    w = vlen(s) * size * 0.56 + 10
    h = size + 5
    return (
        f'<rect x="{x - w / 2:.1f}" y="{y - h / 2:.1f}" width="{w:.1f}" height="{h}" '
        f'rx="{h / 2}" fill="#fff" stroke="{color}" stroke-width="1.3"/>'
        + t(x, y + size * 0.36, s, size, color, "middle", "bold")
    )


def svg(view: str, body: str | list[str]) -> str:
    content = body if isinstance(body, str) else "".join(body)
    return f'<svg viewBox="{view}" xmlns="http://www.w3.org/2000/svg">{content}</svg>'


def arrow_defs(colors: list[str]) -> str:
    return (
        "<defs>"
        + "".join(
            f'<marker id="arr-{c[1:]}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" '
            f'markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
            f'fill="{c}"/></marker>'
            for c in colors
        )
        + "</defs>"
    )


class Blocks:
    """Boxes and arrows for the block diagrams."""

    def __init__(self, colors: list[str]) -> None:
        self.o = [arrow_defs(colors)]

    def box(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        title: str,
        sub: str | None = None,
        fill: str = "#fff",
        stroke: str = "#b9c0c8",
        dashed: bool = False,
    ) -> None:
        dash = ' stroke-dasharray="5 3"' if dashed else ""
        self.o.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.3"{dash}/>'
        )
        ty = y + h / 2 + (4 if not sub else -2)
        self.o.append(t(x + w / 2, ty, title, 11, INK, "middle", "bold"))
        if sub:
            self.o.append(t(x + w / 2, y + h / 2 + 12, sub, 8.6, MUTED, "middle"))

    def link(
        self,
        pts: list[tuple[float, float]],
        color: str,
        label: str | None = None,
        at: tuple[float, float] = (0, 0),
        anchor: str = "middle",
        arrow: bool = True,
        both: bool = False,
    ) -> None:
        end = f' marker-end="url(#arr-{color[1:]})"' if arrow else ""
        start = f' marker-start="url(#arr-{color[1:]})"' if both else ""
        self.o.append(
            f'<path d="{rpath(pts, 6)}" fill="none" stroke="{color}" '
            f'stroke-width="2.2"{end}{start}/>'
        )
        if label:
            self.o.append(t(at[0], at[1], label, 9, color, anchor, "bold"))

    def note(self, x: float, y: float, s: str) -> None:
        self.o.append(t(x, y, s, 8.5, MUTED, "middle"))

    def svg(self, view: str) -> str:
        return svg(view, self.o)


# ------------------------------------------------------------------------------------------
# Parts drawn in several figures

BAND = {"brown": "#7b4a1e", "black": "#111", "red": "#d22", "orange": "#f08c00", "gold": "#c9a227"}
R1K = [BAND["brown"], BAND["black"], BAND["red"], BAND["gold"]]
R10K = [BAND["brown"], BAND["black"], BAND["orange"], BAND["gold"]]

NANO_TOP = [
    "D12",
    "D11",
    "D10",
    "D9",
    "D8",
    "D7",
    "D6",
    "D5",
    "D4",
    "D3",
    "D2",
    "GND",
    "RST",
    "RX0",
    "TX1",
]
NANO_BOT = [
    "D13",
    "3V3",
    "REF",
    "A0",
    "A1",
    "A2",
    "A3",
    "A4",
    "A5",
    "A6",
    "A7",
    "5V",
    "RST",
    "GND",
    "VIN",
]


def resistor(x1: float, y1: float, x2: float, y2: float, bands: list[str]) -> str:
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
    bl = min(36, math.hypot(x2 - x1, y2 - y1) - 10)
    out = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9aa0a6" stroke-width="2"/>'
    for x, y in ((x1, y1), (x2, y2)):
        out += f'<circle cx="{x}" cy="{y}" r="3" fill="#9aa0a6"/>'
    out += f'<g transform="translate({cx:.1f},{cy:.1f}) rotate({ang:.1f})">'
    out += (
        f'<rect x="{-bl / 2}" y="-6" width="{bl}" height="12" rx="5" fill="#e9d3a6" '
        f'stroke="#a88b55" stroke-width="0.8"/>'
    )
    for i, c in enumerate(bands):
        bx = -bl / 2 + 6 + i * 5 if i < len(bands) - 1 else bl / 2 - 7
        out += f'<rect x="{bx:.1f}" y="-6" width="3" height="12" fill="{c}"/>'
    return out + "</g>"


def nano(
    x0: float,
    pitch: float,
    ytop: float,
    ybot: float,
    rings_top: dict[int, str],
    rings_bot: dict[int, str],
    name: str = "NANO",
) -> str:
    """Arduino Nano from above, USB on the left. x0 is the x of the D12/D13 pins."""
    x1 = x0 + 14 * pitch
    my = (ytop + ybot) / 2
    out = [
        f'<rect x="{x0 - pitch * 2.05:.1f}" y="{my - 21}" width="{pitch * 1.9:.1f}" height="42" '
        f'rx="3" fill="#c9ced6" stroke="#8a9099" stroke-width="1"/>',
        t(x0 - pitch * 1.15, my + 3.5, "USB", 9.5, "#333", "middle", "bold"),
        f'<rect x="{x0 - pitch * 0.62:.1f}" y="{ytop - 15}" width="{x1 - x0 + pitch * 1.24:.1f}" '
        f'height="{ybot - ytop + 30}" rx="5" fill="#1f5fa8" stroke="#163f73" stroke-width="1.2"/>',
        f'<rect x="-15" y="-15" width="30" height="30" fill="#1b1f24" '
        f'transform="translate({x0 + pitch * 7.6:.1f},{my:.1f}) rotate(45)"/>',
        t(x0 + pitch * 11.6, my + 4.5, name, 13, "#fff", "middle", "bold"),
    ]
    for names, rings, y, top in (
        (NANO_TOP, rings_top, ytop, True),
        (NANO_BOT, rings_bot, ybot, False),
    ):
        for i, pin in enumerate(names):
            x = x0 + i * pitch
            used = i in rings
            if used:
                out.append(
                    f'<circle cx="{x}" cy="{y}" r="9" fill="#fff" stroke="{rings[i]}" '
                    f'stroke-width="3"/>'
                )
            out.append(
                f'<circle cx="{x}" cy="{y}" r="5" fill="#e6b325" stroke="#9c7a12" '
                f'stroke-width="0.8"/>'
            )
            ly = y + 13 if top else y - 13
            anchor = "end" if top else "start"
            fill = "#fff" if used else "#c9dcf2"
            out.append(
                f'<text x="{x + 3.3:.1f}" y="{ly:.1f}" font-size="{8.2 if used else 7.6}" '
                f'fill="{fill}" font-weight="{"bold" if used else "normal"}" '
                f'text-anchor="{anchor}" transform="rotate(-90 {x + 3.3:.1f} '
                f'{ly:.1f})">{pin}</text>'
            )
    return "".join(out)


def switch_drawing(
    x: float,
    y: float,
    s: float = 1.0,
    order: tuple[str, str, str] = ("C", "NO", "NC"),
    roller_left: bool = True,
) -> str:
    """Roller microswitch; terminals at x+20s, x+50s, x+80s; their ends at y+52s."""
    o = [f'<g transform="translate({x},{y}) scale({s})">']
    if roller_left:
        o.append(
            '<path d="M92,12 L18,-8" stroke="#adb5bd" stroke-width="4" stroke-linecap="round"/>'
        )
        o.append(
            '<circle cx="14" cy="-9" r="8" fill="#ced4da" stroke="#868e96" stroke-width="1.5"/>'
        )
    else:
        o.append(
            '<path d="M8,12 L82,-8" stroke="#adb5bd" stroke-width="4" stroke-linecap="round"/>'
        )
        o.append(
            '<circle cx="86" cy="-9" r="8" fill="#ced4da" stroke="#868e96" stroke-width="1.5"/>'
        )
    o.append('<rect x="0" y="10" width="100" height="32" rx="4" fill="#3a3f47"/>')
    for tx, name in zip((20, 50, 80), order, strict=True):
        o.append(
            f'<rect x="{tx - 4}" y="42" width="8" height="10" fill="#d4d8dd" stroke="#868e96" '
            f'stroke-width="0.8"/>'
        )
        o.append(t(tx, 33, name, 9.5, "#fff", "middle", "bold"))
    o.append("</g>")
    return "".join(o)


def switch_figure(pin: str, color: str) -> str:
    o = [switch_drawing(30, 26, 1.25)]
    o.append(wire([(55, 92), (55, 140)], "#25262b", dots=False))
    o.append(wire([(92.5, 92), (92.5, 140)], color, dots=False))
    o.append(t(48, 156, "C &rarr; GND", 10, INK, "middle", "bold"))
    o.append(t(120, 156, f"NO &rarr; {pin}", 10, color, "middle", "bold"))
    o.append(t(150, 112, "NC:", 9, MUTED, "middle"))
    o.append(t(150, 123, "empty", 9, MUTED, "middle"))
    return svg("0 0 190 164", o)


# ------------------------------------------------------------------------------------------
# Rail electronics

RAIL = {
    "step": "#f08c00",
    "dir": "#d4a300",
    "en": "#7c3aed",
    "home": "#e64980",
    "rx": "#2f9e44",
    "tx": "#1c7ed6",
    "v5": "#e03131",
    "gnd": "#25262b",
}
RAIL_TEXT = dict(RAIL, dir="#9a7600")  # darker yellow for text

RAIL_RINGS_TOP = {
    4: RAIL["tx"],
    5: RAIL["rx"],
    7: RAIL["en"],
    8: RAIL["dir"],
    9: RAIL["step"],
    10: RAIL["home"],
    11: RAIL["gnd"],
}
RAIL_RINGS_BOT = {11: RAIL["v5"], 13: RAIL["gnd"]}


def rail_overview() -> str:
    b = Blocks(["#495057", RAIL["step"], RAIL["rx"], RAIL["home"], RAIL["v5"], "#5c7cfa"])
    b.box(0, 40, 118, 56, "Phone or laptop", "web browser")
    b.box(170, 40, 130, 56, "Raspberry Pi", "runs the web app", fill="#eef3f7", stroke=ACCENT)
    b.box(340, 40, 130, 56, "Arduino Nano", "real-time control", fill="#eef4fc", stroke="#1f5fa8")
    b.box(540, 40, 140, 56, "TMC2209", "stepper driver", fill="#f1f3f5", stroke="#1e2430")
    b.box(170, 176, 130, 50, "Camera", "Sony A6400")
    b.box(340, 176, 130, 50, "Home switch", "roller microswitch")
    b.box(540, 176, 64, 50, "NEMA 17")
    b.box(616, 176, 64, 50, "12 V")
    b.link([(118, 68), (168, 68)], "#495057", "LAN", (143, 61), both=True)
    b.link([(300, 68), (338, 68)], "#495057", "USB", (319, 61), both=True)
    b.link([(235, 98), (235, 174)], "#495057", "USB", (243, 140), "start", both=True)
    b.link([(470, 60), (538, 60)], RAIL["step"], "STEP DIR EN", (504, 53))
    b.link([(472, 80), (538, 80)], RAIL["rx"], "UART", (504, 94), both=True)
    b.link([(405, 174), (405, 98)], RAIL["home"], "D2", (413, 140), "start")
    b.link([(572, 98), (572, 174)], "#5c7cfa", "coils A, B", (566, 140), "end")
    b.link([(648, 174), (648, 98)], RAIL["v5"], "VM", (655, 140), "start")
    return b.svg("0 30 690 202")


TMC_LEFT = [
    ("EN", "enable"),
    ("MS1", "address"),
    ("MS2", "address"),
    ("PDN", "UART: use this one"),
    ("PDN", "(spare)"),
    ("CLK", "clock"),
    ("STEP", "step"),
    ("DIR", "direction"),
]
TMC_RIGHT = [
    ("VM", "motor supply, 12 V"),
    ("GND", "motor ground"),
    ("A2", "coil A"),
    ("A1", "coil A"),
    ("B1", "coil B"),
    ("B2", "coil B"),
    ("VIO", "logic 5 V"),
    ("GND", "logic ground"),
]


def tmc_figure() -> str:
    bx, by, bw, bh = 262, 44, 150, 262
    o = [
        t(150, 22, "LOGIC SIDE: to the Nano", 10, ACCENT, "middle", "bold"),
        t(550, 22, "POWER SIDE: motor and 12 V", 10, WARN, "middle", "bold"),
        f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="9" fill="#1e2430"/>',
        f'<circle cx="{bx + bw / 2}" cy="{by + 40}" r="14" fill="#e9ecef" stroke="#adb5bd" '
        f'stroke-width="2"/>',
        f'<path d="M{bx + bw / 2 - 8},{by + 40} h16 M{bx + bw / 2},{by + 32} v16" '
        f'stroke="#495057" stroke-width="3"/>',
        t(bx + bw / 2, by + 68, "potentiometer", 8.5, "#ced4da", "middle"),
        f'<rect x="{bx + 32}" y="{by + 84}" width="{bw - 64}" height="96" rx="3" fill="#c99a2e" '
        f'stroke="#a37c1f"/>',
        t(bx + bw / 2, by + 128, "cooling pad", 10, "#3b2a05", "middle", "bold"),
        t(bx + bw / 2, by + 143, "(chip underneath)", 8, "#3b2a05", "middle"),
    ]
    for i in range(8):
        y = by + 26 + i * 30
        for side, (name, desc) in ((0, TMC_LEFT[i]), (1, TMC_RIGHT[i])):
            x = bx + 16 if side == 0 else bx + bw - 16
            if i == 0 and side == 0:
                o.append(
                    f'<rect x="{x - 7}" y="{y - 7}" width="14" height="14" fill="#e6b325" '
                    f'stroke="#9c7a12"/>'
                )
            else:
                o.append(f'<circle cx="{x}" cy="{y}" r="7" fill="#e6b325" stroke="#9c7a12"/>')
            if side == 0:
                o.append(t(bx - 12, y + 4.5, name, 12, INK, "end", "bold"))
                hl = i == 3
                o.append(
                    t(
                        bx - 62,
                        y + 4,
                        desc,
                        9,
                        ACCENT if hl else MUTED,
                        "end",
                        "bold" if hl else "normal",
                    )
                )
            else:
                o.append(t(bx + bw + 12, y + 4.5, name, 12, INK, "start", "bold"))
                o.append(t(bx + bw + 56, y + 4, desc, 9, WARN if i == 0 else MUTED, "start"))
    o.append(
        t(
            337,
            326,
            "Top view: potentiometer up, pins down into the breadboard. "
            "Check the labels on your board.",
            9.5,
            MUTED,
            "middle",
        )
    )
    return svg("0 0 680 334", o)


def nano_rail_figure() -> str:
    return svg("0 0 450 182", nano(75, 25, 30, 150, RAIL_RINGS_TOP, RAIL_RINGS_BOT))


def resistor_figure(bands: list[str]) -> str:
    return svg("0 0 250 56", f'<g transform="scale(1.6)">{resistor(10, 18, 146, 18, bands)}</g>')


def cap_figure() -> str:
    o = [
        '<rect x="30" y="10" width="46" height="76" rx="6" fill="#26353f"/>',
        '<rect x="30" y="10" width="13" height="76" rx="4" fill="#c6ccd2"/>',
        '<line x1="43" y1="86" x2="43" y2="122" stroke="#9aa0a6" stroke-width="2.4"/>',
        '<line x1="64" y1="86" x2="64" y2="134" stroke="#9aa0a6" stroke-width="2.4"/>',
        t(38, 140, "&minus;", 12, INK, "middle", "bold"),
        t(66, 148, "+", 12, INK, "middle", "bold"),
        t(53, 160, "side", 8.5, MUTED, "middle"),
        '<circle cx="150" cy="62" r="26" fill="#26353f"/>',
        '<path d="M150,36 A26,26 0 0 0 150,88 Z" fill="#c6ccd2"/>',
        t(141, 66, "&minus;", 13, INK, "middle", "bold"),
        t(161, 67, "+", 13, "#fff", "middle", "bold"),
        t(150, 110, "top, as drawn", 8.5, MUTED, "middle"),
        t(150, 121, "on the breadboard", 8.5, MUTED, "middle"),
    ]
    o += [f'<rect x="33" y="{y}" width="7" height="2.2" fill="#26353f"/>' for y in (28, 50, 72)]
    return svg("0 0 200 166", o)


def coil_figure() -> str:
    o: list[str] = []
    leads = ["#1c7ed6", "#e03131", "#25262b", "#2f9e44"]

    def panel(x0: float, pair: tuple[int, int], reading: str, verdict: str, good: bool) -> None:
        o.append(f'<rect x="{x0}" y="20" width="70" height="64" rx="7" fill="#5c636b"/>')
        o.append(
            f'<circle cx="{x0 + 35}" cy="52" r="13" fill="#dee2e6" stroke="#adb5bd" '
            'stroke-width="2"/>'
        )
        o.append(t(x0 + 35, 14, "NEMA 17", 9, MUTED, "middle", "bold"))
        ends = []
        for i, c in enumerate(leads):
            x = x0 + 14 + i * 14
            o.append(f'<path d="M{x},84 L{x},130" stroke="{c}" stroke-width="3.4" fill="none"/>')
            ends.append(x)
        mx, my = x0 + 160, 52
        o.append(
            f'<rect x="{mx - 34}" y="{my - 40}" width="68" height="92" rx="9" fill="#f8c33c" '
            f'stroke="#b48a12"/>'
        )
        o.append(
            f'<rect x="{mx - 26}" y="{my - 32}" width="52" height="24" rx="3" fill="#dfe8d8" '
            f'stroke="#7c8a73"/>'
        )
        o.append(t(mx, my - 15, reading, 12, INK, "middle", "bold", 'font-family="Consolas"'))
        o.append(f'<circle cx="{mx}" cy="{my + 22}" r="13" fill="#3a3f47"/>')
        o.append(t(mx, my + 26, "&Omega;", 11, "#fff", "middle", "bold"))
        for k, idx in enumerate(pair):
            px = ends[idx]
            col = "#e03131" if k == 0 else "#25262b"
            o.append(
                f'<path d="M{px},130 C{px},150 {mx - 10 + k * 20},150 '
                f'{mx - 10 + k * 20},{my + 52}" '
                f'stroke="{col}" stroke-width="2" fill="none"/>'
            )
            o.append(f'<circle cx="{px}" cy="130" r="3.5" fill="{col}"/>')
        o.append(t(x0 + 100, 172, verdict, 10, "#2b7a3d" if good else "#b42318", "middle", "bold"))

    panel(10, (0, 1), "2.4 &Omega;", "a few ohms: one coil (a pair)", True)
    panel(290, (1, 2), "OL", "open: different coils", False)
    return svg("0 0 560 180", o)


def breadboard_figure() -> str:
    p, x0, y0, ncol = 22, 40, 20, 12
    o = [
        f'<rect x="10" y="4" width="{x0 + (ncol - 1) * p + 30}" height="262" rx="10" '
        f'fill="#f6f1e6" stroke="#ddd3bf"/>'
    ]
    rail_y = y0 + 10
    rows = {r: y0 + 50 + i * 18 for i, r in enumerate("abcde")}
    rows.update({r: y0 + 50 + (i + 6) * 18 for i, r in enumerate("fghij")})
    o.append(
        f'<rect x="{x0 - 12}" y="{rail_y - 8}" width="{(ncol - 1) * p + 24}" height="16" rx="8" '
        f'fill="#e03131" fill-opacity="0.2"/>'
    )
    hx = x0 + 2 * p
    o.append(
        f'<rect x="{hx - 9}" y="{rows["a"] - 9}" width="18" height="{rows["e"] - rows["a"] + 18}" '
        f'rx="6" fill="{ACCENT}" fill-opacity="0.22"/>'
    )
    o.append(
        f'<rect x="{hx - 9}" y="{rows["f"] - 9}" width="18" height="{rows["j"] - rows["f"] + 18}" '
        f'rx="6" fill="#1c7ed6" fill-opacity="0.16"/>'
    )
    gap_y = (rows["e"] + rows["f"]) / 2
    o.append(
        f'<rect x="12" y="{gap_y - 7}" width="{x0 + (ncol - 1) * p + 26}" height="14" '
        'fill="#e3dccb"/>'
    )
    for c in range(ncol):
        x = x0 + c * p
        o.extend(
            f'<rect x="{x - 2.5}" y="{y - 2.5}" width="5" height="5" fill="#555"/>'
            for y in [rail_y, *rows.values()]
        )
    o.extend(t(24, y + 3.5, r, 9, MUTED, "middle") for r, y in rows.items())
    o.extend(t(x0 + (c - 1) * p, rows["a"] - 12, str(c), 8, MUTED, "middle") for c in (1, 5, 10))
    ax = x0 + (ncol - 1) * p + 50
    o.append(t(ax, rail_y + 4, "a rail: the whole row is one connection", 10, "#b42318"))
    o.append(
        t(ax, (rows["a"] + rows["e"]) / 2 + 4, "a&ndash;e of one column: one strip", 10, ACCENT)
    )
    o.append(t(ax, gap_y - 2, "the gap: the two halves", 10, "#555"))
    o.append(t(ax, gap_y + 11, "are not connected", 10, "#555"))
    o.append(
        t(
            ax,
            (rows["f"] + rows["j"]) / 2 + 4,
            "f&ndash;j of one column: another strip",
            10,
            "#1c7ed6",
        )
    )
    return svg("0 0 640 270", o)


class Board:
    """Breadboard geometry: 30 columns, rows a-j, two rails above and two below."""

    def __init__(self, top: float, pitch: float = 24, x0: float = 120) -> None:
        self.b = top
        self.p = pitch
        self.x0 = x0
        self.top_plus, self.top_minus = top + 20, top + 44
        self.bot_plus, self.bot_minus = top + 388, top + 412
        self.rows = {r: i for i, r in enumerate("abcde")} | {
            r: i + 7 for i, r in enumerate("fghij")
        }

    def cx(self, c: float) -> float:
        return self.x0 + (c - 1) * self.p

    def ry(self, r: str) -> float:
        return self.b + 84 + self.rows[r] * self.p

    def hole(self, h: str) -> tuple[float, float]:
        return self.cx(int(h[1:])), self.ry(h[0])

    def draw(self, rail_labels: list[tuple[str, str]], labels_right: bool = False) -> list[str]:
        b, cx, ry = self.b, self.cx, self.ry
        left, right = cx(1) - 30, cx(30) + 30
        o = [
            f'<rect x="{left}" y="{b}" width="{right - left}" height="432" rx="10" '
            f'fill="#f6f1e6" stroke="#d9cfba" stroke-width="1.5"/>',
            f'<rect x="{left + 2}" y="{(ry("e") + ry("f")) / 2 - 9}" width="{right - left - 4}" '
            f'height="18" fill="#e5dece"/>',
        ]
        for y, col in (
            (b + 8, "#e03131"),
            (b + 56, "#1c7ed6"),
            (b + 376, "#e03131"),
            (b + 424, "#1c7ed6"),
        ):
            o.append(
                f'<line x1="{left + 14}" y1="{y}" x2="{right - 14}" y2="{y}" stroke="{col}" '
                f'stroke-width="1.3"/>'
            )
        rails = (self.top_plus, self.top_minus, self.bot_plus, self.bot_minus)
        signs = ["+", "&minus;", "+", "&minus;"]
        for y, s, (label, col) in zip(rails, signs, rail_labels, strict=True):
            sign_col = "#e03131" if s == "+" else "#1c7ed6"
            o.append(t(left + 8, y + 4, s, 12, sign_col, "middle", "bold"))
            o.append(t(right - 8, y + 4, s, 12, sign_col, "middle", "bold"))
            if labels_right:
                o.append(t(right + 6, y + 4, label, 10, col, "start", "bold"))
            else:
                o.append(t(left - 6, y + 4, label, 10, col, "end", "bold"))
        for c in range(1, 31):
            x = cx(c)
            o.extend(
                f'<rect x="{x - 2.6}" y="{y - 2.6}" width="5.2" height="5.2" fill="#6b6b6b"/>'
                for y in [*rails, *(ry(r) for r in "abcdefghij")]
            )
        for c in (1, 5, 10, 15, 20, 25, 30):
            o.append(t(cx(c), b + 69, str(c), 8.5, "#8a8170", "middle"))
            o.append(t(cx(c), b + 367, str(c), 8.5, "#8a8170", "middle"))
        for r in "abcdefghij":
            o.append(t(left + 14, ry(r) + 3.5, r, 9, "#8a8170", "middle"))
            o.append(t(right - 14, ry(r) + 3.5, r, 9, "#8a8170", "middle"))
        return o


TMC_TOP = ["DIR", "STEP", "CLK", "PDN", "PDN", "MS2", "MS1", "EN"]
TMC_BOT = ["GND", "VIO", "B2", "B1", "A1", "A2", "GND", "VM"]


def rail_wiring() -> str:
    bd = Board(120)
    cx, ry, hole = bd.cx, bd.ry, bd.hole
    o = bd.draw(
        [
            ("5 V (+)", "#e03131"),
            ("GND (&minus;)", "#1c7ed6"),
            ("5 V (+)", "#e03131"),
            ("GND (&minus;)", "#1c7ed6"),
        ]
    )
    o.append(nano(cx(2), bd.p, ry("d"), ry("h"), RAIL_RINGS_TOP, RAIL_RINGS_BOT))

    # TMC2209, a quarter turn clockwise from the pinout figure: logic pins along the top.
    c0 = 19
    tx0, tx1 = cx(c0), cx(c0 + 7)
    o.append(
        f'<rect x="{tx0 - 14}" y="{ry("d") - 13}" width="{tx1 - tx0 + 28}" '
        f'height="{ry("g") - ry("d") + 26}" rx="5" fill="#1e2430"/>'
    )
    mid = (ry("d") + ry("g")) / 2
    o.append(
        f'<rect x="{cx(c0 + 1.6)}" y="{mid - 12}" width="70" height="24" rx="2" fill="#c99a2e"/>'
    )
    o.append(t(cx(c0 + 1.6) + 35, mid + 4, "TMC2209", 10, "#3b2a05", "middle", "bold"))
    pcx = cx(c0 + 6.2)
    o.append(
        f'<circle cx="{pcx}" cy="{mid}" r="11" fill="#e9ecef" stroke="#adb5bd" stroke-width="1.5"/>'
    )
    o.append(
        f'<path d="M{pcx - 6},{mid} h12 M{pcx},{mid - 6} v12" stroke="#495057" stroke-width="2.4"/>'
    )
    ring_top = {
        0: RAIL["dir"],
        1: RAIL["step"],
        4: RAIL["rx"],
        5: RAIL["gnd"],
        6: RAIL["gnd"],
        7: RAIL["en"],
    }
    ring_bot = {0: RAIL["gnd"], 1: RAIL["v5"]}
    for i in range(8):
        x = cx(c0 + i)
        for y, names, rings, ly in (
            (ry("d"), TMC_TOP, ring_top, ry("d") + 18),
            (ry("g"), TMC_BOT, ring_bot, ry("g") - 11),
        ):
            if i in rings:
                o.append(
                    f'<circle cx="{x}" cy="{y}" r="8.6" fill="#fff" stroke="{rings[i]}" '
                    f'stroke-width="2.6"/>'
                )
            if i == 7 and names is TMC_TOP:
                o.append(
                    f'<rect x="{x - 5}" y="{y - 5}" width="10" height="10" fill="#e6b325" '
                    f'stroke="#9c7a12" stroke-width="0.8"/>'
                )
            else:
                o.append(
                    f'<circle cx="{x}" cy="{y}" r="5" fill="#e6b325" stroke="#9c7a12" '
                    f'stroke-width="0.8"/>'
                )
            o.append(t(x, ly, names[i], 7.4, "#e9ecef", "middle", "bold"))

    # 100 uF capacitor, top view, legs in h25 (-) and h26 (+)
    ccx, ccy = (cx(25) + cx(26)) / 2, ry("h") + 12
    o.append(
        f'<circle cx="{ccx}" cy="{ccy}" r="17" fill="#26353f" stroke="#111" stroke-width="0.8"/>'
    )
    o.append(f'<path d="M{ccx},{ccy - 17} A17,17 0 0 0 {ccx},{ccy + 17} Z" fill="#c6ccd2"/>')
    o.append(t(ccx - 7, ccy + 4.5, "&minus;", 12, INK, "middle", "bold"))
    o.append(t(ccx + 7, ccy + 4.5, "+", 12, "#fff", "middle", "bold"))

    def jumper(h: str, y_rail: float, color: str, label: str, ly: float | None = None) -> None:
        x, y = hole(h)
        o.append(wire([(x, y), (x, y_rail)], color))
        o.append(tag(x, ly if ly is not None else (y + y_rail) / 2, label, color, 8))

    jumper("a13", bd.top_minus, RAIL["gnd"], "W1")
    jumper("j15", bd.bot_minus, RAIL["gnd"], "W2", ry("j") + 33)
    jumper("j13", bd.bot_plus, RAIL["v5"], "W3", ry("j") + 24)
    o.append(wire([(cx(30), bd.bot_plus), (cx(30), bd.top_plus)], RAIL["v5"]))
    o.append(tag(cx(30), (ry("e") + ry("f")) / 2, "W4", RAIL["v5"], 8))
    jumper("j19", bd.bot_minus, RAIL["gnd"], "W5", ry("j") + 33)
    jumper("j20", bd.bot_plus, RAIL["v5"], "W6", ry("j") + 24)
    jumper("a24", bd.top_minus, RAIL["gnd"], "W7", bd.top_minus + 23)
    jumper("a25", bd.top_minus, RAIL["gnd"], "W8", bd.top_minus + 23)

    # R1: 10 kOhm pull-up from EN (a26) to the top 5 V rail
    x26, ya = hole("a26")
    o.append(resistor(x26, ya, x26, bd.top_plus, R10K))
    o.append(t(x26 - 4, bd.b - 8, "R1 10 k&Omega;", 9.5, INK, "end", "bold"))
    o.append(
        f'<path d="M{x26 - 3},{bd.b - 11} Q{x26},{bd.b - 11} {x26},{bd.b - 2} '
        f'L{x26},{bd.top_plus - 6}" fill="none" stroke="#868e96" stroke-width="0.8" '
        f'stroke-dasharray="2 2"/>'
    )

    def flat(h1: str, h2: str, color: str, label: str, tag_x: float, tcol: str) -> None:
        (x1, y1), (x2, y2) = hole(h1), hole(h2)
        o.append(wire([(x1, y1), (x2, y2)], color))
        o.append(tag(tag_x, y1, label, tcol, 8.5))

    flat("c9", "c26", RAIL["en"], "W9  D5 &rarr; EN", cx(17.2), RAIL["en"])
    flat("b10", "b19", RAIL["dir"], "W10  D4 &rarr; DIR", cx(15.4), RAIL_TEXT["dir"])

    # R2: 1 kOhm from b23 (PDN) to b27
    (rx1, ryy), (rx2, _) = hole("b23"), hole("b27")
    o.append(resistor(rx1, ryy, rx2, ryy, R1K))
    o.append(
        t(
            cx(27) + 8,
            ryy + 3.5,
            "R2 1 k&Omega;",
            9,
            INK,
            "start",
            "bold",
            'stroke="#f6f1e6" stroke-width="6" stroke-linejoin="round" paint-order="stroke"',
        )
    )

    def arch(h1: str, h2: str, lane: float, color: str, label: str) -> None:
        (x1, y1), (x2, y2) = hole(h1), hole(h2)
        o.append(wire([(x1, y1), (x1, lane), (x2, lane), (x2, y2)], color, r=9))
        o.append(tag((x1 + x2) / 2, lane, label, color, 9))

    arch("a6", "a27", 26, RAIL["tx"], "W13  D8 &rarr; R2 (1 k&Omega;)")
    arch("a7", "a23", 54, RAIL["rx"], "W12  D7 &rarr; PDN")
    arch("a11", "a20", 82, RAIL["step"], "W11  D3 &rarr; STEP")

    # Home switch, top right; NO to a12 (D2) along a lane between rows a and b
    ss = 0.9
    sx, sy = cx(28) - 20 * ss, 34
    o.append(switch_drawing(sx, sy, ss))
    c_x, no_x = sx + 20 * ss, sx + 50 * ss
    sb = sy + 52 * ss
    lane = ry("a") + 11
    o.append(wire([(c_x, sb), (c_x, bd.top_minus)], RAIL["gnd"], r=6))
    jog_x = (cx(29) + cx(30)) / 2
    o.append(
        wire(
            [
                (no_x, sb),
                (no_x, bd.b - 8),
                (jog_x, bd.b - 8),
                (jog_x, lane),
                (cx(12), lane),
                (cx(12), ry("a")),
            ],
            RAIL["home"],
            r=6,
        )
    )
    o.append(tag(c_x, bd.b - 22, "W15", RAIL["gnd"], 8))
    o.append(tag(cx(15.2), lane, "W14  D2 &rarr; switch NO", RAIL["home"], 8.5))
    o.append(t(sx + 50 * ss, sy - 18, "home switch", 10, INK, "middle", "bold"))

    # USB to the Pi, camera
    usb_y = (ry("d") + ry("h")) / 2
    ux = cx(2) - bd.p * 2.05
    o.append(
        f'<path d="{rpath([(ux, usb_y), (30, usb_y), (30, 612)], 10)}" fill="none" '
        f'stroke="#495057" stroke-width="6" stroke-linecap="round"/>'
    )
    o.append(
        f'<rect x="8" y="612" width="150" height="58" rx="8" fill="#eef3f7" stroke="{ACCENT}" '
        f'stroke-width="1.5"/>'
    )
    o.append(t(83, 637, "Raspberry Pi", 12, INK, "middle", "bold"))
    o.append(t(83, 653, "USB ports", 9.5, MUTED, "middle"))
    o.append(t(36, 596, "USB (Nano)", 9.5, "#495057", "start", "bold"))
    o.append(
        '<rect x="230" y="612" width="150" height="58" rx="8" fill="#fff" stroke="#adb5bd" '
        'stroke-width="1.5"/>'
    )
    o.append(t(305, 637, "Camera", 12, INK, "middle", "bold"))
    o.append(t(305, 653, "USB", 9.5, MUTED, "middle"))
    o.append(
        '<path d="M230,641 L158,641" stroke="#495057" stroke-width="6" stroke-linecap="round"/>'
    )

    # Motor
    motor_cols = [(21, "#1c7ed6"), (22, "#e03131"), (23, "#25262b"), (24, "#2f9e44")]
    plug_y = 610
    for c, colr in motor_cols:
        o.append(wire([(cx(c), ry("j")), (cx(c), plug_y)], colr, width=4))
    o.append(
        f'<rect x="{cx(21) - 16}" y="{plug_y - 2}" width="{3 * bd.p + 32}" height="14" rx="2" '
        f'fill="#f1f3f5" stroke="#868e96"/>'
    )
    o.append(t(cx(21) - 22, plug_y + 9, "motor plug", 9, MUTED, "end"))
    mx = (cx(21) + cx(24)) / 2
    for i, (c, colr) in enumerate(motor_cols):
        x = cx(c)
        o.append(
            f'<path d="M{x},{plug_y + 12} C{x},{plug_y + 30} {mx - 12 + i * 8},{plug_y + 24} '
            f'{mx - 12 + i * 8},{plug_y + 40}" fill="none" stroke="{colr}" stroke-width="3.2"/>'
        )
    o.append(
        f'<rect x="{mx - 40}" y="{plug_y + 40}" width="80" height="72" rx="8" fill="#5c636b"/>'
    )
    o.append(
        f'<circle cx="{mx}" cy="{plug_y + 76}" r="15" fill="#dee2e6" stroke="#adb5bd" '
        'stroke-width="2"/>'
    )
    o.append(t(mx, plug_y + 128, "NEMA 17", 10.5, INK, "middle", "bold"))
    o.append(t(cx(21) - 22, plug_y + 30, "coil B", 9, MUTED, "end", "bold"))
    o.append(t(cx(24) + 22, plug_y + 30, "coil A", 9, MUTED, "start", "bold"))

    # 12 V supply: straight to VM and GND, never onto the rails
    gx, vx = cx(25), cx(26)
    o.append(wire([(gx, ry("j")), (gx, 590), (790, 590), (790, 624)], "#25262b", width=6, r=8))
    o.append(wire([(vx, ry("j")), (vx, 574), (838, 574), (838, 624)], "#c92a2a", width=6, r=8))
    o.append(
        '<rect x="756" y="618" width="116" height="80" rx="8" fill="#e9ecef" stroke="#868e96" '
        'stroke-width="1.5"/>'
    )
    o.append(
        '<circle cx="790" cy="632" r="7" fill="#25262b"/><circle cx="838" cy="632" r="7" '
        'fill="#e03131"/>'
    )
    o.append(t(803, 636, "&minus;", 11, INK, "middle", "bold"))
    o.append(t(852, 636, "+", 11, "#c92a2a", "middle", "bold"))
    o.append(t(814, 664, "12 V supply", 10, INK, "middle", "bold"))
    o.append(t(814, 678, "V1 &minus;, V2 +", 9, MUTED, "middle"))
    return svg("0 0 880 752", o)


def swatch(color: str) -> str:
    return f'<span class="sw" style="background:{color}"></span>'


RES = "#c9a227"  # swatch colour for resistors and the capacitor in the wire tables

RAIL_WIRES: list[tuple[str, str | None, str, str, str]] = [
    ("", None, "1. Boards", "", ""),
    (
        "P1",
        None,
        "Arduino Nano: pins in rows d and h, columns 2&ndash;16",
        "",
        "D12 and D13 in column 2, USB to the left",
    ),
    (
        "P2",
        None,
        "TMC2209: pins in rows d and g, columns 19&ndash;26",
        "",
        "DIR in d19, EN in d26, VM in g26; potentiometer to the right",
    ),
    ("", None, "2. Wires and parts", "", ""),
    ("W1", RAIL["gnd"], "a13 (Nano GND, top row)", "top GND rail", ""),
    ("W2", RAIL["gnd"], "j15 (Nano GND, bottom row)", "bottom GND rail", ""),
    ("W3", RAIL["v5"], "j13 (Nano 5V)", "bottom 5 V rail", ""),
    ("W4", RAIL["v5"], "bottom 5 V rail", "top 5 V rail", "column 30, joins the rails"),
    ("W5", RAIL["gnd"], "j19 (TMC GND)", "bottom GND rail", "logic ground"),
    ("W6", RAIL["v5"], "j20 (TMC VIO)", "bottom 5 V rail", "logic supply"),
    ("W7", RAIL["gnd"], "a24 (TMC MS2)", "top GND rail", "UART address 0"),
    ("W8", RAIL["gnd"], "a25 (TMC MS1)", "top GND rail", "UART address 0"),
    ("R1", RES, "a26 (TMC EN)", "top 5 V rail", "10 k&Omega; pull-up"),
    ("W9", RAIL["en"], "c9 (D5)", "c26 (EN)", "flat on the board"),
    ("W10", RAIL["dir"], "b10 (D4)", "b19 (DIR)", "flat on the board"),
    ("W11", RAIL["step"], "a11 (D3)", "a20 (STEP)", ""),
    ("W12", RAIL["rx"], "a7 (D7)", "a23 (PDN, UART)", "UART receive, direct"),
    ("R2", RES, "b23 (PDN)", "b27", "1 k&Omega;"),
    ("W13", RAIL["tx"], "a6 (D8)", "a27", "UART transmit, through R2"),
    ("W14", RAIL["home"], "switch NO", "a12 (D2)", "between rows a and b"),
    ("W15", RAIL["gnd"], "switch C", "top GND rail", "NC stays empty"),
    ("C1", RES, "100 &micro;F: stripe (&minus;) in h25", "+ in h26", "check the polarity"),
    ("U1", "#495057", "Nano USB", "Raspberry Pi", "a data cable"),
    ("U2", "#495057", "Camera USB", "Raspberry Pi", ""),
    ("", None, "3. Last, with the 12 V supply off (section 9)", "", ""),
    ("M1", "#1c7ed6", "motor coil B", "j21 (B2), j22 (B1)", ""),
    ("M2", "#2f9e44", "motor coil A", "j23 (A1), j24 (A2)", ""),
    ("V1", "#25262b", "12 V supply &minus;", "j25 (TMC GND)", "straight to the pin"),
    ("V2", "#c92a2a", "12 V supply +", "j26 (TMC VM)", "straight to the pin"),
]


def wire_table(rows: list[tuple[str, str | None, str, str, str]]) -> str:
    out = [
        '<table class="wires"><colgroup><col class="c-tick"><col class="c-id"><col class="c-from">'
        '<col class="c-to"><col></colgroup><thead><tr><th></th><th>No.</th><th>From</th>'
        "<th>To</th><th>Note</th></tr></thead><tbody>"
    ]
    for wid, color, a, b, note in rows:
        if not wid:
            out.append(f'<tr class="group"><td colspan="5">{a}</td></tr>')
            continue
        mark = swatch(color) if color else ""
        out.append(
            f'<tr><td class="tick"></td><td class="id">{mark}{wid}</td><td>{a}</td><td>{b}</td>'
            f'<td class="muted">{note}</td></tr>'
        )
    return "".join(out) + "</tbody></table>"


# ------------------------------------------------------------------------------------------
# Scan module electronics

MOD = {
    "in1": "#f08c00",
    "in2": "#d4a300",
    "in3": "#2f9e44",
    "in4": "#1c7ed6",
    "sw": "#e64980",  # tilt switch (D10)
    "hall": "#7c3aed",  # KY-024 analogue out (A0)
    "mv": "#e03131",  # motor 5 V, from the separate supply
    "nv": "#a61e4d",  # the Nano's own 5 V, for the hall sensor only
    "gnd": "#25262b",
    "usb": "#495057",
}
MOD_TEXT = dict(MOD, in2="#9a7600")
MOTOR_LEADS = ["#1c7ed6", "#f06595", "#fcc419", "#fd7e14", "#e03131"]  # 28BYJ-48 plug order

# Nano top row index: D11 1, D10 2, D9 3, D7 5, D6 6, D5 7, D4 8, D3 9, D2 10, GND 11.
MOD_RINGS_TOP = {
    1: MOD["in4"],
    2: MOD["sw"],
    3: MOD["in3"],
    5: MOD["in1"],
    6: MOD["in2"],
    7: MOD["in4"],
    8: MOD["in3"],
    9: MOD["in2"],
    10: MOD["in1"],
    11: MOD["gnd"],
}
MOD_RINGS_BOT = {3: MOD["hall"], 11: MOD["nv"], 13: MOD["gnd"]}


def module_overview() -> str:
    b = Blocks(["#495057", MOD["in1"], MOD["sw"], MOD["hall"], MOD["mv"], "#5c7cfa", "#adb5bd"])
    b.box(0, 128, 112, 52, "Phone or laptop", "web browser")
    b.box(150, 128, 120, 52, "Raspberry Pi", "runs the web app", fill="#eef3f7", stroke=ACCENT)
    b.box(310, 6, 120, 50, "Camera", dashed=True, stroke="#adb5bd")
    b.box(310, 66, 120, 50, "Rail Nano", "unchanged", dashed=True, stroke="#adb5bd")
    b.box(
        470,
        66,
        210,
        50,
        "TMC2209, NEMA 17, switch",
        "the rail, unchanged",
        dashed=True,
        stroke="#adb5bd",
    )
    b.box(310, 140, 120, 90, "Module Nano", "its own USB cable", fill="#eef4fc", stroke="#1f5fa8")
    b.box(470, 140, 92, 40, "ULN2003", "yaw", fill="#ebfbee", stroke="#2f6f4f")
    b.box(470, 190, 92, 40, "ULN2003", "tilt", fill="#ebfbee", stroke="#2f6f4f")
    b.box(600, 140, 80, 40, "28BYJ-48", "yaw motor")
    b.box(600, 190, 80, 40, "28BYJ-48", "tilt motor")
    b.box(300, 270, 84, 36, "Tilt switch")
    b.box(394, 270, 70, 36, "KY-024")
    b.box(490, 270, 120, 36, "5 V supply", fill="#fff5f5", stroke=MOD["mv"])
    b.link([(112, 154), (148, 154)], "#495057", "LAN", (130, 147), both=True)
    b.link([(270, 146), (290, 146), (290, 31), (308, 31)], "#adb5bd")
    b.link([(270, 150), (294, 150), (294, 91), (308, 91)], "#adb5bd")
    b.link([(270, 166), (294, 166), (294, 185), (308, 185)], "#495057", "USB", (278, 122), "start")
    b.link([(430, 91), (468, 91)], "#adb5bd")
    b.link([(430, 170), (450, 170), (450, 160), (468, 160)], MOD["in1"], "D2&ndash;D5", (449, 134))
    b.link([(430, 200), (450, 200), (450, 210), (468, 210)], MOD["in1"], "D6&ndash;D11", (449, 246))
    b.link([(562, 160), (598, 160)], "#5c7cfa")
    b.link([(562, 210), (598, 210)], "#5c7cfa")
    b.link([(342, 270), (342, 232)], MOD["sw"], "D10", (348, 258), "start")
    b.link([(420, 270), (420, 232)], MOD["hall"], "A0", (404, 258), "end")
    b.link([(530, 270), (530, 232)], MOD["mv"], "+5 V", (536, 258), "start")
    b.note(550, 322, "only its ground is joined to the Nano's")
    return b.svg("0 0 690 330")


def uln_board(
    x: float, y: float, w: float, h: float, pins: list[tuple[float, str]], scale_text: float = 1.0
) -> str:
    """Stylised ULN2003 board; pins along the bottom edge, the motor socket on the top edge."""
    cx0 = x + w / 2
    o = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#2f6f4f" stroke="#1e4a34" '
        f'stroke-width="1.2"/>',
        f'<rect x="{cx0 - 34}" y="{y + 40}" width="68" height="24" rx="2" fill="#1b1f24"/>',
        t(cx0, y + 56, "ULN2003", 8.5 * scale_text, "#ced4da", "middle", "bold"),
        f'<rect x="{cx0 - 30}" y="{y - 6}" width="60" height="22" rx="2" fill="#f8f9fa" '
        f'stroke="#adb5bd"/>',
    ]
    for i, s in enumerate("ABCD"):
        lx = cx0 - 33 + i * 22
        o.append(
            f'<circle cx="{lx}" cy="{y + 78}" r="4.2" fill="#ff6b6b" stroke="#c92a2a" '
            f'stroke-width="0.8"/>'
        )
        o.append(t(lx + 7, y + 81, s, 6.5, "#d3f9d8"))
    o += [
        f'<rect x="{cx0 - 24 + i * 11}" y="{y + 1}" width="5" height="8" fill="#868e96"/>'
        for i in range(5)
    ]
    py = y + h - 14
    for px, label in pins:
        o.append(
            f'<rect x="{px - 5}" y="{py - 5}" width="10" height="10" fill="#e6b325" '
            f'stroke="#9c7a12" stroke-width="0.8"/>'
        )
        o.append(t(px, py - 10, label, 7.6 * scale_text, "#fff", "middle", "bold"))
    return "".join(o)


def jumper_cap(x: float, y: float) -> str:
    return f'<rect x="{x - 12}" y="{y - 6}" width="24" height="12" rx="2" fill="#1b1f24"/>' + t(
        x, y + 3, "ON", 6.5, "#adb5bd", "middle", "bold"
    )


def uln_figure() -> str:
    bx, by, bw, bh = 200, 60, 240, 200
    pins: list[tuple[float, str]] = [(bx + 40 + i * 26, f"IN{i + 1}") for i in range(4)]
    pins += [(bx + 170, "&minus;"), (bx + 196, "+")]
    o = [uln_board(bx, by, bw, bh, pins, 1.15), jumper_cap(bx + 183, by + bh - 50)]

    def note(
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        lines: list[str],
        color: str = INK,
        anchor: str = "start",
    ) -> None:
        o.append(f'<path d="M{x1},{y1} L{x2},{y2}" stroke="#868e96" stroke-width="1" fill="none"/>')
        o.append(f'<circle cx="{x1}" cy="{y1}" r="2.2" fill="#868e96"/>')
        for i, s in enumerate(lines):
            dx = 4 if anchor == "start" else -4
            o.append(
                t(
                    x2 + dx,
                    y2 + 4 + i * 12,
                    s,
                    9.5 if i == 0 else 8.8,
                    color if i == 0 else MUTED,
                    anchor,
                    "bold" if i == 0 else "normal",
                )
            )

    note(bx + 150, by + 2, 470, 34, ["Motor socket", "5 pins, keyed"])
    note(bx + 153, by + 78, 470, 104, ["LEDs A&ndash;D", "light while the coils are on"])
    note(bx + 183, by + bh - 50, 470, 166, ["Power jumper", "must be fitted"], WARN)
    note(
        bx + 183,
        by + bh - 14,
        470,
        222,
        ["Power &minus; and +", "from the separate 5 V supply"],
        MOD["mv"],
    )
    note(
        bx + 79, by + bh - 14, 170, 222, ["IN1 IN2 IN3 IN4", "signals from the Nano"], ACCENT, "end"
    )
    note(bx + 86, by + 52, 170, 100, ["ULN2003", "switches the motor coils"], INK, "end")
    o.append(
        t(
            320,
            280,
            "Typical layout. Go by the labels printed next to the pins on your board.",
            9,
            MUTED,
            "middle",
        )
    )
    return svg("0 0 640 288", o)


def motor_drawing(cxm: float, cym: float, r: float = 34, label: bool = True) -> str:
    """28BYJ-48 from the shaft side; the cable leaves at the bottom."""
    o = []
    for sx in (-1, 1):
        ex = cxm + sx * (r + 9)
        sweep = 1 if sx > 0 else 0
        o.append(
            f'<path d="M{cxm + sx * (r - 6)},{cym - 9} L{ex},{cym - 7} A7,7 0 0 {sweep} '
            f'{ex},{cym + 7} L{cxm + sx * (r - 6)},{cym + 9} Z" fill="#ced4da" stroke="#868e96" '
            f'stroke-width="1"/>'
        )
        o.append(f'<circle cx="{ex}" cy="{cym}" r="2.8" fill="#fff" stroke="#868e96"/>')
    o.append(
        f'<rect x="{cxm - 15}" y="{cym + r - 10}" width="30" height="18" rx="2" fill="#4dabf7" '
        f'stroke="#1c7ed6"/>'
    )
    o.append(
        f'<circle cx="{cxm}" cy="{cym}" r="{r}" fill="#dee2e6" stroke="#868e96" '
        'stroke-width="1.4"/>'
    )
    o.append(f'<circle cx="{cxm}" cy="{cym - 8}" r="8" fill="#adb5bd" stroke="#868e96"/>')
    o.append(f'<rect x="{cxm - 2.5}" y="{cym - 13}" width="5" height="10" fill="#495057"/>')
    if label:
        o.append(t(cxm, cym + 17, "5VDC", 7.5, "#495057", "middle", "bold"))
    return "".join(o)


def motor_figure() -> str:
    o = [motor_drawing(70, 50, 38)]
    for i, c in enumerate(MOTOR_LEADS):
        x = 62 + i * 4
        o.append(
            f'<path d="M{x},96 C{x},118 {54 + i * 8},118 {54 + i * 8},140" stroke="{c}" '
            f'stroke-width="2.6" fill="none"/>'
        )
    o.append('<rect x="44" y="138" width="52" height="18" rx="2" fill="#f8f9fa" stroke="#868e96"/>')
    o.append(t(70, 174, "5-pin plug", 8.5, MUTED, "middle"))
    o.append(t(130, 44, "Label: 5VDC", 9, INK, "start", "bold"))
    o.append(t(130, 57, "(not the 12 V version)", 8.5, MUTED))
    o.append(t(130, 84, "Shaft off-centre,", 9, INK, "start", "bold"))
    o.append(t(130, 97, "double-D, 5 mm", 8.5, MUTED))
    o.append(t(130, 128, "Red lead: common +5 V", 8.5, MUTED))
    return svg("0 0 250 180", o)


def ky024_drawing(x: float, y: float, pitch: float = 24) -> str:
    """KY-024 with its pins AO, G, +, DO along the top edge at x, x+p, x+2p, x+3p."""
    bx0, bx1 = x - 22, x + 3 * pitch + 22
    hx = (bx0 + bx1) / 2
    o = [
        f'<rect x="{bx0}" y="{y - 10}" width="{bx1 - bx0}" height="70" rx="5" fill="#c92a2a" '
        f'stroke="#8f1d1d"/>',
        f'<rect x="{x + 8}" y="{y + 16}" width="22" height="22" rx="2" fill="#1c7ed6" '
        f'stroke="#1864ab"/>',
        f'<circle cx="{x + 19}" cy="{y + 27}" r="5" fill="#e9ecef"/>',
        f'<rect x="{x + 40}" y="{y + 18}" width="20" height="16" fill="#1b1f24"/>',
        f'<circle cx="{x + 3 * pitch - 2}" cy="{y + 24}" r="3.2" fill="#ffd43b" stroke="#b08900"/>',
        f'<path d="M{hx - 9},{y + 72} h18 v12 a9,6 0 0 1 -18,0 z" fill="#1b1f24"/>',
    ]
    o += [
        f'<line x1="{hx + dx}" y1="{y + 56}" x2="{hx + dx}" y2="{y + 72}" stroke="#9aa0a6" '
        f'stroke-width="1.6"/>'
        for dx in (-5, 0, 5)
    ]
    for i, name in enumerate(["AO", "G", "+", "DO"]):
        px = x + i * pitch
        o.append(
            f'<rect x="{px - 5}" y="{y - 5}" width="10" height="10" fill="#e6b325" '
            f'stroke="#9c7a12" stroke-width="0.8"/>'
        )
        o.append(t(px, y + 12, name, 7.8, "#fff", "middle", "bold"))
    return "".join(o)


def ky024_figure() -> str:
    o = [
        ky024_drawing(70, 50, 24),
        wire([(70, 45), (70, 14)], MOD["hall"], 3.6, dots=False),
        wire([(94, 45), (94, 14)], MOD["gnd"], 3.6, dots=False),
        wire([(118, 45), (118, 14)], MOD["nv"], 3.6, dots=False),
        t(70, 8, "A0", 8.5, MOD["hall"], "middle", "bold"),
        t(94, 8, "GND", 8.5, INK, "middle", "bold"),
        t(124, 8, "Nano 5V", 8.5, MOD["nv"], "middle", "bold"),
        t(200, 46, "DO: empty", 8.5, MUTED),
        t(36, 82, "pot:", 8, MUTED, "end"),
        t(36, 92, "unused", 8, MUTED, "end"),
        t(132, 140, "sensor, bent flat", 8.5, INK, "start", "bold"),
        t(132, 152, "into the floor pocket", 8.5, MUTED),
    ]
    return svg("0 0 280 160", o)


def nano_module_figure() -> str:
    return svg("0 0 450 182", nano(75, 25, 30, 150, MOD_RINGS_TOP, MOD_RINGS_BOT, "MODULE"))


def module_wiring() -> str:
    bd = Board(410)
    cx, ry, hole = bd.cx, bd.ry, bd.hole
    b = bd.b
    width, height = 950, 990
    o = bd.draw(
        [("motor 5 V", MOD["mv"]), ("GND", INK), ("Nano 5 V", MOD["nv"]), ("GND", INK)],
        labels_right=True,
    )
    o.append(nano(cx(7), bd.p, ry("d"), ry("h"), MOD_RINGS_TOP, MOD_RINGS_BOT, "MODULE"))

    def jumper(h: str, y_rail: float, color: str, label: str, ly: float) -> None:
        x, y = hole(h)
        o.append(wire([(x, y), (x, y_rail)], color))
        o.append(tag(x, ly, label, color, 8))

    jumper("a18", bd.top_minus, MOD["gnd"], "W1", (ry("a") + bd.top_minus) / 2 + 2)
    jumper("j18", bd.bot_plus, MOD["nv"], "W2", ry("j") + 22)
    jumper("j20", bd.bot_minus, MOD["gnd"], "W3", ry("j") + 34)

    hy = b - 86  # y of the ULN2003 header pins
    lanes = [b - 14, b - 30, b - 46, b - 62]
    board_top = b - 228

    def uln(
        in_xs: list[float], pwr: list[tuple[float, str]], title: str, motor: str
    ) -> tuple[float, float]:
        xs = [*in_xs, *(x for x, _ in pwr)]
        bx0, bx1 = min(xs) - 24, max(xs) + 24
        pins = [(x, f"IN{4 - i}") for i, x in enumerate(in_xs)] + pwr
        o.append(uln_board(bx0, board_top, bx1 - bx0, hy - board_top + 14, pins))
        o.append(jumper_cap((pwr[0][0] + pwr[1][0]) / 2, hy - 34))
        o.append(t((bx0 + bx1) / 2, board_top + 30, title, 10, "#fff", "middle", "bold"))
        mcx, mcy = (bx0 + bx1) / 2, board_top - 92
        o.append(motor_drawing(mcx, mcy, 32))
        for i, c in enumerate(MOTOR_LEADS):
            xa, xb = mcx - 8 + i * 4, mcx - 22 + i * 11
            o.append(
                f'<path d="M{xa},{mcy + 48} C{xa},{mcy + 70} {xb + 2.5},{mcy + 66} '
                f'{xb + 2.5},{board_top - 6}" stroke="{c}" stroke-width="2.6" fill="none"/>'
            )
        o.append(
            f'<rect x="{mcx - 30}" y="{board_top - 12}" width="60" height="9" rx="1.5" '
            f'fill="#f8f9fa" stroke="#868e96"/>'
        )
        o.append(t(mcx + 48, mcy - 4, motor, 10.5, INK, "start", "bold"))
        o.append(t(mcx + 48, mcy + 9, "28BYJ-48, 5 V", 9, MUTED))
        return mcx, mcy

    # IN4..IN1 left to right. Tilt: + at c1, - at c2. Yaw: - at c24, + at c25.
    tilt_in = [cx(3), cx(4), cx(5), cx(6)]
    yaw_in = [cx(19), cx(20), cx(21), cx(22)]
    tm = uln(tilt_in, [(cx(1), "+"), (cx(2), "&minus;")], "TILT driver", "tilt motor")
    ym = uln(yaw_in, [(cx(24), "&minus;"), (cx(25), "+")], "YAW driver", "yaw motor")
    o.append(tag(tm[0] + 42, tm[1] + 66, "M2", "#495057", 8.5))
    o.append(tag(ym[0] + 42, ym[1] + 66, "M1", "#495057", 8.5))

    names = ["in4", "in3", "in2", "in1"]
    # Tilt, IN4..IN1: D11 (c8), D9 (c10), D6 (c13), D7 (c12). IN1 and IN2 cross: IN1 is on D7.
    tilt_cols = (8, 10, 13, 12)
    tilt_ids = [
        "W11  D11 &rarr; IN4",
        "W10  D9 &rarr; IN3",
        "W9  D6 &rarr; IN2",
        "W8  D7 &rarr; IN1",
    ]
    for i, c in enumerate(tilt_cols):
        x, y = hole(f"a{c}")
        o.append(
            wire(
                [(x, y), (x, lanes[i]), (tilt_in[i], lanes[i]), (tilt_in[i], hy)],
                MOD[names[i]],
                r=6,
            )
        )
    # Yaw, IN4..IN1: D5 (c14), D4 (c15), D3 (c16), D2 (c17)
    yaw_cols = (14, 15, 16, 17)
    yaw_ids = ["W7  D5 &rarr; IN4", "W6  D4 &rarr; IN3", "W5  D3 &rarr; IN2", "W4  D2 &rarr; IN1"]
    for i, c in enumerate(yaw_cols):
        x, y = hole(f"a{c}")
        lane = lanes[3 - i]
        o.append(wire([(x, y), (x, lane), (yaw_in[i], lane), (yaw_in[i], hy)], MOD[names[i]], r=6))
    for i, c in enumerate(tilt_cols):
        o.append(tag((cx(c) + tilt_in[i]) / 2 + 2, lanes[i], tilt_ids[i], MOD_TEXT[names[i]], 8))
    for i, c in enumerate(yaw_cols):
        o.append(tag((cx(c) + yaw_in[i]) / 2 - 2, lanes[3 - i], yaw_ids[i], MOD_TEXT[names[i]], 8))

    # Driver power: straight down to the top rails
    o.append(wire([(cx(1), hy), (cx(1), bd.top_plus)], MOD["mv"]))
    o.append(wire([(cx(2), hy), (cx(2), bd.top_minus)], MOD["gnd"]))
    o.append(wire([(cx(24), hy), (cx(24), bd.top_minus)], MOD["gnd"]))
    o.append(wire([(cx(25), hy), (cx(25), bd.top_plus)], MOD["mv"]))
    o.append(tag(cx(1), b - 50, "W18", MOD["mv"], 8))
    o.append(tag(cx(2), b - 30, "W17", MOD["gnd"], 8))
    o.append(tag(cx(24), b - 30, "W19", MOD["gnd"], 8))
    o.append(tag(cx(25), b - 50, "W20", MOD["mv"], 8))

    # 5 V supply, top right
    sx0, sy0 = cx(27) + 2, b - 190
    o.append(
        f'<rect x="{sx0}" y="{sy0}" width="132" height="84" rx="8" fill="#e9ecef" stroke="#868e96" '
        f'stroke-width="1.5"/>'
    )
    o.append(t(sx0 + 66, sy0 + 34, "5 V supply", 11, INK, "middle", "bold"))
    o.append(t(sx0 + 66, sy0 + 50, "at least 1 A, separate", 8.5, MUTED, "middle"))
    gx, vx = cx(28), cx(29)
    o.append(
        f'<circle cx="{gx}" cy="{sy0 + 84}" r="6" fill="#25262b"/>'
        f'<circle cx="{vx}" cy="{sy0 + 84}" r="6" fill="#e03131"/>'
    )
    o.append(wire([(gx, sy0 + 90), (gx, bd.top_minus)], "#25262b", width=5.5))
    o.append(wire([(vx, sy0 + 90), (vx, bd.top_plus)], "#c92a2a", width=5.5))
    o.append(tag(gx - 4, b - 50, "V1 &minus;", "#25262b", 8))
    o.append(tag(vx + 6, b - 30, "V2 +", "#c92a2a", 8))

    # Tilt switch, top left: NO to b9 (D10) between rows a and b; C to the top GND rail
    sw_x, sw_y, ss = 6, b - 186, 0.75
    o.append(switch_drawing(sw_x, sw_y, ss, order=("NC", "NO", "C"), roller_left=False))
    no_x, c_x = sw_x + 50 * ss, sw_x + 80 * ss
    sb = sw_y + 52 * ss
    lane_ab = ry("a") + 12
    o.append(
        wire([(no_x, sb), (no_x, lane_ab), (cx(9), lane_ab), (cx(9), ry("b"))], MOD["sw"], r=6)
    )
    o.append(wire([(c_x, sb), (c_x, bd.top_minus), (cx(1), bd.top_minus)], MOD["gnd"], r=6))
    o.append(t(sw_x + 50 * ss, sw_y - 24, "tilt switch", 10, INK, "middle", "bold"))
    o.append(tag(no_x, b - 60, "W12", MOD_TEXT["sw"], 8))
    o.append(tag(c_x, b - 30, "W13", MOD["gnd"], 8))
    o.append(tag(cx(4.6), lane_ab, "W12  D10 &rarr; NO", MOD_TEXT["sw"], 8))

    # KY-024 below the board: AO to j10 (A0), G to the bottom GND rail, + to the Nano 5 V rail
    ky_y = b + 478
    o.append(ky024_drawing(cx(10), ky_y, bd.p))
    o.append(wire([(cx(10), ry("j")), (cx(10), ky_y)], MOD["hall"]))
    o.append(wire([(cx(11), bd.bot_minus), (cx(11), ky_y)], MOD["gnd"]))
    o.append(wire([(cx(12), bd.bot_plus), (cx(12), ky_y)], MOD["nv"]))
    o.append(tag(cx(10) - 32, ky_y - 22, "W14  A0 &rarr; AO", MOD["hall"], 8))
    o.append(tag(cx(13) + 26, ky_y - 30, "W15  G", MOD["gnd"], 8))
    o.append(tag(cx(13) + 30, ky_y - 14, "W16  +", MOD["nv"], 8))
    o.append(t(cx(14) + 6, ky_y + 30, "KY-024", 10.5, INK, "start", "bold"))
    o.append(t(cx(14) + 6, ky_y + 43, "DO and potentiometer unused", 9, MUTED))

    # USB to the Pi
    usb_y = (ry("d") + ry("h")) / 2
    ux = cx(7) - bd.p * 2.05
    o.append(
        f'<path d="{rpath([(ux, usb_y), (24, usb_y), (24, height - 72)], 10)}" fill="none" '
        f'stroke="#495057" stroke-width="6" stroke-linecap="round"/>'
    )
    o.append(t(32, usb_y - 8, "USB (module Nano)", 9.5, "#495057", "start", "bold"))
    o.append(
        f'<rect x="6" y="{height - 72}" width="196" height="64" rx="8" fill="#eef3f7" '
        f'stroke="{ACCENT}" stroke-width="1.5"/>'
    )
    o.append(t(104, height - 48, "Raspberry Pi", 12, INK, "middle", "bold"))
    o.append(t(104, height - 33, "USB: camera, rail Nano,", 9, MUTED, "middle"))
    o.append(t(104, height - 21, "module Nano", 9, MUTED, "middle"))
    o.append(
        t(
            cx(30) + 30,
            b + 452,
            "The top and bottom + rails are never joined.",
            9.5,
            MOD["mv"],
            "end",
            "bold",
        )
    )
    return svg(f"0 44 {width} {height - 44}", o)


def routing_figure() -> str:
    """Front view from the camera: -Y (tilt motor) left, +Y (bearing, switch) right."""
    ay = 120
    o = [
        '<rect x="120" y="300" width="360" height="16" rx="2" fill="#8d96a0"/>',
        '<rect x="90" y="316" width="420" height="10" rx="2" fill="#ced4da"/>',
        t(300, 342, "carriage", 9, MUTED, "middle"),
    ]
    for x0, w in ((150, 18), (432, 22)):
        o.append(
            f'<path d="M{x0},300 L{x0},{ay - 10} A{w / 2},{w / 2} 0 0 1 {x0 + w},{ay - 10} '
            f'L{x0 + w},300 Z" fill="#a9b1ba" stroke="#6b737c"/>'
        )
    o += [
        f'<rect x="112" y="{ay - 30}" width="38" height="60" rx="6" fill="#dee2e6" '
        'stroke="#868e96"/>',
        t(131, ay + 4, "tilt", 8.5, INK, "middle", "bold"),
        f'<rect x="454" y="{ay + 30}" width="8" height="40" fill="#a9b1ba"/>',
        f'<rect x="462" y="{ay + 36}" width="26" height="30" rx="3" fill="#3a3f47"/>',
        t(500, ay + 54, "switch", 8.5, INK, "start", "bold"),
        f'<rect x="176" y="{ay - 46}" width="14" height="196" rx="5" fill="#c3c9d0" '
        'stroke="#6b737c"/>',
        f'<rect x="410" y="{ay - 46}" width="14" height="196" rx="5" fill="#c3c9d0" '
        'stroke="#6b737c"/>',
        f'<rect x="176" y="{ay + 136}" width="248" height="14" rx="3" fill="#c3c9d0" '
        'stroke="#6b737c"/>',
        f'<rect x="424" y="{ay - 34}" width="22" height="5" fill="#495057"/>',
        f'<path d="M424,{ay - 60} h40 v40 h-40 z" fill="{MOD["sw"]}" fill-opacity="0.12" '
        f'stroke="{MOD["sw"]}" stroke-dasharray="3 2"/>',
        f'<rect x="268" y="{ay + 150}" width="64" height="30" rx="6" fill="#dee2e6" '
        'stroke="#868e96"/>',
        t(300, ay + 169, "yaw", 8.5, INK, "middle", "bold"),
        f'<rect x="214" y="{ay + 150}" width="40" height="8" fill="#c92a2a"/>',
        t(196, ay + 161, "KY-024", 8, INK, "end", "bold"),
        f'<rect x="270" y="{ay + 100}" width="60" height="36" rx="5" fill="#a9b1ba"/>',
        f'<path d="M292,{ay + 100} L300,{ay + 60} L308,{ay + 100} Z" fill="#a9b1ba"/>',
        f'<line x1="300" y1="{ay + 60}" x2="300" y2="{ay + 6}" stroke="#868e96" '
        'stroke-width="1.4"/>',
        f'<circle cx="300" cy="{ay}" r="5" fill="#495057"/>',
        f'<line x1="96" y1="{ay}" x2="520" y2="{ay}" stroke="{ACCENT}" stroke-width="1.2" '
        f'stroke-dasharray="7 4"/>',
        t(526, ay + 4, "tilt axis", 9, ACCENT, "start", "bold"),
    ]
    cab = "#e8590c"
    o.append(wire([(268, ay + 168), (200, ay + 168), (200, ay - 6)], cab, 3.4, dots=False, r=8))
    o.append(wire([(234, ay + 158), (234, ay + 162), (204, ay + 162)], cab, 2.4, dots=False, r=4))
    loop = (
        f"M200,{ay - 6} C200,{ay - 80} 120,{ay - 84} 104,{ay - 50} C98,{ay - 38} 100,{ay - 20} "
        f"100,{ay + 20} L100,300"
    )
    o.append(
        f'<path d="{loop}" fill="none" stroke="#000" stroke-opacity="0.3" stroke-width="5.4"/>'
    )
    o.append(f'<path d="{loop}" fill="none" stroke="{cab}" stroke-width="3.4"/>')
    o += [
        f'<rect x="194" y="{y}" width="12" height="4" rx="1" fill="#212529"/>'
        for y in (ay + 40, ay + 100)
    ]
    o.append(f'<rect x="94" y="{ay + 60}" width="12" height="4" rx="1" fill="#212529"/>')
    o.append(wire([(122, ay + 30), (122, 300)], "#868e96", 3, dots=False))
    o.append(wire([(488, ay + 60), (500, ay + 80), (500, 300)], "#868e96", 3, dots=False, r=6))
    o += [
        t(214, ay - 74, "slack loop over the axis", 9.5, cab, "start", "bold"),
        t(214, ay - 62, "(the cradle swings from &minus;33&#176; to +97&#176;)", 9, MUTED),
        t(88, ay + 66, "tie", 9, INK, "end", "bold"),
        t(214, ay + 74, "tied to", 9, INK, "start", "bold"),
        t(214, ay + 86, "the &minus;Y arm", 9, INK, "start", "bold"),
        t(470, ay - 66, "keep clear:", 9, MOD_TEXT["sw"], "start", "bold"),
        t(470, ay - 54, "flag bolt", 9, MOD_TEXT["sw"], "start", "bold"),
        t(150, 364, "&minus;Y: tilt motor side", 10, INK, "middle", "bold"),
        t(450, 364, "+Y: bearing and switch", 10, INK, "middle", "bold"),
        t(
            300,
            382,
            "Seen from the camera. The cables leave at the back (&minus;X).",
            9,
            MUTED,
            "middle",
        ),
    ]
    return svg("40 30 560 360", o)


MODULE_WIRES: list[tuple[str, str | None, str, str, str]] = [
    ("", None, "1. Board and jumpers", "", ""),
    (
        "P1",
        None,
        "Module Nano: rows d and h, columns 7&ndash;21",
        "",
        "D12 and D13 in column 7, USB left",
    ),
    ("P2", None, "Power jumpers on both ULN2003 boards", "", "the jumper next to &minus; +"),
    ("", None, "2. Wires", "", ""),
    ("W1", MOD["gnd"], "a18 (Nano GND, top row)", "top GND rail", "common ground with the motors"),
    ("W2", MOD["nv"], "j18 (Nano 5V)", "bottom + rail", "Nano 5 V, for the sensor only"),
    ("W3", MOD["gnd"], "j20 (Nano GND, bottom row)", "bottom GND rail", ""),
    ("W4", MOD["in1"], "a17 (D2)", "yaw IN1", ""),
    ("W5", MOD["in2"], "a16 (D3)", "yaw IN2", ""),
    ("W6", MOD["in3"], "a15 (D4)", "yaw IN3", ""),
    ("W7", MOD["in4"], "a14 (D5)", "yaw IN4", ""),
    ("W8", MOD["in1"], "a12 (D7)", "tilt IN1", "IN1 on D7"),
    ("W9", MOD["in2"], "a13 (D6)", "tilt IN2", "IN2 on D6: crosses W8"),
    ("W10", MOD["in3"], "a10 (D9)", "tilt IN3", "D8 stays free"),
    ("W11", MOD["in4"], "a8 (D11)", "tilt IN4", "D10 is the switch"),
    ("W12", MOD["sw"], "b9 (D10)", "tilt switch NO", "between rows a and b"),
    ("W13", MOD["gnd"], "top GND rail (column 1)", "tilt switch C", "NC stays empty"),
    ("W14", MOD["hall"], "j10 (A0)", "KY-024 AO", "the analogue pin, not DO"),
    ("W15", MOD["gnd"], "bottom GND rail", "KY-024 G", ""),
    ("W16", MOD["nv"], "bottom + rail (Nano 5 V)", "KY-024 +", ""),
    ("W17", MOD["gnd"], "tilt driver &minus;", "top GND rail (column 2)", ""),
    ("W18", MOD["mv"], "tilt driver +", "top + rail (column 1)", "motor 5 V"),
    ("W19", MOD["gnd"], "yaw driver &minus;", "top GND rail (column 24)", ""),
    ("W20", MOD["mv"], "yaw driver +", "top + rail (column 25)", "motor 5 V"),
    ("U1", MOD["usb"], "module Nano USB", "Raspberry Pi", "a data cable"),
    ("", None, "3. Last, with the 5 V supply unplugged", "", ""),
    ("M1", "#495057", "yaw motor plug", "yaw driver socket", "keyed"),
    ("M2", "#495057", "tilt motor plug", "tilt driver socket", "keyed"),
    ("V1", "#25262b", "5 V supply &minus;", "top GND rail (column 28)", ""),
    ("V2", "#c92a2a", "5 V supply +", "top + rail (column 29)", ""),
]


def legend(rows: list[tuple[str, str, str | None]]) -> str:
    out = ['<table class="legend"><tbody>']
    for pin, desc, color in rows:
        mark = swatch(color) if color else '<span class="sw" style="visibility:hidden"></span>'
        out.append(f'<tr><td class="nw">{mark}<strong>{pin}</strong></td><td>{desc}</td></tr>')
    return "".join(out) + "</tbody></table>"


PARTS: dict[str, Callable[[], str]] = {
    "rail_overview": rail_overview,
    "tmc_figure": tmc_figure,
    "nano_rail": nano_rail_figure,
    "nano_rail_legend": lambda: legend(
        [
            ("D2", "home switch (interrupt INT0)", RAIL["home"]),
            ("D3", "STEP", RAIL["step"]),
            ("D4", "DIR", RAIL["dir"]),
            ("D5", "EN, active low", RAIL["en"]),
            ("D7", "UART receive (direct)", RAIL["rx"]),
            ("D8", "UART transmit (through 1 k&Omega;)", RAIL["tx"]),
            ("5V", "logic supply", RAIL["v5"]),
            ("GND", "ground (both pins)", RAIL["gnd"]),
        ]
    ),
    "r1k": lambda: resistor_figure(R1K),
    "r10k": lambda: resistor_figure(R10K),
    "cap_figure": cap_figure,
    "rail_switch": lambda: switch_figure("D2", RAIL["home"]),
    "coil_figure": coil_figure,
    "breadboard": breadboard_figure,
    "rail_wiring": rail_wiring,
    "rail_wires": lambda: wire_table(RAIL_WIRES),
    "module_overview": module_overview,
    "uln_figure": uln_figure,
    "motor_figure": motor_figure,
    "ky024_figure": ky024_figure,
    "module_switch": lambda: switch_figure("D10", MOD["sw"]),
    "nano_module": nano_module_figure,
    "nano_module_legend": lambda: legend(
        [
            ("D2&ndash;D5", "yaw IN1, IN2, IN3, IN4", None),
            ("D7, D6, D9, D11", "tilt IN1, IN2, IN3, IN4", None),
            ("IN1", "D2 (yaw), D7 (tilt)", MOD["in1"]),
            ("IN2", "D3 (yaw), D6 (tilt)", MOD["in2"]),
            ("IN3", "D4 (yaw), D9 (tilt)", MOD["in3"]),
            ("IN4", "D5 (yaw), D11 (tilt)", MOD["in4"]),
            ("D10", "tilt switch NO", MOD["sw"]),
            ("A0", "KY-024 AO (analogue)", MOD["hall"]),
            ("5V", "KY-024 + only", MOD["nv"]),
            ("GND", "common ground (both pins)", MOD["gnd"]),
        ]
    ),
    "module_wiring": module_wiring,
    "module_wires": lambda: wire_table(MODULE_WIRES),
    "routing_figure": routing_figure,
}

# ------------------------------------------------------------------------------------------
# Pictures


def picture(src: str) -> str:
    """Copies a picture into build/img at print size; returns its path relative to build/."""
    if src.startswith("shot:"):
        file, box = SHOTS[src[5:]]
        out = BUILD / "img" / f"app-{src[5:]}.png"
        if not out.exists() or out.stat().st_mtime < (APP_SHOTS / file).stat().st_mtime:
            Image.open(APP_SHOTS / file).convert("RGB").crop(box).save(out, optimize=True)
        return f"img/{out.name}"
    path = (HERE / src).resolve()
    name = "-".join(path.relative_to(HERE.parent).with_suffix("").parts)
    out = BUILD / "img" / f"{name}.jpg"
    if not out.exists() or out.stat().st_mtime < path.stat().st_mtime:
        im = Image.open(path).convert("RGB")
        if im.width > MAX_IMAGE_PX:
            im = im.resize(
                (MAX_IMAGE_PX, round(im.height * MAX_IMAGE_PX / im.width)), Image.Resampling.LANCZOS
            )
        im.save(out, quality=86, optimize=True)
    return f"img/{out.name}"


# ------------------------------------------------------------------------------------------
# Assembly


@dataclass
class Section:
    num: str
    title: str
    page: int | None = None


def plain(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def number_headings(body: str) -> tuple[str, list[Section]]:
    sections: list[Section] = []
    h2 = h3 = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal h2, h3
        level, attrs, text = m.group(1), m.group(2), m.group(3)
        if level == "2":
            h2 += 1
            h3 = 0
            num = str(h2)
            sections.append(Section(num, plain(text)))
        else:
            h3 += 1
            num = f"{h2}.{h3}"
        return f'<h{level}{attrs} id="s{num}"><span class="num">{num}</span>{text}</h{level}>'

    return re.sub(r"<h([23])((?:\s[^>]*)?)>(.*?)</h\1>", repl, body, flags=re.S), sections


def contents(sections: list[Section]) -> str:
    rows = "".join(
        f'<tr><td class="n">{s.num}</td><td>{s.title}</td>'
        f'<td class="p">{s.page if s.page else ""}</td></tr>'
        for s in sections
    )
    return f'<div class="contents"><h2 class="toc">Contents</h2><table>{rows}</table></div>'


def render(guide: Guide, sections: list[Section] | None = None) -> tuple[str, list[Section]]:
    source = (HERE / guide.source).read_text(encoding="utf-8")

    def part(m: re.Match[str]) -> str:
        return PARTS[m.group(1)]()

    body = re.sub(r"\{\{(\w+)\}\}", part, source.replace("{{contents}}", "\0CONTENTS\0"))
    body = re.sub(r'src="([^"]+)"', lambda m: f'src="{picture(m.group(1))}"', body)
    body, found = number_headings(body)
    if sections:
        for s, known in zip(found, sections, strict=True):
            s.page = known.page
    body = body.replace("\0CONTENTS\0", contents(found))
    css = (HERE / "style.css").read_text(encoding="utf-8")
    footer = f'@page {{ @bottom-left {{ content: "{guide.footer}"; }} }}'
    doc = (
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
        f"<title>{guide.footer}</title><style>{css}\n{footer}</style></head><body>{body}</body></html>"
    )
    return doc, found


def find_browser() -> str:
    candidates = [
        "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    for name in ("msedge", "microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        if found := shutil.which(name):
            return found
    sys.exit("No Edge or Chrome found to print the PDF with.")


def print_pdf(browser: str, page: Path, pdf: Path) -> None:
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(  # noqa: S603
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-pdf-header-footer",
                f"--user-data-dir={profile}",
                "--virtual-time-budget=10000",
                f"--print-to-pdf={pdf}",
                page.as_uri(),
            ],
            check=True,
            capture_output=True,
        )


def section_pages(pdf: Path, sections: list[Section]) -> bool:
    """Fills in the page each section starts on, from the PDF's text. False without pdftotext."""
    tool = shutil.which("pdftotext")
    if not tool:
        return False
    text = subprocess.run(  # noqa: S603
        [tool, "-layout", "-enc", "UTF-8", str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    pages = text.split("\f")
    for s in sections:
        pattern = re.compile(rf"^\s*{re.escape(s.num)}\s+{re.escape(s.title)}\s*$", re.M)
        s.page = next((i + 1 for i, p in enumerate(pages) if i > 0 and pattern.search(p)), None)
    return True


def build(key: str, browser: str) -> Path:
    guide = GUIDES[key]
    (BUILD / "img").mkdir(parents=True, exist_ok=True)
    page = BUILD / f"{key}.html"
    pdf = HERE / guide.pdf
    doc, sections = render(guide)
    page.write_text(doc, encoding="utf-8")
    print_pdf(browser, page, pdf)
    if section_pages(pdf, sections):
        doc, _ = render(guide, sections)
        page.write_text(doc, encoding="utf-8")
        print_pdf(browser, page, pdf)
    return pdf


def main() -> None:
    keys = sys.argv[1:] or list(GUIDES)
    unknown = [k for k in keys if k not in GUIDES]
    if unknown:
        sys.exit(f"Unknown guide {unknown[0]!r}; choose from {', '.join(GUIDES)}.")
    browser = find_browser()
    for key in keys:
        print(build(key, browser).relative_to(HERE.parent.parent))


if __name__ == "__main__":
    main()
