# Graceful Shutdown Testing Guide

## 🧪 Testing Your Graceful Shutdown Implementation

### ✅ Automated Tests (Already Passed!)

Your implementation passed all automated tests:
- ✅ **Signal Handling**: SIGUSR1 (shutdown) and SIGUSR2 (status) work correctly
- ✅ **Game State Tracking**: Games finish before shutdown proceeds
- ✅ **Timeout Behavior**: 5-minute timeout works as expected
- ✅ **Multi-Competition**: Both CLUE and GUESS competitions coordinate properly

### 🚀 Manual Testing with PM2

#### Option 1: Quick Manual Test Script
```bash
# Make the test script executable
chmod +x test_manual.sh

# Run the interactive test menu
./test_manual.sh
```

This gives you options to:
- Test graceful shutdown signals
- Test status request signals  
- Monitor current logs

#### Option 2: Full Real-World Test

**Step 1: Start Your Validator**
```bash
# Start your validator with PM2 (if not already running)
pm2 start scripts/run_auto_validator.sh

# Check it's running
pm2 list
```

**Step 2: Monitor Current Behavior**
```bash
# Watch the logs to see normal operation
pm2 logs brainplay_auto_validator --lines 50
```

**Step 3: Test Graceful Shutdown Signals**
```bash
# Get the validator PID
VALIDATOR_PID=$(pm2 pid brainplay_auto_validator)
echo "Validator PID: $VALIDATOR_PID"

# Send shutdown request signal
kill -SIGUSR1 $VALIDATOR_PID

# Watch logs for graceful shutdown behavior
pm2 logs brainplay_auto_validator --lines 30
```

**Step 4: Test Status Request**
```bash
# Send status request signal
kill -SIGUSR2 $VALIDATOR_PID

# Check logs for status response
pm2 logs brainplay_auto_validator --lines 10 | grep "status"
```

**Step 5: Simulate Real Update Scenario**
```bash
# Create a backup of current version
cp game/__init__.py game/__init__.py.backup

# Temporarily bump version to trigger update
sed -i 's/__version__ = "[0-9.]*"/__version__ = "999.9.9"/' game/__init__.py

# Watch logs - the auto-update script should detect the change
# and trigger graceful restart
pm2 logs brainplay_auto_validator --lines 100

# Restore original version when done
mv game/__init__.py.backup game/__init__.py
```

### 🔍 What to Look For in Logs

**Normal Operation:**
```
[CLUE] Starting game 1
[CLUE] Game 1 completed
[GUESS] Starting game 1
[GUESS] Game 1 completed
```

**Graceful Shutdown Requested:**
```
Received shutdown request signal (SIGUSR1)
Game active: true
[CLUE] Shutdown requested - stopping new games
[GUESS] Shutdown requested - stopping new games
Game ended - shutdown ready
```

**Status Request:**
```
Received status request signal (SIGUSR2)
Current status - Game active: false, Shutdown requested: true
```

### ⚡ Quick Verification Commands

```bash
# Check if validator is running
pm2 list | grep brainplay_auto_validator

# Get validator PID
pm2 pid brainplay_auto_validator

# View recent logs
pm2 logs brainplay_auto_validator --lines 20 --nostream

# Monitor logs in real-time
pm2 logs brainplay_auto_validator

# Restart validator if needed
pm2 restart brainplay_auto_validator
```

### 🎯 Success Criteria

Your graceful shutdown is working if:
1. ✅ Validator responds to SIGUSR1 with shutdown request acknowledgment
2. ✅ Active games complete before restart (no mid-game interruptions)
3. ✅ New games don't start after shutdown request
4. ✅ Both CLUE and GUESS competitions coordinate properly
5. ✅ Auto-update script waits for all games to finish before restart
6. ✅ 5-minute timeout works if games don't end naturally

### 🚨 Troubleshooting

**If signals don't work:**
- Check that the validator process is running
- Verify the PID is correct
- Check if signals are being blocked

**If games don't coordinate:**
- Check logs for both `[CLUE]` and `[GUESS]` prefixes
- Verify both competitions are running
- Check signal forwarding in the parent process

**If timeout doesn't work:**
- Check the 5-minute timeout configuration
- Verify the timeout logic in the auto-update script

### 🎉 You're Ready!

All tests pass and you have the tools to verify everything works. Your graceful shutdown implementation is robust and ready for production use!