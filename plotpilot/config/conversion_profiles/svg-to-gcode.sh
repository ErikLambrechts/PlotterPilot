#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$ROOT/../../.." && pwd)"
source "$PROJECT_ROOT/plotpilot/lib/cli.sh"

SPEC='
{
}
'

cli_init "$SPEC" "$@"

if [[ "$CLI_MODE" == "json" ]]; then
    exit 0
fi

PYTHONPATH="$PROJECT_ROOT" python -m plotpilot.converters.svg_to_gcode.pipeline \
    "$input" \
    "$output"
