#!/bin/bash

# This script is intended to be run from a BACKUP SERVER to pull a database backup 
# from the BOT SERVER.
#
# Prerequisite:
# - SSH key-based authentication must be set up from the backup server to the bot server.
#
# Usage:
#   ./remote_backup.sh [bot-name]
#
# Example:
#   ./remote_backup.sh my-book-club
#   (This will look for the bot in /root/my-book-club on the remote server)

# --- Configuration ---
# Details for the server where the bot is running
REMOTE_USER="root"
REMOTE_HOST="bot" # "your-bot-server-ip"
REMOTE_BOT_BASE_DIR="/root"
BOT_NAME="${1:-book-club-bot}"
REMOTE_BOT_DIR="${REMOTE_BOT_BASE_DIR}/${BOT_NAME}"
REMOTE_DB_PATH="/app/data/bookclub.db"
REMOTE_BACKUP_PATH="/app/data/bookclub_backup.db"

# Local configuration on the backup machine.
# Resolved relative to this script, not the caller's cwd — cron runs with a
# different working directory, which would otherwise scatter backups around.
# Override with BACKUP_DIR=/some/path to store them elsewhere.
LOCAL_BACKUP_DIR="${BACKUP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backups}"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
LOCAL_BACKUP_FILE="${LOCAL_BACKUP_DIR}/bookclub_${BOT_NAME}_${TIMESTAMP}.db"

# Create local backup directory if it doesn't exist
mkdir -p "${LOCAL_BACKUP_DIR}"

echo "Connecting to ${REMOTE_HOST} to create a safe database snapshot..."

# --- Step 1: Create a safe SQLite backup inside the running container on the remote server ---
# We use 'ssh' to execute the docker command remotely.
# The '-T' flag in docker compose is important for non-interactive shells.
ssh "${REMOTE_USER}@${REMOTE_HOST}" "cd ${REMOTE_BOT_DIR} && docker compose exec -T bot sqlite3 ${REMOTE_DB_PATH} \".backup '${REMOTE_BACKUP_PATH}'\""

if [ $? -ne 0 ]; then
    echo "Error: Failed to create backup on the remote server. Is the bot running?"
    exit 1
fi

# --- Step 2: Download the backup file from the remote server to the local machine ---
echo "Downloading the backup file..."
# The file inside the container at /app/data/bookclub_backup.db is mapped to ${REMOTE_BOT_DIR}/data/bookclub_backup.db on the host
scp "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_BOT_DIR}/data/bookclub_backup.db" "${LOCAL_BACKUP_FILE}"

if [ $? -ne 0 ]; then
    echo "Error: Failed to download the backup file via SCP."
    exit 1
fi

# --- Step 3: Cleanup the temporary backup file on the remote server ---
echo "Cleaning up temporary backup file on the remote server..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" "rm ${REMOTE_BOT_DIR}/data/bookclub_backup.db"

echo "------------------------------------------------"
echo "Backup successful!"
echo "Saved to: ${LOCAL_BACKUP_FILE}"
echo "------------------------------------------------"
