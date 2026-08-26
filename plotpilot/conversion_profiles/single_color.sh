#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/../lib/cli.sh"

SPEC='
{
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
'

cli_init "$SPEC" "$@"

if [[ "$CLI_MODE" == "json" ]]; then
    exit 0
fi

python3 - "$input" "$output" "$scale" <<'PY'
import sys
from pathlib import Path

input_file = Path(sys.argv[1])
output_file = Path(sys.argv[2])
scale = float(sys.argv[3])

try:
    import vpype
except ImportError:
    raise SystemExit(
        "vpype is required for this conversion profile"
    )

pipeline = [
    "read",
    str(input_file),
]

vpype_cli = [
    "vpype",
    "read",
    str(input_file),
    "write",
    str(output_file),
]

import subprocess

result = subprocess.run(
    vpype_cli,
    capture_output=True,
    text=True,
)

if result.returncode != 0:
    raise SystemExit(result.stderr)
PY
