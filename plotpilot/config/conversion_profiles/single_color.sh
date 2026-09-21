#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")" &&
    pwd
)"

source "$SCRIPT_DIR/../../lib/cli.sh"

CLI_SPEC='
{
  "name": "single-color",
  "description": "Convert SVG to optimized single-color G-code",

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
      "description": "flip vertical axis"
    },

    "feed_rate": {
      "type": "number",
      "default": 3000,
      "description": "drawing feed rate"
    },

    "travel_height": {
      "type": "number",
      "default": 5,
      "description": "Z height used for travel moves"
    },

    "draw_height": {
      "type": "number",
      "default": 0,
      "description": "Z height used while drawing"
    }
  }
}
'

cli_init "$CLI_SPEC" "$@"

INPUT_TMP="$(mktemp --suffix=.svg)"
OUTPUT_TMP="$(mktemp --suffix=.gcode)"
CONFIG="$(mktemp --suffix=.toml)"

cleanup() {
    rm -f "$INPUT_TMP" "$OUTPUT_TMP" "$CONFIG"
}

trap cleanup EXIT

cli_read_input > "$INPUT_TMP"

# ------------------------------------------------------------
# Generate the vpype-gcode profile.
# ------------------------------------------------------------

cat > "$CONFIG" <<EOF
[gwrite.simple]
unit = "mm"
invert_y = ${flip_vertical}

document_start = """\
G21
G17
G90
"""

segment_first = """\
G00 Z${travel_height}
G00 X{x:.4f} Y{y:.4f}
G01 Z${draw_height} F1000
"""

segment = "G01 X{x:.4f} Y{y:.4f} Z${draw_height} F${feed_rate}\n"

line_end = """\
G00 Z${travel_height}
"""

document_end = """\
M5
G00 Z${travel_height}
G00 X0.0000 Y0.0000
M2
"""
EOF

# ------------------------------------------------------------
# SVG -> optimized single-color G-code.
#
# 1. linemerge       Join connected/nearby line segments
# 2. linesimplify    Reduce unnecessary points
# 3. linesort        Optimize path traversal order
# ------------------------------------------------------------

vpype --config "$CONFIG" \
    read "$INPUT_TMP" \
    linemerge --tolerance 0.1mm \
    linesimplify --tolerance 0.05mm \
    linesort \
    gwrite -p simple "$OUTPUT_TMP"

cli_write_file "$OUTPUT_TMP"
