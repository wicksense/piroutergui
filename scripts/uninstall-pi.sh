#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="piroutergui"
REPO_DIR="${REPO_DIR:-$HOME/piroutergui}"
REMOVE_APP_DIR="${REMOVE_APP_DIR:-false}"
REMOVE_STATE="${REMOVE_STATE:-false}"

echo "Stopping and disabling service..."
sudo systemctl disable --now "${SERVICE_NAME}.service" 2>/dev/null || true

if [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
  echo "Removing systemd unit..."
  sudo rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
fi

sudo systemctl daemon-reload

if [ "$REMOVE_STATE" = "true" ]; then
  echo "Removing managed state/backups..."
  sudo rm -rf "$REPO_DIR/state"
fi

if [ "$REMOVE_APP_DIR" = "true" ]; then
  echo "Removing app directory: $REPO_DIR"
  sudo rm -rf "$REPO_DIR"
else
  echo "Keeping app directory: $REPO_DIR"
fi

echo "Uninstall complete."
echo "Tip: run 'sudo systemctl status ${SERVICE_NAME}' to confirm it's gone."
