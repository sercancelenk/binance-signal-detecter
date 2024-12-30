#!/bin/bash

# Define log and PID files
LOG_FILE="app.log"
PID_FILE="app.pid"

# Function to check if the app is already running
is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        else
            echo "Stale PID file found. Cleaning up..."
            rm -f "$PID_FILE"
        fi
    fi
    return 1
}

# Check if the app is already running
if is_running; then
    echo "The app is already running with PID $(cat "$PID_FILE")."
    exit 1
fi

# Start the app in the background using setsid
echo "Starting the app in the background..."
setsid python3 app.py > "$LOG_FILE" 2>&1 < /dev/null &

# Save the process ID (PID) to a file for later use
APP_PID=$!
echo $APP_PID > "$PID_FILE"
echo "App started with PID $APP_PID. Logs are in $LOG_FILE."