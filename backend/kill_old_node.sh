#!/bin/bash
# Helper script to kill any old P2P node processes

echo "Checking for running P2P nodes..."

# Find Python processes using our ports
PIDS=$(lsof -ti :8468 -ti :8469 -ti :8080 2>/dev/null | sort -u)

if [ -z "$PIDS" ]; then
    echo "✅ No P2P nodes running. Ports are free!"
    exit 0
fi

echo "Found processes using P2P ports:"
lsof -i :8468 -i :8469 -i :8080 2>/dev/null | grep Python

echo ""
read -p "Kill these processes? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    for PID in $PIDS; do
        echo "Killing process $PID..."
        kill -9 $PID 2>/dev/null
    done
    sleep 1
    echo "✅ Done! Ports should be free now."
else
    echo "Cancelled."
fi

