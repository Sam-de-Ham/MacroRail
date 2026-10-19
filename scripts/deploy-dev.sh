#!/usr/bin/env bash
# Development only: copy the committed HEAD to the Pi and (re)install it there.
#
#   scripts/deploy-dev.sh [ssh-host] [install.sh options]
#
# The Pi gets a clean copy in ~/macrorail; its virtualenv is kept between deploys.
set -euo pipefail

host="${1:-pi}"
shift || true
cd "$(git rev-parse --show-toplevel)"
if ! git diff --quiet HEAD; then
  echo "note: uncommitted changes are not deployed (HEAD $(git rev-parse --short HEAD) is)" >&2
fi

git archive --format=tar HEAD | ssh "$host" '
  set -e
  rm -rf ~/macrorail.new && mkdir ~/macrorail.new
  tar -x -C ~/macrorail.new
  if [ -d ~/macrorail/.venv ]; then mv ~/macrorail/.venv ~/macrorail.new/; fi
  rm -rf ~/macrorail && mv ~/macrorail.new ~/macrorail
'
ssh -t "$host" "~/macrorail/deploy/install.sh $*"
