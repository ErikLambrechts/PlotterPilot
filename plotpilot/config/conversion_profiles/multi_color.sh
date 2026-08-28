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
    "flip_vertical": {
      "type": "boolean",
      "default": "false",
      "description": "flip vertical access"
    },

    "pause_between_colors": {
      "type": "boolean",
      "default": true,
      "description": "Pause between pen colors"
    },

    "feed_rate": {
      "type": "number",
      "default": 3000,
      "description": "feed rate"
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

CONFIG="$(mktemp --suffix=.toml)"

cleanup() {
    rm -f "$INPUT_TMP" "$OUTPUT_TMP" "$CONFIG"
}

trap cleanup EXIT

cli_read_input > "$INPUT_TMP"

cat > "$CONFIG" <<EOF
[gwrite.colors]
unit = "mm"
vertical_flip = ${flip_vertical}

document_start = """\
G21
G17
G90
"""

layer_start = """\
; ========================================
; START COLOR: {vp_color}
; ========================================
G0 Z5
M5
"""

layer_join = """\
; ----------------------------------------
; COLOR CHANGE
; ----------------------------------------
G0 Z5
"""

line_start = """\
G0 Z5
G0 X{x:.4f} Y{y:.4f}
G1 Z0 F1000
"""

segment = "G1 X{x:.4f} Y{y:.4f} F${feed_rate}\n"

line_end = """\
G0 Z5
"""

layer_end = """\
; END COLOR: {vp_color}
G0 Z5
"""

document_end = """\
M5
G0 Z5
G0 X0 Y0
M2
"""
EOF

vpype --config "$CONFIG" \
    read "$INPUT_TMP" \
    linemerge --tolerance 0.1mm \
    linesimplify --tolerance 0.05mm \
    linesort \
    gwrite -p colors "$OUTPUT_TMP"

cli_write_file "$OUTPUT_TMP"


cli_write_file "$OUTPUT_TMP"
