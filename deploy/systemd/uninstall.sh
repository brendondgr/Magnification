#!/usr/bin/env bash
#
# Remove the Magnification systemd user units (web app + daily search).
# Disables + stops the units and deletes the installed unit files.

set -euo pipefail

UNIT_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"

systemctl --user disable --now magnification-daily-search.timer 2>/dev/null || true
systemctl --user stop magnification-daily-search.service 2>/dev/null || true
systemctl --user disable --now magnification-web.service 2>/dev/null || true

rm -f "${UNIT_DIR}/magnification-daily-search.timer" \
      "${UNIT_DIR}/magnification-daily-search.service" \
      "${UNIT_DIR}/magnification-web.service"

systemctl --user daemon-reload
echo "Removed magnification-web.service + magnification-daily-search.{timer,service} from ${UNIT_DIR}."
