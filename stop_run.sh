#!/bin/bash

# Check if PID file exists
if [ ! -f app.pid ]; then
    echo "PID file not found. Is the app running?"
    exit 1
fi

# Kill the process
PID=$(cat app.pid)
kill "$PID" && echo "App stopped." || echo "Failed to stop the app."

# Remove the PID file
rm -f app.pid