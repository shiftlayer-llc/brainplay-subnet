# Graceful Shutdown Mechanism for Brainplay Validator

## Overview

This implementation adds a graceful shutdown mechanism to the Brainplay subnet validator that prevents forced restarts during active games. The solution uses Unix signals (SIGUSR1 and SIGUSR2) for communication between the auto-update script and the validator process.

## Problem Solved

Previously, the auto-update script would immediately restart the validator process when a new version was detected, potentially interrupting ongoing games. This could lead to:
- Incomplete games and lost game state
- Poor user experience for players
- Potential data inconsistencies

## Solution

The graceful shutdown mechanism implements a signal-based communication protocol:

1. **Signal-based Communication**: Uses SIGUSR1 for shutdown requests and SIGUSR2 for status requests
2. **Game State Tracking**: The validator tracks whether a game is currently active
3. **Coordinated Shutdown**: The auto-update script waits for games to complete before restarting
4. **Timeout Protection**: Includes a 5-minute timeout to prevent indefinite waiting

## Architecture

### Components

1. **GracefulShutdownManager** (`game/validator/graceful_shutdown.py`)
   - Handles signal reception and game state tracking
   - Provides thread-safe operations for game state changes
   - Manages shutdown coordination

2. **Modified Validator** (`neurons/validator.py`)
   - Integrates graceful shutdown checks in the main loop
   - Prevents new game creation when shutdown is requested
   - Tracks game start/end events

3. **Enhanced Forward Function** (`game/validator/forward.py`)
   - Sets game state to active when a game starts
   - Sets game state to inactive when a game ends
   - Checks for shutdown requests before starting new games

4. **Updated Auto-update Script** (`scripts/run_auto_validator.sh`)
   - Implements graceful restart logic
   - Sends shutdown request signals
   - Waits for validator readiness with timeout
   - Falls back to forced shutdown if graceful shutdown fails

### Signal Protocol

#### SIGUSR1 (Shutdown Request)
- **Sent by**: Auto-update script
- **Received by**: Validator process
- **Purpose**: Request graceful shutdown
- **Validator Response**: 
  - If no game active: Set shutdown ready immediately
  - If game active: Wait for game completion, then set shutdown ready

#### SIGUSR2 (Status Request)
- **Sent by**: Auto-update script (optional)
- **Received by**: Validator process
- **Purpose**: Query current status
- **Validator Response**: Log current game state and shutdown status

## Usage

### Starting the System

```bash
# Start the validator with auto-update monitoring
./scripts/run_auto_validator.sh

# With custom check interval (e.g., 10 minutes)
./scripts/run_auto_validator.sh --check-interval 600
```

### Monitoring

```bash
# Check process status
pm2 status

# View validator logs
pm2 logs brainplay_auto_validator

# View auto-update monitor logs
pm2 logs brainplay_update_monitor
```

### Testing the Mechanism

```bash
# Run the test suite
./scripts/test_graceful_shutdown.sh
```

## Implementation Details

### Game State Tracking

The validator tracks game state using these key points:

```python
# Game start (in forward function)
shutdown_manager.set_game_active(True)

# Game end (in forward function)
shutdown_manager.set_game_active(False)

# Shutdown check (in main loop)
if shutdown_manager.is_shutdown_requested():
    bt.logging.info("Shutdown requested - validator will exit")
    break
```

### Graceful Restart Process

The auto-update script implements this restart flow:

```bash
# 1. Request graceful shutdown
request_graceful_shutdown()  # Sends SIGUSR1

# 2. Wait for validator readiness
wait_for_graceful_shutdown()  # Up to 5 minutes

# 3. Force shutdown if timeout
force_shutdown()  # Fallback mechanism
```

### Error Handling

The implementation includes several safety mechanisms:

1. **Timeout Protection**: 5-minute maximum wait for graceful shutdown
2. **Fallback to Force Shutdown**: If graceful shutdown fails, force shutdown is used
3. **Process Monitoring**: Continuous monitoring of validator process status
4. **Rollback on Failure**: Automatic rollback if restart fails

## Configuration

### Timeout Settings

- **Graceful Shutdown Timeout**: 300 seconds (5 minutes)
- **Shutdown Check Interval**: 10 seconds
- **Status Check Frequency**: Every 30 seconds during wait

### Environment Variables

- `CHECK_INTERVAL`: Override default update check interval (default: 1200 seconds)

## Testing

The test suite (`scripts/test_graceful_shutdown.sh`) validates:

1. **Basic Graceful Shutdown**: Validator exits cleanly when no game is active
2. **Shutdown During Active Game**: Validator waits for game completion before exiting
3. **Status Signal Handling**: Validator responds correctly to status requests

## Logs and Debugging

### Key Log Messages

**Validator Logs:**
- `Shutdown requested - skipping game creation`
- `Game state changed: Active/Inactive`
- `Game ended - shutdown ready`
- `No active game - shutdown ready immediately`

**Auto-update Logs:**
- `Sending graceful shutdown request to validator`
- `Waiting for validator to be ready for shutdown`
- `Validator is ready for shutdown`
- `Graceful shutdown timeout - forcing restart`

### Debugging Commands

```bash
# Check recent validator logs for shutdown signals
pm2 logs brainplay_auto_validator --lines 20 --nostream | grep -E "(shutdown|game|signal)"

# Monitor real-time logs during update
pm2 logs brainplay_auto_validator --lines 0

# Check process signals
ps aux | grep validator
```

## Migration from Old System

If you're currently using the old auto-update script:

1. **Backup**: Create a backup of your current setup
2. **Update**: Replace the old script with the new one
3. **Restart**: Stop existing processes and start with the new script
4. **Verify**: Check logs to ensure graceful shutdown is working

```bash
# Stop existing processes
pm2 stop brainplay_auto_validator brainplay_update_monitor

# Start with new script
./scripts/run_auto_validator.sh
```

## Performance Impact

The graceful shutdown mechanism has minimal performance impact:

- **Signal Handling**: Negligible overhead (< 1ms per signal)
- **Game State Tracking**: Thread-safe operations with minimal locking
- **Memory Usage**: Small memory footprint for shutdown manager
- **CPU Usage**: No continuous polling - event-driven architecture

## Troubleshooting

### Common Issues

1. **Validator not responding to signals**
   - Check if validator process is running: `pm2 status`
   - Verify signal handlers are registered in logs
   - Check for process permission issues

2. **Graceful shutdown timeout**
   - Games may be taking longer than 5 minutes
   - Consider increasing timeout if needed
   - Check for stuck game states

3. **Auto-update script not detecting validator readiness**
   - Verify log parsing is working correctly
   - Check log format matches expected patterns
   - Ensure PM2 log access permissions

### Recovery Procedures

If the system gets stuck:

```bash
# Force stop all processes
pm2 stop all
pm2 delete all

# Clear logs if needed
pm2 flush

# Restart fresh
./scripts/run_auto_validator.sh
```

## Future Enhancements

Potential improvements for consideration:

1. **Multiple Game Support**: Handle multiple concurrent games
2. **Game Persistence**: Save game state for recovery after restart
3. **Configurable Timeouts**: Make shutdown timeout configurable
4. **Health Checks**: Add health monitoring for the mechanism itself
5. **Metrics**: Track graceful shutdown success rates and timing

## Security Considerations

- Signal handling is limited to the validator process
- No external network communication for shutdown coordination
- Process isolation maintained through PM2
- Log access restricted to authorized users

## Conclusion

This graceful shutdown mechanism provides a robust solution for preventing game interruptions during updates while maintaining the reliability and simplicity of the existing auto-update system. The signal-based approach ensures minimal overhead and maximum compatibility with the current PM2-based deployment architecture.