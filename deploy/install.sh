#!/usr/bin/env bash
# Install (or update) MacroRail on a Raspberry Pi from this checkout.
#
#   deploy/install.sh                 install and start now and on every boot
#   deploy/install.sh --no-autostart  install only; start by hand when wanted
#
# Safe to run again after updating the checkout.
set -euo pipefail

autostart=1
case "${1:-}" in
  "") ;;
  --no-autostart) autostart=0 ;;
  *) echo "usage: $0 [--no-autostart]" >&2; exit 2 ;;
esac

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
user="$(id -un)"
config="$HOME/.config/macrorail/config.toml"
unit=/etc/systemd/system/macrorail.service

step() { printf '\n==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }

if ! command -v uv >/dev/null 2>&1; then
  step "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

step "Installing Python dependencies"
cd "$repo"
uv sync --frozen --no-dev

if [[ ! -f "$config" ]]; then
  step "Creating $config"
  mkdir -p "$(dirname "$config")"
  cp deploy/config.example.toml "$config"
fi

for group in dialout plugdev; do
  if ! id -nG "$user" | grep -qw "$group"; then
    warn "$user is not in the '$group' group; run: sudo usermod -aG $group $user (then log in again)"
  fi
done
if pgrep -f gvfs-gphoto2-volume-monitor >/dev/null 2>&1; then
  warn "gvfs-gphoto2-volume-monitor is running and may grab the camera; consider removing gvfs-backends"
fi

step "Installing the macrorail service"
sed -e "s|@USER@|$user|g" -e "s|@DIR@|$repo|g" deploy/macrorail.service | sudo tee "$unit" >/dev/null
sudo systemctl daemon-reload

host="$(hostname).local"
port="$(sed -n 's/^port *= *\([0-9]\+\).*/\1/p' "$config" | tail -n 1)"
url="http://$host:${port:-8000}"

if (( autostart )); then
  # A copy started by hand would hold the port, the controller and the camera.
  if pkill -f "^$repo/\.venv/bin/python"; then
    step "Stopped MacroRail that was started by hand"
    sleep 2
  fi
  sudo systemctl enable macrorail >/dev/null
  sudo systemctl restart macrorail
  step "MacroRail is running at $url and starts on boot"
  echo "    logs:            journalctl -u macrorail -f"
  echo "    stop autostart:  sudo systemctl disable --now macrorail"
else
  step "MacroRail is installed but not started"
  echo "    start now:        sudo systemctl start macrorail   (then open $url)"
  echo "    start on boot:    sudo systemctl enable --now macrorail"
fi
