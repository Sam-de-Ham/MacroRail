# Guides

| PDF | Covers |
|---|---|
| [`MacroRail-build-guide.pdf`](MacroRail-build-guide.pdf) | The rail: parts and costs, printing, mechanical assembly, the breadboard controller (wire by wire), firmware, installing the app on the Pi, camera settings, first homing, a first stack, troubleshooting. |
| [`MacroRail-scan-module-guide.pdf`](MacroRail-scan-module-guide.pdf) | The optional scan module: parts and costs, printing and test pieces, assembly, wiring the module Nano, flashing, connecting, Module test, calibration, centring, scans, manual tilt, review and export, troubleshooting. |

## Rebuilding

```bash
uv run python docs/guides/build.py           # both
uv run python docs/guides/build.py rail      # or one: rail, module
```

- The text is in `rail.html` and `module.html`, the look in `style.css`. `build.py` adds the
  section numbers, the contents, the wiring drawings and wire tables (`{{name}}` in the text),
  and resized copies of the pictures, then prints with headless Edge or Chrome.
- It prints each guide twice so the contents get page numbers; that needs `pdftotext`
  (poppler). The intermediate HTML and pictures go to `build/`, which is not committed.
- Pictures: the renders in `img/rail/` and `img/module/` (made by `hardware/render/`), the
  product renders in `../images/` and the app screenshots in `../images/app/`.
- Keep the guides in step with `firmware/src/config.h`, `firmware-module/src/config.h`
  (pins, directions), `deploy/config.example.toml` and the app's labels. After a change,
  look at every page: figures and tables must not split, and headings must not end a page.
