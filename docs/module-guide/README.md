# Scan module wiring guide

`MacroRail-module-wiring-guide.pdf` is the illustrated electronics guide for the 3D scan module:
the parts, the module Nano's breadboard wiring with a wire-by-wire checklist, cable routing on
the module, flashing and configuring, the first power-up checks and troubleshooting. The rail's
own wiring is in the [setup guide](../setup-guide/MacroRail-setup-guide.pdf) and doesn't change.

It is generated from `build_html.py`. To rebuild it after a change:

```bash
python docs/module-guide/build_html.py
```

Then print `docs/module-guide/module-guide.html` to PDF from Chrome or Edge with A4 paper,
background graphics on, and headers and footers off. Or do it headless:

```bash
msedge --headless=new --no-pdf-header-footer --print-to-pdf=docs/module-guide/MacroRail-module-wiring-guide.pdf docs/module-guide/module-guide.html
```

The two photos on the cable-routing page come from `hardware/scan-module/guide/img/` (relative
paths), so print from the repository, not from a copy of the HTML file.

Keep it in step with `docs/protocol-module.md` (pins, directions, error codes) and
`firmware-module/src/config.h` (pin constants, `TILT_INVERT`, `YAW_INVERT`).
