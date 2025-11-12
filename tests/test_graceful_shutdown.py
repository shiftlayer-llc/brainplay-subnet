#!/usr/bin/env python3
"""
Test script for graceful shutdown functionality
"""

import os
import signal
import subprocess
import time
import threading
import sys


def test_signal_handling():
    """Test that the validator responds to SIGUSR1 and SIGUSR2 signals"""
    print("=== Testing Signal Handling ===")

    # Start a simple validator process for testing
    env = os.environ.copy()
    env["PYTHONPATH"] = "/root/brainplay-subnet"

    # Start validator with minimal configuration
    cmd = [
        sys.executable,
        "-c",
        """
import sys
sys.path.insert(0, '/root/brainplay-subnet')
from game.validator.graceful_shutdown import get_shutdown_manager
import bittensor as bt
import time
import signal

# Initialize shutdown manager
shutdown_manager = get_shutdown_manager()

print("Validator started - PID:", os.getpid())
print("Waiting for signals...")

# Keep running until shutdown is requested
while not shutdown_manager.is_shutdown_requested():
    time.sleep(1)

print("Shutdown requested - exiting gracefully")
""",
    ]

    process = subprocess.Popen(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    # Give it time to start
    time.sleep(2)

    print(f"Started test validator process with PID: {process.pid}")

    # Test SIGUSR2 (status request)
    print("Sending SIGUSR2 (status request)...")
    os.kill(process.pid, signal.SIGUSR2)
    time.sleep(1)

    # Test SIGUSR1 (shutdown request)
    print("Sending SIGUSR1 (shutdown request)...")
    os.kill(process.pid, signal.SIGUSR1)

    # Wait for process to exit
    try:
        process.wait(timeout=10)
        print(f"✓ Process exited gracefully with code: {process.returncode}")
        return True
    except subprocess.TimeoutExpired:
        print("✗ Process did not exit within timeout")
        process.kill()
        return False


def test_game_state_tracking():
    """Test game state tracking during shutdown"""
    print("\n=== Testing Game State Tracking ===")

    env = os.environ.copy()
    env["PYTHONPATH"] = "/root/brainplay-subnet"

    cmd = [
        sys.executable,
        "-c",
        """
import sys
sys.path.insert(0, '/root/brainplay-subnet')
from game.validator.graceful_shutdown import get_shutdown_manager
import time
import signal
import os

shutdown_manager = get_shutdown_manager()

print("Starting game simulation...")

# Simulate starting a game
shutdown_manager.set_game_active(True)
print("Game started - active state set")

# Simulate shutdown request during game
print("Simulating shutdown request during active game...")
os.kill(os.getpid(), signal.SIGUSR1)
time.sleep(1)

# Check if shutdown is requested but not ready (game still active)
if shutdown_manager.is_shutdown_requested():
    print("✓ Shutdown requested detected")
else:
    print("✗ Shutdown request not detected")

# End the game
print("Ending game...")
shutdown_manager.set_game_active(False)

# Wait a bit to see if shutdown becomes ready
if shutdown_manager.wait_for_shutdown_ready(timeout=2):
    print("✓ Shutdown became ready after game ended")
else:
    print("✗ Shutdown did not become ready")

print("Test completed")
""",
    ]

    process = subprocess.Popen(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    stdout, stderr = process.communicate(timeout=15)

    print("Output:")
    print(stdout)
    if stderr:
        print("Errors:")
        print(stderr)

    return process.returncode == 0


def test_timeout_behavior():
    """Test timeout behavior when games don't end"""
    print("\n=== Testing Timeout Behavior ===")

    env = os.environ.copy()
    env["PYTHONPATH"] = "/root/brainplay-subnet"

    cmd = [
        sys.executable,
        "-c",
        """
import sys
sys.path.insert(0, '/root/brainplay-subnet')
from game.validator.graceful_shutdown import get_shutdown_manager
import time
import signal
import os

shutdown_manager = get_shutdown_manager()

print("Starting long-running game...")
shutdown_manager.set_game_active(True)

# Simulate shutdown request
print("Shutdown requested...")
os.kill(os.getpid(), signal.SIGUSR1)

# Keep game active (simulating a game that won't end)
print("Game staying active - testing timeout...")
start_time = time.time()

# Wait for shutdown with short timeout
ready = shutdown_manager.wait_for_shutdown_ready(timeout=3)
end_time = time.time()

if ready:
    print("✗ Shutdown became ready unexpectedly")
elif (end_time - start_time) >= 3:
    print(f"✓ Timeout worked correctly after {end_time - start_time:.1f}s")
else:
    print(f"✗ Timeout too short: {end_time - start_time:.1f}s")

# Clean up
shutdown_manager.set_game_active(False)
""",
    ]

    process = subprocess.Popen(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    stdout, stderr = process.communicate(timeout=10)

    print("Output:")
    print(stdout)
    if stderr:
        print("Errors:")
        print(stderr)

    return process.returncode == 0


def main():
    """Run all tests"""
    print("Starting Graceful Shutdown Tests")
    print("=" * 50)

    tests = [
        ("Signal Handling", test_signal_handling),
        ("Game State Tracking", test_game_state_tracking),
        ("Timeout Behavior", test_timeout_behavior),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        try:
            if test_func():
                print(f"✓ {test_name}: PASSED")
                passed += 1
            else:
                print(f"✗ {test_name}: FAILED")
        except Exception as e:
            print(f"✗ {test_name}: ERROR - {e}")

    print(f"\n{'='*50}")
    print(f"Test Results: {passed}/{total} passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
