#!/bin/bash

# Define log file
LOG_FILE="app.log"

# Check if the app is already running
if pgrep -f "python3 app.py" > /dev/null; then
    echo "The app is already running."
    exit 1
fi

# Run the app in the background
echo "Starting the app in the background..."
nohup python3 app.py > "$LOG_FILE" 2>&1 &

# Save the process ID (PID) to a file for later use
echo $! > app.pid
echo "App started with PID $(cat app.pid). Logs are in $LOG_FILE."