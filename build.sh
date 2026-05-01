#!/usr/bin/env bash
set -euo pipefail

PLUGIN_JSON=".claude-plugin/plugin.json"
NAME=$(python3 -c "import json; print(json.load(open('$PLUGIN_JSON'))['name'])")
VERSION=$(python3 -c "import json; print(json.load(open('$PLUGIN_JSON'))['version'])")
OUTPUT="${NAME}-${VERSION}.plugin"

STAGING=$(mktemp -d)
trap "rm -rf '$STAGING'" EXIT

cp -r .claude-plugin scripts skills README.md CONNECTORS.md "$STAGING/"

(cd "$STAGING" && zip -r - . --exclude '*.DS_Store') > "$OUTPUT"

echo "Built: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
