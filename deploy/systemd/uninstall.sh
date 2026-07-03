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

# Remove the jobs/jobsctl management command.
rm -f "${HOME}/.local/bin/jobsctl" && echo "Removed ~/.local/bin/jobsctl."
BASHRC="${HOME}/.bashrc"
if [[ -f "${BASHRC}" ]] && grep -qF "# >>> magnification jobs command >>>" "${BASHRC}"; then
  # Delete the marked block (inclusive) plus a preceding blank line if present.
  sed -i '/# >>> magnification jobs command >>>/,/# <<< magnification jobs command <<</d' "${BASHRC}"
  echo "Removed 'jobs' shell function from ${BASHRC} (open a new shell to drop it)."
fi
