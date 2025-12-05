#!/bin/bash
# Helper script to start the P2P backend node
# This ensures the venv is properly activated

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Creating venv..."
    python3.12 -m venv venv
    echo "Installing dependencies..."
    venv/bin/python -m pip install -r requirements.txt
    echo "✅ Virtual environment created and dependencies installed!"
fi

# Use the venv Python directly (more reliable than activation)
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"

# Verify venv Python exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Error: venv Python not found at $VENV_PYTHON"
    exit 1
fi

# Run the CLI with all arguments passed to this script
exec "$VENV_PYTHON" cli.py "$@"

