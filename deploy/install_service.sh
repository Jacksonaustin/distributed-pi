#!/usr/bin/env bash
# Optional: start this Pi's Lab 5 app automatically at boot (systemd).
#
# Usage, on the Pi, from the repo root:
#   sudo deploy/install_service.sh pi_a      (or pi_b)
#
# Afterwards:
#   sudo systemctl stop lab5-pi-a       stop it (the "stop the leader" tests)
#   sudo systemctl start lab5-pi-a      start it again
#   journalctl -u lab5-pi-a -f          watch its output
#   sudo systemctl disable --now lab5-pi-a   remove it from boot
set -euo pipefail

NODE="${1:?usage: sudo $0 pi_a|pi_b}"
case "$NODE" in
  pi_a|pi_b) ;;
  *) echo "node must be pi_a or pi_b" >&2; exit 1 ;;
esac

REPO="$(cd "$(dirname "$0")/.." && pwd)"
RUN_AS="${SUDO_USER:-$(whoami)}"
SERVICE="lab5-${NODE//_/-}"

if [ ! -x "$REPO/venv/bin/python" ]; then
  echo "No venv at $REPO/venv - create it first (see docs/lab5_running.md)" >&2
  exit 1
fi

cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=Lab 5 leader election (${NODE})
After=network-online.target
Wants=network-online.target

[Service]
User=${RUN_AS}
WorkingDirectory=${REPO}/src
Environment=PYTHONUNBUFFERED=1
ExecStart=${REPO}/venv/bin/python -m ${NODE}.lab5_app
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE}"
echo "Installed ${SERVICE}. Watch it with: journalctl -u ${SERVICE} -f"
