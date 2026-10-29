#!/usr/bin/env bash
# Optional: start this Pi's election app automatically at boot (systemd).
# Every Pi runs the same shared app (python -m node); only the name differs.
#
# Usage, on the Pi, from the repo root:
#   sudo deploy/install_service.sh pi-a      (the node's name in cluster.json)
#
# Afterwards:
#   sudo systemctl stop election-pi-a       stop it (the "stop the leader" tests)
#   sudo systemctl start election-pi-a      start it again
#   journalctl -u election-pi-a -f          watch its output
#   sudo systemctl disable --now election-pi-a   remove it from boot
set -euo pipefail

NODE="${1:?usage: sudo $0 <node name, e.g. pi-a>}"
if ! [[ "$NODE" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]]; then
  echo "node name must be lowercase letters, digits and dashes" >&2; exit 1
fi

REPO="$(cd "$(dirname "$0")/.." && pwd)"
RUN_AS="${SUDO_USER:-$(whoami)}"
SERVICE="election-${NODE}"

if [ ! -x "$REPO/venv/bin/python" ]; then
  echo "No venv at $REPO/venv - create it first (see docs/lab5_running.md)" >&2
  exit 1
fi

cat > "/etc/systemd/system/${SERVICE}.service" <<EOF
[Unit]
Description=Leader election node (${NODE})
After=network-online.target
Wants=network-online.target

[Service]
User=${RUN_AS}
WorkingDirectory=${REPO}/src
Environment=PYTHONUNBUFFERED=1
ExecStart=${REPO}/venv/bin/python -m node --name ${NODE}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE}"
echo "Installed ${SERVICE}. Watch it with: journalctl -u ${SERVICE} -f"
