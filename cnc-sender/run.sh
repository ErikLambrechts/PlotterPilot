#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -d ".venv" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing dependencies..."
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

echo
echo "Starting Plotbot CNC Sender"
echo
echo "Open:"
echo "  http://127.0.0.1:5000"
echo
echo "Machine:"
echo "  plotbot.local:23"
echo

python app.py
