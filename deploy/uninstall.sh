#!/usr/bin/env bash
# Remove the MacroRail service. Config (~/.config/macrorail) and data
# (~/.local/share/macrorail) are kept; delete them by hand if wanted.
set -euo pipefail

unit=/etc/systemd/system/macrorail.service
if [[ -f "$unit" ]]; then
  sudo systemctl disable --now macrorail >/dev/null 2>&1 || true
  sudo rm "$unit"
  sudo systemctl daemon-reload
  echo "MacroRail service removed."
else
  echo "MacroRail service is not installed."
fi
