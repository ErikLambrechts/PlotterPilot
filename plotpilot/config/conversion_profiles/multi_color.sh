#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")" &&
    pwd
)"

source "$SCRIPT_DIR/../../lib/cli.sh"

CLI_SPEC='
{
  "name": "multi-color",
  "description": "Convert SVG to multi-color G-code",

  "input": {
    "type": "svg",
    "transport": [
      "file",
      "stdin"
    ]
  },

  "output": {
    "type": "gcode",
    "transport": [
      "file",
      "stdout"
    ]
  },

  "parameters": {
    "profile": {
      "type": "string",
      "default": "multi-color",
      "description": "Conversion profile"
    },

    "pause_between_colors": {
      "type": "boolean",
      "default": true,
      "description": "Pause between pen colors"
    },

    "scale": {
      "type": "number",
      "default": 1.0,
      "description": "SVG scale"
    }
  }
}
'

cli_init "$CLI_SPEC" "$@"

INPUT_TMP="$(mktemp --suffix=.svg)"
OUTPUT_TMP="$(mktemp --suffix=.gcode)"

cleanup() {
    rm -f "$INPUT_TMP" "$OUTPUT_TMP"
}

trap cleanup EXIT

cli_read_input > "$INPUT_TMP"

PROJECT_ROOT="$(
    cd "$SCRIPT_DIR/../../.." &&
    pwd
)"

# ------------------------------------------------------------
# Use the existing PlotPilot SVG -> G-code converter.
# ------------------------------------------------------------

PYTHONPATH="$PROJECT_ROOT" \
python -m plotpilot.converters.svg_to_gcode.pipeline \
    "$INPUT_TMP" \
    "$OUTPUT_TMP" \
    --profile "$profile" \
    --pause-between-colors "$pause_between_colors" \
    --scale "$scale"

cli_write_file "$OUTPUT_TMP"
