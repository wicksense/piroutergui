#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/piroutergui}"
REPO_URL="${REPO_URL:-https://github.com/wicksense/piroutergui.git}"
SERVICE_NAME="piroutergui"
RUN_USER="${SUDO_USER:-$USER}"
INSTALL_STATE_DIR="$REPO_DIR/.install-state"
REQ_HASH_FILE="$INSTALL_STATE_DIR/requirements.sha256"

hash_requirements() {
  sha256sum "$REPO_DIR/requirements.txt" | awk '{print $1}'
}

echo "[1/7] Installing system packages..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

echo "[2/7] Cloning/updating repository..."
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$REPO_DIR"
fi

echo "[3/7] Ensuring virtual environment..."
if [ ! -x "$REPO_DIR/.venv/bin/python" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$REPO_DIR/.venv"
else
  echo "Virtual environment already exists, reusing it."
fi

echo "[4/7] Installing Python dependencies (only when needed)..."
mkdir -p "$INSTALL_STATE_DIR"
NEW_HASH="$(hash_requirements)"
OLD_HASH=""
if [ -f "$REQ_HASH_FILE" ]; then
  OLD_HASH="$(cat "$REQ_HASH_FILE")"
fi

if [ "$NEW_HASH" != "$OLD_HASH" ]; then
  echo "requirements.txt changed (or first run) — installing deps..."
  "$REPO_DIR/.venv/bin/pip" install --upgrade pip
  "$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
  echo "$NEW_HASH" > "$REQ_HASH_FILE"
else
  echo "requirements.txt unchanged — skipping pip install."
fi

echo "[5/7] Installing systemd service..."
sudo cp "$REPO_DIR/scripts/piroutergui.service" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo sed -i "s|__WORKDIR__|$REPO_DIR|g" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo sed -i "s|__USER__|$RUN_USER|g" "/etc/systemd/system/${SERVICE_NAME}.service"

echo "[6/7] Enabling + starting service..."
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}.service"

echo "[7/7] Done."
echo "Service status:"
sudo systemctl --no-pager --full status "${SERVICE_NAME}.service" || true

echo "Open PiRouterGUI at: http://$(hostname -I | awk '{print $1}'):8080"
