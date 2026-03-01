#!/usr/bin/env bash
# build-report.sh - Build a self-contained HTML report from a terraform plan.log
# Usage: ./build-report.sh <plan.log> [output.html]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLAN_FILE="${1:?Usage: build-report.sh <plan.log> [output.html]}"
OUTPUT_FILE="${2:-terraform-plan-report.html}"

[[ -f "$PLAN_FILE" ]] || { echo "Error: File not found: $PLAN_FILE" >&2; exit 1; }
[[ -f "$SCRIPT_DIR/extract.sh" ]] || { echo "Error: extract.sh not found in $SCRIPT_DIR" >&2; exit 1; }
[[ -f "$SCRIPT_DIR/template.html" ]] || { echo "Error: template.html not found in $SCRIPT_DIR" >&2; exit 1; }

TMPJSON=$(mktemp /tmp/tf-plan-json.XXXXXX)
trap 'rm -f "$TMPJSON"' EXIT

echo "Extracting plan data from: $PLAN_FILE"
"$SCRIPT_DIR/extract.sh" "$PLAN_FILE" > "$TMPJSON"

# Validate JSON
if ! python3 -m json.tool "$TMPJSON" > /dev/null 2>&1; then
  echo "Warning: JSON validation failed, attempting to continue..." >&2
fi

echo "Building HTML report..."

# Use python3 with file-based approach - avoids shell quoting issues entirely
python3 -c "
import sys
with open(sys.argv[1]) as f:
    template = f.read()
with open(sys.argv[2]) as f:
    json_data = f.read().strip()
result = template.replace('__PLAN_DATA__', json_data, 1)
with open(sys.argv[3], 'w') as f:
    f.write(result)
" "$SCRIPT_DIR/template.html" "$TMPJSON" "$OUTPUT_FILE"

echo "Report generated: $OUTPUT_FILE"

# Open in browser on macOS
if [[ "$(uname)" == "Darwin" ]]; then
  open "$OUTPUT_FILE" 2>/dev/null || true
fi
