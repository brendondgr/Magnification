#!/usr/bin/env bash
#
# Remove the Magnification daily-search systemd user units.
# Disables + stops the timer/service and deletes the installed unit files.

set -euo pipefail

UNIT_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"

systemctl --user disable --now magnification-daily-search.timer 2>/dev/null || true
systemctl --user stop magnification-daily-search.service 2>/dev/null || true

rm -f "${UNIT_DIR}/magnification-daily-search.timer" \
      "${UNIT_DIR}/magnification-daily-search.service"

systemctl --user daemon-reload
echo "Removed magnification-daily-search.{timer,service} from ${UNIT_DIR}."
