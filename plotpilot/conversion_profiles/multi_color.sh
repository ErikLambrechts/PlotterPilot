#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/../lib/cli.sh"

SPEC='
{
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
'

cli_init "$SPEC" "$@"

if [[ "$CLI_MODE" == "json" ]]; then
    exit 0
fi

python3 - "$input" "$output" "$pause_between_colors" "$scale" <<'PY'
import subprocess
import sys
from pathlib import Path

input_file = Path(sys.argv[1])
output_file = Path(sys.argv[2])

pause = sys.argv[3] == "true"
scale = float(sys.argv[4])

cmd = [
    "vpype",
    "read",
    str(input_file),
    "write",
    str(output_file),
]

result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
)

if result.returncode != 0:
    raise SystemExit(result.stderr)

if pause:
    text = output_file.read_text(encoding="utf-8")

    lines = text.splitlines()

    output = []

    for line in lines:
        output.append(line)

    output_file.write_text(
        "\n".join(output) + "\n",
        encoding="utf-8",
    )
PY
