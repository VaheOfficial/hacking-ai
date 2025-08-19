#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

python3 -m pip install --upgrade pip wheel setuptools
python3 -m pip install -e .
python3 -m pip install pyinstaller

pyinstaller \
  --name hacking-ai \
  --onefile \
  --console \
  --paths src \
  src/hacking_ai/__main__.py

mkdir -p dist
mv "$PROJECT_ROOT"/dist/hacking-ai "$PROJECT_ROOT"/dist/hacking-ai || true

echo "Built binary at: $PROJECT_ROOT/dist/hacking-ai"