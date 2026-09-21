#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")" &&
    pwd
)"

source "$SCRIPT_DIR/../../lib/cli.sh"

CLI_SPEC='
{
  "name": "page-layout",
  "description": "Scale and center an SVG on a page while preserving its aspect ratio",

  "input": {
    "type": "svg",
    "transport": [
      "file",
      "stdin"
    ]
  },

  "output": {
    "type": "svg",
    "transport": [
      "file",
      "stdout"
    ]
  },

  "parameters": {
    "page_size": {
      "type": "string",
      "default": "a4",
      "description": "page size, e.g. a4, a3, 210x297mm"
    },

    "orientation": {
      "type": "string",
      "default": "portrait",
      "description": "page orientation: portrait or landscape"
    },

    "border": {
      "type": "number",
      "default": 10,
      "description": "border around the drawing in millimeters"
    }
  }
}
'

cli_init "$CLI_SPEC" "$@"

INPUT_TMP="$(mktemp --suffix=.svg)"
OUTPUT_TMP="$(mktemp --suffix=.svg)"

cleanup() {
    rm -f "$INPUT_TMP" "$OUTPUT_TMP"
}

trap cleanup EXIT

cli_read_input > "$INPUT_TMP"

# ------------------------------------------------------------
# Build orientation arguments.
# ------------------------------------------------------------

ORIENTATION_ARGS=()

case "$orientation" in
    portrait)
        ;;
    landscape)
        ORIENTATION_ARGS+=(--landscape)
        ;;
    *)
        echo "Invalid orientation: $orientation (expected portrait or landscape)" >&2
        exit 1
        ;;
esac

# ------------------------------------------------------------
# SVG -> centered, proportionally scaled SVG.
# ------------------------------------------------------------

vpype \
    read "$INPUT_TMP" \
    layout \
        "${ORIENTATION_ARGS[@]}" \
        --fit-to-margins "${border}mm" \
        "$page_size" \
    write "$OUTPUT_TMP"

cli_write_file "$OUTPUT_TMP"
