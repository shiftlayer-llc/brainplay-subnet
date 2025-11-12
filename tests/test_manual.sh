#!/bin/bash
# Quick test script for manual testing of graceful shutdown with PM2

echo "=== Manual Testing Guide for Graceful Shutdown ==="
echo
echo "This script will help you test the graceful shutdown functionality"
echo "with your actual validator running under PM2."
echo

# Function to safely test graceful shutdown
test_graceful_shutdown() {
    echo "Step 1: Check if validator is running"
    if pm2 list | grep -q "brainplay_auto_validator"; then
        echo "✓ Validator is running under PM2"
        
        echo "Step 2: Get validator PID"
        VALIDATOR_PID=$(pm2 pid brainplay_auto_validator)
        echo "Validator PID: $VALIDATOR_PID"
        
        echo "Step 3: Send shutdown request signal (SIGUSR1)"
        kill -SIGUSR1 $VALIDATOR_PID
        echo "✓ Shutdown request sent"
        
        echo "Step 4: Monitor logs for graceful shutdown"
        echo "Watching logs for 10 seconds..."
        timeout 10 pm2 logs brainplay_auto_validator --lines 50
        
        echo "Step 5: Check if validator is still running"
        if pm2 list | grep -q "brainplay_auto_validator"; then
            echo "✓ Validator still running (expected - waiting for games to finish)"
        else
            echo "✗ Validator stopped (unexpected)"
        fi
        
    else
        echo "✗ Validator not running. Start it with:"
        echo "pm2 start scripts/run_auto_validator.sh"
    fi
}

# Function to test status request
test_status_request() {
    echo "=== Testing Status Request ==="
    
    if pm2 list | grep -q "brainplay_auto_validator"; then
        VALIDATOR_PID=$(pm2 pid brainplay_auto_validator)
        echo "Sending status request signal (SIGUSR2) to PID: $VALIDATOR_PID"
        kill -SIGUSR2 $VALIDATOR_PID
        echo "Check logs for status response..."
        sleep 2
        pm2 logs brainplay_auto_validator --lines 10 --nostream | grep "status"
    else
        echo "Validator not running"
    fi
}

echo "Choose a test option:"
echo "1. Test graceful shutdown signals"
echo "2. Test status request signal"
echo "3. Monitor current logs"
echo "4. Exit"
echo

read -p "Enter choice (1-4): " choice

case $choice in
    1)
        test_graceful_shutdown
        ;;
    2)
        test_status_request
        ;;
    3)
        echo "=== Current PM2 Status ==="
        pm2 list
        echo
        echo "=== Recent Logs ==="
        pm2 logs brainplay_auto_validator --lines 20 --nostream
        ;;
    4)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo
echo "=== Test Complete ==="
echo "To see full logs: pm2 logs brainplay_auto_validator"
echo "To restart validator: pm2 restart brainplay_auto_validator"
echo "To stop validator: pm2 stop brainplay_auto_validator"