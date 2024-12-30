#!/bin/bash

# Define log and PID files
LOG_FILE="app.log"
PID_FILE="app.pid"
APP_NAME="app.py"

# Function to check if the app is already running
is_running() {
    # Look for any running process for app.py (exclude this script and grep)
    RUNNING_PID=$(pgrep -f "$APP_NAME" | grep -v $$ | grep -v grep | head -n 1)
    if [ -n "$RUNNING_PID" ]; then
        echo "App is already running with PID $RUNNING_PID."
        return 0
    fi
    return 1
}

# Check if the app is already running
if is_running; then
    exit 1
fi

# Start the app in the background using setsid
echo "Starting the app in the background..."
setsid python3 app.py > "$LOG_FILE" 2>&1 < /dev/null &

# Save the process ID (PID) to a file for later use
APP_PID=$!
echo $APP_PID > "$PID_FILE"
echo "App started with PID $APP_PID. Logs are in $LOG_FILE."