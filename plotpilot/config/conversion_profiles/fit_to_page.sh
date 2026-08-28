#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")" &&
    pwd
)"

source "$SCRIPT_DIR/../../lib/cli.sh"

CLI_SPEC='
{
  "name": "fit-to-page",
  "description": "Scale and center an SVG to fit within a paper size and margin",

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
    "margin": {
      "type": "number",
      "default": 10,
      "description": "Margin around the artwork in mm"
    },

    "paper_size": {
      "type": "string",
      "default": "a4",
      "description": "Paper size. Supported sizes include a0, a1, a2, a3, a4, a5, a6, letter, legal, ledger, tabloid, ansi-a, ansi-b, ansi-c, ansi-d, ansi-e, arch-a, arch-b, arch-c, arch-d, arch-e, or a custom size such as 210x297mm"
    },

    "orientation": {
      "type": "string",
      "default": "portrait",
      "description": "Paper orientation: portrait or landscape"
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

case "$orientation" in
    portrait)
        ;;
    landscape)
        paper_size="${paper_size} landscape"
        ;;
    *)
        echo "Invalid orientation: $orientation" >&2
        echo "Expected: portrait or landscape" >&2
        exit 1
        ;;
esac

vpype \
    read "$INPUT_TMP" \
    layout --fit-to-margins "${margin}mm" "$paper_size" \
    write "$OUTPUT_TMP"

cli_write_file "$OUTPUT_TMP"
