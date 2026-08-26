#!/usr/bin/env bash

cli_init() {
    local spec="$1"
    shift

    CLI_SPEC="$spec"
    CLI_MODE="run"

    input=""
    output=""

    while IFS= read -r name; do
        local value
        value=$(jq -r --arg name "$name" \
            '.[$name].default // empty' <<< "$CLI_SPEC")

        if [[ -n "$value" ]]; then
            printf -v "$name" '%s' "$value"
        fi
    done < <(jq -r 'keys[]' <<< "$CLI_SPEC")

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                cli_help
                exit 0
                ;;

            --json)
                CLI_MODE="json"
                cli_json
                exit 0
                ;;

            --input)
                [[ $# -ge 2 ]] || cli_error "--input requires a value"
                input="$2"
                shift 2
                ;;

            --output)
                [[ $# -ge 2 ]] || cli_error "--output requires a value"
                output="$2"
                shift 2
                ;;

            --*)
                local name="${1#--}"

                if ! jq -e --arg name "$name" \
                    '.[$name]' <<< "$CLI_SPEC" >/dev/null
                then
                    cli_error "Unknown option: $1"
                fi

                local type
                type=$(jq -r --arg name "$name" \
                    '.[$name].type' <<< "$CLI_SPEC")

                case "$type" in
                    boolean)
                        printf -v "$name" '%s' true
                        shift
                        ;;

                    *)
                        [[ $# -ge 2 ]] || cli_error "$1 requires a value"
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

    [[ -n "$input" ]] || cli_error "--input is required"
    [[ -n "$output" ]] || cli_error "--output is required"
}

cli_help() {
    echo "Usage: $0 --input <file> --output <file> [OPTIONS]"
    echo
    echo "Common options:"
    echo "  --input <file>     Input file"
    echo "  --output <file>    Output file"
    echo "  --help, -h         Show this help"
    echo "  --json             Output parameter specification as JSON"
    echo
    echo "Profile options:"

    jq -r '
        to_entries[] |
        if .value.type == "boolean" then
            "  --\(.key)\t\(.value.description) (default: \(.value.default))"
        else
            "  --\(.key) <value>\t\(.value.description) (default: \(.value.default))"
        end
    ' <<< "$CLI_SPEC"
}

cli_json() {
    jq '
        {
            input: {
                type: "file",
                required: true,
                description: "Input file"
            },
            output: {
                type: "file",
                required: true,
                description: "Output file"
            },
            parameters: .
        }
    ' <<< "$CLI_SPEC"
}

cli_error() {
    echo "Error: $1" >&2
    echo "Use --help for usage." >&2
    exit 1
}
