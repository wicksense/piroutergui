#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/piroutergui}"
REPO_URL="${REPO_URL:-https://github.com/wicksense/piroutergui.git}"
SERVICE_NAME="piroutergui"
RUN_USER="${SUDO_USER:-$USER}"

echo "[1/7] Installing system packages..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

echo "[2/7] Cloning/updating repository..."
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$REPO_DIR"
fi

echo "[3/7] Creating virtual environment..."
python3 -m venv "$REPO_DIR/.venv"


echo "[4/7] Installing Python dependencies..."
"$REPO_DIR/.venv/bin/pip" install --upgrade pip
"$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt"


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
