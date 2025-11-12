# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2025 ShiftLayer

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import signal
import threading
import time
import bittensor as bt


class GracefulShutdownManager:
    """
    Manages graceful shutdown signals and game state tracking for the validator.

    This class handles:
    - Signal-based communication with the auto-update script
    - Game state tracking (whether a game is currently active)
    - Graceful shutdown coordination
    """

    def __init__(self):
        self._shutdown_requested = False
        self._game_active = False
        self._lock = threading.Lock()
        self._shutdown_ready = threading.Event()
        self._signal_received = threading.Event()

        # Register signal handlers
        signal.signal(signal.SIGUSR1, self._handle_shutdown_signal)
        signal.signal(signal.SIGUSR2, self._handle_status_signal)

        bt.logging.info(
            "GracefulShutdownManager initialized - listening for SIGUSR1 (shutdown request) and SIGUSR2 (status request)"
        )

    def _handle_shutdown_signal(self, signum, frame):
        """Handle SIGUSR1 - shutdown request from auto-update script"""
        with self._lock:
            self._shutdown_requested = True
            self._signal_received.set()
        bt.logging.info("Received shutdown request signal (SIGUSR1)")
        bt.logging.info(f"Game active: {self._game_active}")

        if not self._game_active:
            # No game running, can shutdown immediately
            self._shutdown_ready.set()
            bt.logging.info("No active game - shutdown ready immediately")

    def _handle_status_signal(self, signum, frame):
        """Handle SIGUSR2 - status request from auto-update script"""
        with self._lock:
            game_active = self._game_active
            shutdown_requested = self._shutdown_requested

        bt.logging.info(f"Received status request signal (SIGUSR2)")
        bt.logging.info(
            f"Current status - Game active: {game_active}, Shutdown requested: {shutdown_requested}"
        )

        # The auto-update script can check our logs or we could write to a file
        # For now, it will parse our log output

    def is_shutdown_requested(self):
        """Check if shutdown has been requested"""
        with self._lock:
            return self._shutdown_requested

    def is_game_active(self):
        """Check if a game is currently active"""
        with self._lock:
            return self._game_active

    def set_game_active(self, active: bool):
        """Set whether a game is currently active"""
        with self._lock:
            old_state = self._game_active
            self._game_active = active

            if old_state != active:
                bt.logging.info(
                    f"Game state changed: {'Active' if active else 'Inactive'}"
                )

                # If game just ended and shutdown was requested, we're ready to shutdown
                if not active and self._shutdown_requested:
                    self._shutdown_ready.set()
                    bt.logging.info("Game ended - shutdown ready")

    def wait_for_shutdown_ready(self, timeout=None):
        """
        Wait for shutdown to be ready (no active game and shutdown requested).
        Returns True if shutdown is ready, False if timeout occurred.
        """
        return self._shutdown_ready.wait(timeout=timeout)

    def reset_shutdown_request(self):
        """Reset the shutdown request (useful for testing)"""
        with self._lock:
            self._shutdown_requested = False
            self._shutdown_ready.clear()
            self._signal_received.clear()
        bt.logging.info("Shutdown request reset")


# Global instance
_shutdown_manager = None


def get_shutdown_manager():
    """Get the global shutdown manager instance"""
    global _shutdown_manager
    if _shutdown_manager is None:
        _shutdown_manager = GracefulShutdownManager()
    return _shutdown_manager
