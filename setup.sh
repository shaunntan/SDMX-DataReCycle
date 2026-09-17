#!/usr/bin/env bash
# Sets up the Data Re-cycle webapp: installs frontend deps and creates the
# Python venv the backend scripts run in. See README.md for details and for
# manual steps this script does not cover (the `codex` CLI prerequisite).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Checking prerequisites"
command -v node >/dev/null 2>&1 || { echo "error: node is not installed (need Node.js 20+)" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "error: npm is not installed" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "error: python3 is not installed (need Python 3.12)" >&2; exit 1; }

if ! command -v codex >/dev/null 2>&1 && [ -z "${SDMX_CODEX_BIN:-}" ]; then
  echo "warning: no 'codex' CLI found on PATH and SDMX_CODEX_BIN is not set."
  echo "         AI review, export suggestions, and manual retry will fail"
  echo "         gracefully until this is set up; the rest of the app works."
fi

echo "==> Installing frontend dependencies (web/)"
(cd "$ROOT_DIR/web" && npm install)

echo "==> Setting up Python backend (PrototypeCodes/.venv)"
if [ ! -d "$ROOT_DIR/PrototypeCodes/.venv" ]; then
  python3 -m venv "$ROOT_DIR/PrototypeCodes/.venv"
fi
"$ROOT_DIR/PrototypeCodes/.venv/bin/pip" install --upgrade pip
"$ROOT_DIR/PrototypeCodes/.venv/bin/pip" install -r "$ROOT_DIR/PrototypeCodes/requirements.txt"

echo
echo "==> Setup complete."
echo "    Start the app with:"
echo "      cd web && npm run dev"
echo "    Then open http://localhost:3000"
