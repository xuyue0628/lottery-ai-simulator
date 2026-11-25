#!/usr/bin/env bash

set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${LOTTERY_VENV_DIR:-"$PROJECT_DIR/.venv"}"
VENV_PYTHON="$VENV_DIR/bin/python"
SYSTEM_PYTHON="${PYTHON_BIN:-python3}"

cd "$PROJECT_DIR"

if [[ ! -x "$VENV_PYTHON" ]] || ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
    echo "Creating virtual environment: $VENV_DIR"
    if ! "$SYSTEM_PYTHON" -m venv "$VENV_DIR"; then
        if [[ ! -x "$VENV_PYTHON" ]] || ! "$SYSTEM_PYTHON" -m pip --version >/dev/null 2>&1; then
            echo "Failed to create the virtual environment." >&2
            echo "On Ubuntu/Debian, install the matching venv package first:" >&2
            echo "  sudo apt install python3.14-venv" >&2
            exit 1
        fi
        echo "Bootstrapping pip without ensurepip..."
        "$SYSTEM_PYTHON" -m pip --python "$VENV_PYTHON" install pip
    fi
fi

if ! "$VENV_PYTHON" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    echo "Installing Python dependencies..."
    "$VENV_PYTHON" -m pip install --upgrade pip
    "$VENV_PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt"
fi

export PYTHONPATH="$PROJECT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1
export LOTTERY_HOST="${LOTTERY_HOST:-127.0.0.1}"
export LOTTERY_PORT="${LOTTERY_PORT:-8765}"
export LOTTERY_OPEN_BROWSER="${LOTTERY_OPEN_BROWSER:-0}"

echo "Starting lottery dashboard: http://$LOTTERY_HOST:$LOTTERY_PORT"
exec "$VENV_PYTHON" "$PROJECT_DIR/launcher.py"
