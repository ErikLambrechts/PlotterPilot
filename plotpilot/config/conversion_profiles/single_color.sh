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
  "description": "Convert SVG to single-color G-code",

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
      "description": "feed rate"
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
vertical_flip = ${flip_vertical}

document_start = """\
G21
G17
G90
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

document_end = """\
M5
G0 Z5
G0 X0 Y0
M2
"""
EOF

# ------------------------------------------------------------
# SVG -> optimized single-color G-code.
# ------------------------------------------------------------

vpype --config "$CONFIG" \
    read "$INPUT_TMP" \
    linemerge --tolerance 0.1mm \
    linesimplify --tolerance 0.05mm \
    linesort \
    gwrite -p simple "$OUTPUT_TMP"

cli_write_file "$OUTPUT_TMP"
