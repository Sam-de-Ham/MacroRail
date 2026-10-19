# Setup guide

`MacroRail-setup-guide.pdf` is the illustrated hardware guide: the parts, breadboard wiring
with a wire-by-wire checklist, flashing, installing and the first power-up checks.

It is generated from `build_html.py`. To rebuild it after a change:

```bash
python docs/setup-guide/build_html.py
```

Then print `docs/setup-guide/setup-guide.html` to PDF from Chrome or Edge with A4 paper,
background graphics on, and headers and footers off. Or do it headless:

```bash
msedge --headless=new --no-pdf-header-footer --print-to-pdf=docs/setup-guide/MacroRail-setup-guide.pdf docs/setup-guide/setup-guide.html
```
