#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")" &&
    pwd
)"

source "$SCRIPT_DIR/../../lib/cli.sh"

CLI_SPEC='
{
  "name": "text-to-svg",
  "description": "Render text using a vpype Hershey font",

  "input": {
    "type": "none"
  },

  "output": {
    "type": "svg",
    "transport": [
      "file",
      "stdout"
    ]
  },

  "parameters": {
    "font": {
      "type": "string",
      "default": "futural",
      "description": "vpype Hershey font"
    },

    "text": {
      "type": "string",
      "default": "",
      "description": "Text to render"
    },

    "size": {
      "type": "number",
      "default": 18,
      "description": "Text size"
    }
  }
}
'

cli_init "$CLI_SPEC" "$@"

OUTPUT_TMP="$(mktemp --suffix=.svg)"

cleanup() {
    rm -f "$OUTPUT_TMP"
}

trap cleanup EXIT

vpype \
    text \
        --font "$font" \
        --size "$size" \
        "$text" \
    write "$OUTPUT_TMP"

cli_write_file "$OUTPUT_TMP"
