#!/usr/bin/env bash

# ============================================================
# PlotPilot shared CLI
#
# A profile supplies CLI_SPEC and calls:
#
#     cli_init "$CLI_SPEC" "$@"
#
# Universal transport:
#
#     --input FILE
#     --input -
#
#     --output FILE
#     --output -
#
# "-" means stdin/stdout.
#
# Profiles describe semantic data types independently from
# physical transport.
# ============================================================

set -euo pipefail

CLI_SPEC="${CLI_SPEC:-}"

CLI_MODE="run"

input="-"
output="-"

CLI_HAS_INPUT="false"
CLI_HAS_OUTPUT="false"

cli_error() {
    echo "Error: $*" >&2
    echo "Use --help for usage." >&2
    exit 1
}

cli_init() {
    local spec="$1"
    shift

    CLI_SPEC="$spec"

    if ! command -v jq >/dev/null 2>&1; then
        cli_error "jq is required"
    fi

    CLI_HAS_INPUT="$(
        jq -r '
            if .input == null then
                "false"
            else
                "true"
            end
        ' <<< "$CLI_SPEC"
    )"

    CLI_HAS_OUTPUT="$(
        jq -r '
            if .output == null then
                "false"
            else
                "true"
            end
        ' <<< "$CLI_SPEC"
    )"

    # --------------------------------------------------------
    # Initialize parameter defaults.
    # --------------------------------------------------------

    while IFS= read -r name; do

        [[ -n "$name" ]] || continue

        local has_default
        has_default="$(
            jq -r \
                --arg name "$name" \
                '
                if .parameters[$name] | has("default")
                then "true"
                else "false"
                end
                ' \
                <<< "$CLI_SPEC"
        )"

        if [[ "$has_default" == "true" ]]; then

            local value

            value="$(
                jq -r \
                    --arg name "$name" \
                    '.parameters[$name].default' \
                    <<< "$CLI_SPEC"
            )"

            printf -v "$name" '%s' "$value"

        fi

    done < <(
        jq -r '
            .parameters // {} |
            keys[]
        ' <<< "$CLI_SPEC"
    )

    # --------------------------------------------------------
    # Parse command line.
    # --------------------------------------------------------

    while [[ $# -gt 0 ]]; do

        case "$1" in

            --help|-h)

                CLI_MODE="help"
                cli_help
                exit 0
                ;;

            --json)

                CLI_MODE="json"
                cli_json
                exit 0
                ;;

            --input)

                [[ "$CLI_HAS_INPUT" == "true" ]] ||
                    cli_error "This profile does not accept input"

                [[ $# -ge 2 ]] ||
                    cli_error "--input requires a value"

                input="$2"

                shift 2
                ;;

            --output)

                [[ "$CLI_HAS_OUTPUT" == "true" ]] ||
                    cli_error "This profile does not produce output"

                [[ $# -ge 2 ]] ||
                    cli_error "--output requires a value"

                output="$2"

                shift 2
                ;;

            --*)

                local name="${1#--}"

                jq -e \
                    --arg name "$name" \
                    '
                    .parameters[$name] != null
                    ' \
                    <<< "$CLI_SPEC" \
                    >/dev/null ||
                    cli_error "Unknown option: $1"

                local type

                type="$(
                    jq -r \
                        --arg name "$name" \
                        '.parameters[$name].type' \
                        <<< "$CLI_SPEC"
                )"

                case "$type" in

                    boolean)

                        printf -v "$name" '%s' true
                        shift
                        ;;

                    *)

                        [[ $# -ge 2 ]] ||
                            cli_error "$1 requires a value"

                        printf -v "$name" '%s' "$2"

                        shift 2
                        ;;

                esac

                ;;

            *)

                cli_error "Unexpected argument: $1"

                ;;

        esac

    done

    # --------------------------------------------------------
    # Validate required parameters.
    # --------------------------------------------------------

    while IFS= read -r name; do

        [[ -n "$name" ]] || continue

        local required

        required="$(
            jq -r \
                --arg name "$name" \
                '
                if .parameters[$name].required == true
                then "true"
                else "false"
                end
                ' \
                <<< "$CLI_SPEC"
        )"

        if [[ "$required" == "true" ]]; then

            local value="${!name:-}"

            [[ -n "$value" ]] ||
                cli_error "--$name is required"

        fi

    done < <(
        jq -r '
            .parameters // {} |
            keys[]
        ' <<< "$CLI_SPEC"
    )
}

cli_json() {
    jq . <<< "$CLI_SPEC"
}

cli_help() {

    local name
    local description

    name="$(
        jq -r '.name // "PlotPilot tool"' <<< "$CLI_SPEC"
    )"

    description="$(
        jq -r '.description // empty' <<< "$CLI_SPEC"
    )"

    echo "Usage: $0 [OPTIONS]"
    echo

    echo "$name"

    if [[ -n "$description" ]]; then
        echo "$description"
    fi

    echo

    # --------------------------------------------------------
    # Input
    # --------------------------------------------------------

    if [[ "$CLI_HAS_INPUT" == "true" ]]; then

        local input_type

        input_type="$(
            jq -r '.input.type' <<< "$CLI_SPEC"
        )"

        echo "Input:"
        echo "  type: $input_type"
        echo "  --input FILE       Read from file"
        echo "  --input -          Read from stdin"
        echo

    else

        echo "Input:"
        echo "  none"
        echo

    fi

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    if [[ "$CLI_HAS_OUTPUT" == "true" ]]; then

        local output_type

        output_type="$(
            jq -r '.output.type' <<< "$CLI_SPEC"
        )"

        echo "Output:"
        echo "  type: $output_type"
        echo "  --output FILE      Write to file"
        echo "  --output -         Write to stdout"
        echo

    else

        echo "Output:"
        echo "  none"
        echo

    fi

    # --------------------------------------------------------
    # Parameters
    # --------------------------------------------------------

    if jq -e '
        (.parameters // {}) |
        length > 0
    ' <<< "$CLI_SPEC" >/dev/null; then

        echo "Parameters:"

        jq -r '
            .parameters |
            to_entries[] |
            (
                "  --" + .key +
                (
                    if .value.type == "boolean"
                    then ""
                    else " <value>"
                    end
                ) +
                "\t" +
                (.value.description // "") +
                (
                    if .value | has("default")
                    then " (default: " + (.value.default | tostring) + ")"
                    else ""
                    end
                )
            )
        ' <<< "$CLI_SPEC"

        echo

    fi
}

# ------------------------------------------------------------
# Read input.
#
# This is deliberately a transport primitive.
#
# A converter can do:
#
#     cli_read_input > "$tmp"
#
# regardless of whether the caller supplied a file or stdin.
# ------------------------------------------------------------

cli_read_input() {

    [[ "$CLI_HAS_INPUT" == "true" ]] ||
        cli_error "This profile has no input"

    if [[ "$input" == "-" ]]; then

        cat

    else

        [[ -f "$input" ]] ||
            cli_error "Input file does not exist: $input"

        cat "$input"

    fi
}

# ------------------------------------------------------------
# Write output.
#
# Usage:
#
#     some_command | cli_write_output
#
# The converter therefore does not need to know whether the
# destination is a file or stdout.
# ------------------------------------------------------------

cli_write_output() {

    [[ "$CLI_HAS_OUTPUT" == "true" ]] ||
        cli_error "This profile has no output"

    if [[ "$output" == "-" ]]; then

        cat

    else

        mkdir -p "$(dirname "$output")"

        cat > "$output"

    fi
}

# ------------------------------------------------------------
# Copy a generated file through the transport layer.
# ------------------------------------------------------------

cli_write_file() {

    local source="$1"

    [[ -f "$source" ]] ||
        cli_error "Generated output does not exist: $source"

    cat "$source" | cli_write_output
}
