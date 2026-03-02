#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "Running terraform-plan-visualizer tests..."
echo ""
python3 -m unittest discover -s tests -p "test_*.py" -v
echo ""
echo "All tests passed."
