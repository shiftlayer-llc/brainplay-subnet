#!/bin/bash

#==============================================================================
# BRAINPLAY SUBNET AUTO-VALIDATOR SCRIPT
#==============================================================================
# This script automatically runs and updates the Brainplay subnet validator
# with PM2 process management and continuous monitoring for updates.
#
# Features:
# - Automatic version checking and updates from GitHub
# - PM2 process management for persistent execution
# - Backup and rollback functionality
# - Configurable update intervals
# - Comprehensive logging
#==============================================================================

set -euo pipefail  # Exit on error, undefined vars, pipe failures

#==============================================================================
# GLOBAL CONFIGURATION
#==============================================================================

# Script paths and directories
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_DIR="$(dirname "$SCRIPT_DIR")"
readonly PYTHON_ENV="$REPO_DIR/venv"

# Default configuration
readonly DEFAULT_SCRIPT="neurons/validator.py"
readonly DEFAULT_VALIDATOR_PROC_NAME="brainplay_auto_validator"
readonly DEFAULT_MONITOR_PROC_NAME="brainplay_update_monitor"
readonly DEFAULT_CHECK_INTERVAL=1200  # 20 minutes
readonly DEFAULT_LOG_FILE="./logs/validator_auto_update.log"
readonly DEFAULT_BACKUP_DIR="./backups"
readonly VERSION_FILE="./game/__init__.py"
readonly VERSION_VAR="__version__"
readonly GITHUB_REPO="shiftlayer-llc/brainplay-subnet"

# Dynamically get the current git branch
get_current_branch() {
    if git rev-parse --git-dir >/dev/null 2>&1; then
        git branch --show-current 2>/dev/null || echo "main"
    else
        echo "main"
    fi
}

readonly GIT_BRANCH=$(get_current_branch)

# Runtime variables
script="$DEFAULT_SCRIPT"
validator_proc_name="$DEFAULT_VALIDATOR_PROC_NAME"
monitor_proc_name="$DEFAULT_MONITOR_PROC_NAME"
CHECK_INTERVAL="${CHECK_INTERVAL:-$DEFAULT_CHECK_INTERVAL}"
LOG_FILE="$DEFAULT_LOG_FILE"
BACKUP_DIR="$DEFAULT_BACKUP_DIR"

#==============================================================================
# UTILITY FUNCTIONS
#==============================================================================

# Strip quotes from a string
strip_quotes() {
    local input="$1"
    local stripped="${input#\"}"
    stripped="${stripped%\"}"
    echo "$stripped"
}

# Check if a package is installed on the system
check_package_installed() {
    local package_name="$1"
    local os_name=$(uname -s)
    
    case "$os_name" in
        "Linux")
            if dpkg-query -W -f='${Status}' "$package_name" 2>/dev/null | grep -q "installed"; then
                return 1
            else
                return 0
            fi
            ;;
        "Darwin")
            if brew list --formula | grep -q "^$package_name$"; then
                return 1
            else
                return 0
            fi
            ;;
        *)
            echo "Unknown operating system"
            return 0
            ;;
    esac
}

#==============================================================================
# LOGGING FUNCTIONS
#==============================================================================

# Main logging function with timestamps
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Ensure log directory exists before writing
    if [[ "$LOG_FILE" != "/dev/null" ]]; then
        mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
    fi
    
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

# Convenience logging functions
log_info() { log "INFO" "$@"; }
log_warn() { log "WARN" "$@"; }
log_error() { log "ERROR" "$@"; }
log_debug() { log "DEBUG" "$@"; }

#==============================================================================
# VERSION MANAGEMENT FUNCTIONS
#==============================================================================

# Check if version1 is less than or equal to version2
version_less_than_or_equal() {
    [ "$1" = "$(echo -e "$1\n$2" | sort -V | head -n1)" ]
}

# Check if version1 is less than version2
version_less_than() {
    [ "$1" = "$2" ] && return 1 || version_less_than_or_equal "$1" "$2"
}

# Calculate numerical difference between two versions
get_version_difference() {
    local tag1="$1"
    local tag2="$2"
    local version1=$(echo "$tag1" | sed 's/v//')
    local version2=$(echo "$tag2" | sed 's/v//')
    
    IFS='.' read -ra version1_arr <<< "$version1"
    IFS='.' read -ra version2_arr <<< "$version2"
    
    local diff=0
    for i in "${!version1_arr[@]}"; do
        local num1=${version1_arr[$i]}
        local num2=${version2_arr[$i]}
        
        if (( num1 > num2 )); then
            diff=$((diff + num1 - num2))
        elif (( num1 < num2 )); then
            diff=$((diff + num2 - num1))
        fi
    done
    
    strip_quotes "$diff"
}

# Read version value from local file
read_version_value() {
    local version_location="$VERSION_FILE"
    local version="$VERSION_VAR"
    
    while IFS= read -r line; do
        if [[ "$line" == *"$version"* ]]; then
            local value=$(echo "$line" | awk -F '=' '{print $2}' | tr -d ' ')
            strip_quotes "$value"
            return 0
        fi
    done < "$version_location"
    
    echo ""
}

# Check version value on GitHub
check_variable_value_on_github() {
    local repo="$1"
    local file_path="$2"
    local variable_name="$3"
    local url="https://api.github.com/repos/$repo/contents/$file_path?ref=$GIT_BRANCH"
    
    # Use curl with timeout
    local response=$(curl -s --max-time 30 "$url" 2>/dev/null)
    local curl_exit_code=$?
    
    if [[ $curl_exit_code -ne 0 ]]; then
        log_warn "Network error: Failed to connect to GitHub (curl exit code: $curl_exit_code)" >&2
        return 1
    fi
    
    if [[ -z "$response" ]]; then
        log_warn "Empty response from GitHub API" >&2
        return 1
    fi
    
    # Check for API errors
    if echo "$response" | jq -e '.message' >/dev/null 2>&1; then
        local error_msg=$(echo "$response" | jq -r '.message')
        log_warn "GitHub API error: $error_msg" >&2
        return 1
    fi
    
    # Extract and decode content
    local content=$(echo "$response" | tr -d '\n' | jq -r '.content' 2>/dev/null)
    
    if [[ "$content" == "null" || -z "$content" ]]; then
        log_error "File '$file_path' not found in repository" >&2
        return 1
    fi
    
    local decoded_content=$(echo "$content" | base64 --decode 2>/dev/null)
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to decode base64 content from GitHub" >&2
        return 1
    fi
    
    # Extract variable value using improved pattern
    local variable_value=$(echo "$decoded_content" | grep "^$variable_name[[:space:]]*=" | awk -F '=' '{print $2}' | tr -d ' ')
    
    if [[ -z "$variable_value" ]]; then
        log_error "Variable '$variable_name' not found in file '$file_path'" >&2
        return 1
    fi
    
    # Only output the cleaned version value to stdout
    strip_quotes "$variable_value"
    return 0
}

#==============================================================================
# BACKUP AND ROLLBACK FUNCTIONS
#==============================================================================

# Create a backup before updating
create_backup() {
    local backup_name="backup_$(date '+%Y%m%d_%H%M%S')"
    local backup_path="$BACKUP_DIR/$backup_name"
    
    log_info "Creating backup: $backup_name"
    mkdir -p "$backup_path"
    
    # Copy critical files and directories
    cp -r "$REPO_DIR/game" "$backup_path/" 2>/dev/null
    cp -r "$REPO_DIR/neurons" "$backup_path/" 2>/dev/null
    cp "$REPO_DIR/requirements.txt" "$backup_path/" 2>/dev/null
    cp "$REPO_DIR/setup.py" "$backup_path/" 2>/dev/null
    
    # Store current git commit hash and version
    cd "$REPO_DIR"
    git rev-parse HEAD > "$backup_path/commit_hash.txt" 2>/dev/null
    echo "$1" > "$backup_path/version.txt"
    
    if [[ $? -eq 0 ]]; then
        log_info "Backup created successfully at: $backup_path"
        echo "$backup_path"
        return 0
    else
        log_error "Failed to create backup"
        return 1
    fi
}

# Rollback from backup
rollback_from_backup() {
    local backup_path="$1"
    
    if [[ ! -d "$backup_path" ]]; then
        log_error "Backup directory not found: $backup_path"
        return 1
    fi
    
    log_warn "Rolling back from backup: $backup_path"
    pm2 stop "$validator_proc_name" 2>/dev/null
    
    cd "$REPO_DIR"
    
    # Reset to backed up commit if available
    if [[ -f "$backup_path/commit_hash.txt" ]]; then
        local commit_hash=$(cat "$backup_path/commit_hash.txt")
        log_info "Rolling back to commit: $commit_hash"
        git reset --hard "$commit_hash"
        
        if [[ $? -ne 0 ]]; then
            log_error "Failed to reset to backup commit"
            return 1
        fi
    fi
    
    # Restore files from backup
    cp -r "$backup_path/game" "$REPO_DIR/" 2>/dev/null
    cp -r "$backup_path/neurons" "$REPO_DIR/" 2>/dev/null
    cp "$backup_path/requirements.txt" "$REPO_DIR/" 2>/dev/null
    cp "$backup_path/setup.py" "$REPO_DIR/" 2>/dev/null
    
    # Reinstall dependencies
    if [[ -f "$backup_path/requirements.txt" ]]; then
        log_info "Reinstalling dependencies from backup..."
        "$PYTHON_ENV/bin/pip" install -r "$backup_path/requirements.txt"
    fi
    
    pm2 restart "$validator_proc_name"
    log_info "Rollback completed successfully"
    return 0
}

# Clean old backups (keep only last 5)
cleanup_old_backups() {
    log_debug "Cleaning up old backups..."
    cd "$BACKUP_DIR" 2>/dev/null || return 0
    
    local files_to_clean=$(ls -t 2>/dev/null | tail -n +6)
    if [ -n "$files_to_clean" ]; then
        echo "$files_to_clean" | xargs -r rm -rf 2>/dev/null
        log_debug "Old backups cleaned up"
    fi
}

#==============================================================================
# PM2 PROCESS MANAGEMENT
#==============================================================================

# Create PM2 configuration file
create_pm2_config() {
    local joined_args=$(printf "%s," "${args[@]}")
    joined_args=${joined_args%,}
    
    cat > app.config.js << EOF
module.exports = {
  apps : [{
    name: '$validator_proc_name',
    namespace: 'brainplay-validator',
    script: '$script',
    interpreter: '$PYTHON_ENV/bin/python',
    min_uptime: '5m',
    max_restarts: '5',
    args: [$joined_args]
  }]
}
EOF
}

# Run monitoring loop (when script is called with --monitor flag)
run_monitoring_loop() {
    local current_version=$(read_version_value)
    
    log_info "---------------------------------------------"
    log_info "Starting auto-update monitoring loop..."
    log_info "Process name: $monitor_proc_name"
    log_info "Check interval: $CHECK_INTERVAL seconds"
    log_info "---------------------------------------------"
    log_info "Current version: $current_version"
    
    while true; do
        log_info "******************************"
        log_info "Checking for updates..."
        
        # Check if we're in a git repository using git command
        if git rev-parse --git-dir >/dev/null 2>&1; then
            latest_version=$(check_variable_value_on_github "$GITHUB_REPO" "game/__init__.py" "$VERSION_VAR")

            log_info "Latest version: $latest_version"
            log_info "Current version: $current_version"
            
            if version_less_than $current_version $latest_version; then
                diff=$(get_version_difference $latest_version $current_version)
                if [ "$diff" -gt 0 ]; then
                    
                    log_info "==================================="
                    log_info "New version available!!!"
                    log_info "Version difference: $diff"
                    log_info "==================================="

                    # Create backup before updating
                    backup_path=$(create_backup "$current_version")
                    if [[ $? -ne 0 ]]; then
                        log_error "Failed to create backup. Skipping update for safety."
                        sleep $CHECK_INTERVAL
                        continue
                    fi
                    
                    # Pull latest changes
                    log_debug "Pulling latest changes from repository..."
                    if git pull origin $GIT_BRANCH; then
                        log_info "New version published. Updating the local copy."
                        
                        # Install dependencies
                        log_info "Installing updated dependencies..."
                        if ! "$PYTHON_ENV/bin/pip" install -e .; then
                            log_error "Failed to install dependencies. Rolling back..."
                            rollback_from_backup "$backup_path"
                            sleep $CHECK_INTERVAL
                            continue
                        fi
                        
                        # Restart PM2 process
                        log_info "Restarting PM2 process"
                        if ! pm2 restart $validator_proc_name; then
                            log_error "Failed to restart PM2 process. Rolling back..."
                            rollback_from_backup "$backup_path"
                            sleep $CHECK_INTERVAL
                            continue
                        fi
                        
                        # Verify process is running
                        sleep 5
                        if ! pm2 describe $validator_proc_name | grep -q "online"; then
                            log_error "Validator process failed to start properly. Rolling back..."
                            rollback_from_backup "$backup_path"
                            sleep $CHECK_INTERVAL
                            continue
                        fi
                        
                        # Update current version and cleanup
                        current_version=$(read_version_value)
                        log_info "Validator updated and restarted successfully!"
                        cleanup_old_backups
                    else
                        log_error "Git pull failed. Please stash local changes using 'git stash'."
                        rm -rf "$backup_path" 2>/dev/null
                    fi
                else
                    log_warn "Local version is newer than remote. Manual update required."
                fi
            else
                log_info "No update needed. Current version is up to date."
            fi
        else
            log_error "Not a Git installation. Please install from source."
        fi
        
        log_info "Next check in $CHECK_INTERVAL seconds ($((CHECK_INTERVAL/60)) minutes)..."
        sleep $CHECK_INTERVAL
    done
}

#==============================================================================
# ARGUMENT PARSING AND VALIDATION
#==============================================================================

# Parse command line arguments
parse_arguments() {
    local temp_args=()
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --check-interval)
                CHECK_INTERVAL="$2"
                shift 2
                ;;
            --log-file)
                LOG_FILE="$2"
                shift 2
                ;;
            --backup-dir)
                BACKUP_DIR="$2"
                shift 2
                ;;
            --internal-monitor)
                # Internal flag used by PM2 to run monitoring loop
                run_monitoring_loop
                exit 0
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                temp_args+=("$1")
                shift
                ;;
        esac
    done
    
    # Restore remaining arguments
    set -- "${temp_args[@]}"
}

# Show help message
show_help() {
    cat << EOF
Usage: $0 [OPTIONS] [VALIDATOR_ARGS...]

This script automatically starts a validator process and sets up continuous 
monitoring for updates. Both the validator and auto-update monitoring will 
run persistently in the background using PM2.

Options:
  --check-interval SECONDS    Set update check interval (default: 1200)
  --log-file PATH             Set log file path
  --backup-dir PATH           Set backup directory path
  --help, -h                  Show this help message

Environment Variables:
  CHECK_INTERVAL              Override default check interval

Examples:
  $0 --check-interval 600     # Check for updates every 10 minutes
  $0 --check-interval 300     # Check for updates every 5 minutes
  CHECK_INTERVAL=180 $0       # Check for updates every 3 minutes via env var

The script will automatically:
  - Start the validator process with PM2
  - Start the auto-update monitoring process with PM2
  - Monitor for code updates and restart the validator when needed
  - Create backups before updates and rollback on failures
EOF
}

# Validate configuration
validate_config() {
    if ! [[ "$CHECK_INTERVAL" =~ ^[0-9]+$ ]] || [[ "$CHECK_INTERVAL" -lt 60 ]]; then
        log_error "CHECK_INTERVAL must be a number >= 60 seconds"
        exit 1
    fi
    
    # Create directories
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
    mkdir -p "$BACKUP_DIR" 2>/dev/null || true
    
    # Verify log directory
    if [ ! -d "$(dirname "$LOG_FILE")" ]; then
        log_warn "Could not create log directory $(dirname "$LOG_FILE")"
        LOG_FILE="/dev/null"
    fi
}

# Check prerequisites
check_prerequisites() {
    # Check if jq is installed
    if ! command -v jq &> /dev/null; then
        log_error "Missing package 'jq'. Please install it first."
        log_info "On Ubuntu/Debian: sudo apt-get install jq"
        log_info "On macOS: brew install jq"
        exit 1
    fi
    
    # Check if pm2 is installed
    if ! command -v pm2 &> /dev/null; then
        log_error "pm2 not found. Please install pm2 first."
        log_info "See: https://pm2.keymetrics.io/docs/usage/quick-start/"
        exit 1
    fi
}

#==============================================================================
# MAIN EXECUTION
#==============================================================================

main() {
    # Change to repository directory
    cd "$REPO_DIR"
    
    # Parse arguments and validate configuration
    parse_arguments "$@"
    validate_config
    check_prerequisites
    
    log_info "Starting validator with auto-update functionality..."
    log_info "Configuration:"
    log_info "  Check interval: $CHECK_INTERVAL seconds ($((CHECK_INTERVAL/60)) minutes)"
    log_info "  Log file: $LOG_FILE"
    log_info "  Backup directory: $BACKUP_DIR"
    
    # Process validator arguments
    local args=()
    while [[ $# -gt 0 ]]; do
        local arg="$1"
        
        if [[ "$arg" == -* ]]; then
            if [[ $# -gt 1 && "$2" != -* ]]; then
                if [[ "$arg" == "--script" ]]; then
                    script="$2"
                    shift 2
                else
                    args+=("'$arg'" "'$2'")
                    shift 2
                fi
            else
                args+=("'$arg'")
                shift
            fi
        else
            args+=("'$arg'")
            shift
        fi
    done
    
    # Validate script argument
    if [[ -z "$script" ]]; then
        log_error "The --script argument is required."
        exit 1
    fi
    
    log_info "Watching branch: $GIT_BRANCH"
    log_info "PM2 process name: $validator_proc_name"
    
    # Get current version
    local current_version=$(read_version_value)
    
    # Stop existing PM2 process if running
    if pm2 status | grep -q "$validator_proc_name"; then
        log_info "Stopping existing PM2 process..."
        pm2 stop "$validator_proc_name"
        pm2 delete "$validator_proc_name"
    fi
    
    # Create and start PM2 configuration
    log_info "Creating PM2 configuration..."
    create_pm2_config
    cat app.config.js
    pm2 start app.config.js
    
    # Create and start monitoring process
    
    # Stop existing monitoring process
    if pm2 status | grep -q "$monitor_proc_name"; then
        log_info "Stopping existing monitoring process..."
        pm2 stop "$monitor_proc_name"
        pm2 delete "$monitor_proc_name"
    fi
    
    # Start monitoring process using this script with internal flag
    log_info "Starting auto-update monitoring as PM2 process: $monitor_proc_name"
    pm2 start "$0" --name "$monitor_proc_name" --namespace "brainplay-validator" --log "$LOG_FILE" -- --internal-monitor \
        --check-interval "$CHECK_INTERVAL" \
        --log-file "$LOG_FILE" \
        --backup-dir "$BACKUP_DIR"
    
    log_info "Setup complete!"
    log_info "Validator process: $validator_proc_name"
    log_info "Monitor process: $monitor_proc_name"
    log_info "Both processes are now running persistently with PM2"
    log_info ""
    log_info "To check status: pm2 status"
    log_info "To view logs: pm2 logs $validator_proc_name or pm2 logs $monitor_proc_name"
    log_info "To stop: pm2 stop $validator_proc_name $monitor_proc_name"
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi