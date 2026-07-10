#!/bin/bash

# --- Configuration ---
# Details for the server where the bot is running
REMOTE_USER="root"
REMOTE_HOST="your-bot-server-ip"
REMOTE_BOT_DIR="/path/to/GIT/book-club-bot"
REMOTE_DB_PATH="/app/data/bookclub.db"
REMOTE_BACKUP_PATH="/app/data/bookclub_backup.db"

# Local configuration on the backup machine
LOCAL_BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
LOCAL_BACKUP_FILE="${LOCAL_BACKUP_DIR}/bookclub_${TIMESTAMP}.db"

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
