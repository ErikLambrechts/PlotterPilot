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
    "profile": {
      "type": "string",
      "default": "single-color",
      "description": "Conversion profile"
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

# ------------------------------------------------------------
# The converter itself works on files.
#
# The CLI transport does not.
#
# This means:
#
#   file -> converter -> file
#
# and:
#
#   stdin -> temporary input -> converter -> stdout
#
# use exactly the same conversion implementation.
# ------------------------------------------------------------

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
#
# The profile-specific settings are passed through the
# existing conversion interface.
# ------------------------------------------------------------

PYTHONPATH="$PROJECT_ROOT" \
python -m plotpilot.converters.svg_to_gcode.pipeline \
    "$INPUT_TMP" \
    "$OUTPUT_TMP" \
    --profile "$profile" \
    --scale "$scale"

cli_write_file "$OUTPUT_TMP"
