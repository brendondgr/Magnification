#!/usr/bin/env bash
#
# Install the Magnification systemd *user* units:
#   * magnification-web.service            — the Flask web app (starts at boot)
#   * magnification-daily-search.service   — the LLM-gated daily scrape (oneshot)
#   * magnification-daily-search.timer     — boot + daily trigger for the scrape
#
# Renders the {{REPO_ROOT}} / {{PYTHON}} placeholders in the templates for THIS
# checkout, copies them into ~/.config/systemd/user/, reloads the user manager,
# and enables the web service + timer so they start at the next boot.
#
# Run this from the checkout you want the units to point at (normally the main
# checkout, after merging to main). Idempotent: safe to re-run.
#
# Usage:
#   deploy/systemd/install.sh          # install + enable (live next boot)
#   deploy/systemd/install.sh --now    # also start the web app in this session
#                                      # (the daily-search timer is never auto-
#                                      #  started, to avoid an immediate scrape)

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"
PYTHON="${REPO_ROOT}/.venv/bin/python"
UNIT_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"

START_NOW=0
[[ "${1:-}" == "--now" ]] && START_NOW=1

# --- Sanity checks -----------------------------------------------------------
if [[ ! -d "${REPO_ROOT}/utils/backend/scheduler" || ! -f "${REPO_ROOT}/app.py" ]]; then
  echo "ERROR: ${REPO_ROOT} does not look like the Magnification repo." >&2
  exit 1
fi
if [[ ! -x "${PYTHON}" ]]; then
  echo "ERROR: venv Python not found at ${PYTHON}" >&2
  echo "       Create it first, e.g.:  uv venv --python 3.13 && uv pip install --only-binary=:all: -r requirements.txt" >&2
  exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
  echo "ERROR: systemctl not found; this installer targets systemd user units." >&2
  exit 1
fi

echo "Repo root : ${REPO_ROOT}"
echo "Python    : ${PYTHON}"
echo "Unit dir  : ${UNIT_DIR}"

mkdir -p "${UNIT_DIR}"

render() {
  # render <template> <dest>
  sed -e "s|{{REPO_ROOT}}|${REPO_ROOT}|g" \
      -e "s|{{PYTHON}}|${PYTHON}|g" \
      "$1" > "$2"
  echo "  wrote $2"
}

echo "Rendering units..."
render "${HERE}/magnification-web.service"          "${UNIT_DIR}/magnification-web.service"
render "${HERE}/magnification-daily-search.service" "${UNIT_DIR}/magnification-daily-search.service"
render "${HERE}/magnification-daily-search.timer"   "${UNIT_DIR}/magnification-daily-search.timer"

echo "Reloading user manager..."
systemctl --user daemon-reload

echo "Enabling web service + daily-search timer..."
systemctl --user enable magnification-web.service
systemctl --user enable magnification-daily-search.timer

if [[ "${START_NOW}" == "1" ]]; then
  echo "Starting web app now (http://127.0.0.1:13374)..."
  systemctl --user restart magnification-web.service
  # NOTE: the daily-search timer is intentionally NOT started here — starting it
  # would fire OnBootSec immediately and could launch a scrape mid-session. It
  # activates at the next boot. To trigger a scrape now, run the service directly.
fi

echo
echo "Done. The web app and daily search are enabled and start at the next boot."
echo "Inspect with:"
echo "  systemctl --user status magnification-web.service"
echo "  systemctl --user list-timers magnification-daily-search.timer --all"
echo "  journalctl --user -u magnification-web.service -e"
echo
echo "Web app URL: http://127.0.0.1:13374"
echo "Probe the LLM gate without scraping:"
echo "  ${PYTHON} -m utils.backend.scheduler --check-llm ; echo exit=\$?"
echo "Force a scrape now (bypasses the once-per-day guard):"
echo "  ${PYTHON} -m utils.backend.scheduler --force"
