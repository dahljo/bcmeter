#!/bin/bash
set -euo pipefail

if (( EUID != 0 )); then
  echo "Run with sudo."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt update -y
apt install -y git python3 python3-venv python3-pip ca-certificates

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

REPO_URL="https://github.com/dahljo/bcmeter.git"
REPO_DIR="$SCRIPT_DIR/.bcmeter_repo"
REPO_UPDATED=0

if [ "${1-}" = "update" ] || [ ! -f "$SCRIPT_DIR/install.py" ]; then
  if [ -d "$REPO_DIR/.git" ]; then
    git -C "$REPO_DIR" fetch --all --prune
    git -C "$REPO_DIR" reset --hard origin/main
  else
    rm -rf "$REPO_DIR"
    git clone --depth 1 --branch main "$REPO_URL" "$REPO_DIR"
  fi

  if [ ! -f "$REPO_DIR/install.py" ]; then
    echo "install.py missing in repo checkout."
    exit 2
  fi

  cp -f "$REPO_DIR/install.py" "$SCRIPT_DIR/install.py"
  REPO_UPDATED=1
fi

if [ "${1-}" = "update" ]; then
  BCMETER_REPO_UPDATED="$REPO_UPDATED" exec python3 "$SCRIPT_DIR/install.py" update "${@:2}"
else
  BCMETER_REPO_UPDATED="$REPO_UPDATED" exec python3 "$SCRIPT_DIR/install.py" "$@"
fi
