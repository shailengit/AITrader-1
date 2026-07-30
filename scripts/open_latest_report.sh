#!/bin/bash
# Open the most recent run viewer report in the browser
REPORTS_DIR="$(dirname "$0")/../docs/reports"
LATEST=$(ls -t "$REPORTS_DIR"/batch_*.html 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
    echo "No batch reports found in $REPORTS_DIR"
    echo "Run a strategy first to generate a report."
    exit 1
fi
echo "Opening: $LATEST"
open "$LATEST"