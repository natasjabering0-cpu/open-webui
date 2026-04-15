#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/venv}"

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip wheel setuptools
python -m pip install -r backend/requirements.txt

npm install

if [[ "$ROOT_DIR" == *"("* || "$ROOT_DIR" == *")"* ]]; then
  SAFE_BUILD_DIR="$(mktemp -d /tmp/openwebui-build-XXXXXX)"
  trap 'rm -rf "$SAFE_BUILD_DIR"' EXIT
  rsync -a --delete \
    --exclude venv \
    --exclude .git \
    --exclude build \
    "$ROOT_DIR"/ "$SAFE_BUILD_DIR"/
  (
    cd "$SAFE_BUILD_DIR"
    SKIP_PYODIDE_FETCH=true npm run build
  )
  rm -rf "$ROOT_DIR/build"
  cp -a "$SAFE_BUILD_DIR/build" "$ROOT_DIR/build"
else
  SKIP_PYODIDE_FETCH=true npm run build
fi

mkdir -p data

echo
echo "Local installation ready."
echo "Start with:"
echo "  python run-local.py"
