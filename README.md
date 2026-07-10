# 📚 Book Club Telegram Bot

A bilingual (English/Russian) Telegram bot to help book clubs manage their reading lists, vote on upcoming books, and track their reading history.

## 🌟 Features

- **Bilingual Support:** Switch between English and Russian in the `/settings` menu.
- **Book Management:** Add books with details like title, author, page count, fiction/non-fiction status, review links, and descriptions.
- **Voting System:** Users can vote on books with three options:
  - ✅ **Want to read** (+1 point)
  - 😐 **Don't care** (+0.5 points)
  - ❌ **Don't want to read** (-1 point)
- **Top Rated Books:** View a list of undiscussed books ranked by their votes score.
- **Smart Notifications:** 
  - Get notified when a new book is added (with a 10-minute delay).
  - Notifications include a voting card to vote directly from the message.
  - Opt-in or out via `/settings`.
  - **Admin Notifications:** The main admin (first ID in `ADMIN_IDS`) receives notifications when the bot starts up or shuts down.
- **Access Control:** Optionally restrict bot usage to members of a specific Telegram chat (via `ALLOWED_CHAT_ID`). For this bot should be inside the chat too
- **Archive:** Track books that have already been discussed.

## 🛠 Commands

### User Commands
- `/start` or `/help`: Welcome message and command list.
- `/info`: About the bot and last update time.
- `/add`: Add a new book to the list.
- `/list`: See all undiscussed books (option to filter for unvoted only).
- `/top`: See the highest-rated books.
- `/settings`: Change your notification and language preferences.
- `/edit`: Edit a book's details (limited to book owner or admins).
- `/delete`: Delete a book (limited to book owner or admins).
- `/discussed`: View books already discussed by the club.
- `/cancel`: Abort the current interactive command.

### Admin Commands
- `/markdiscussed`: Mark a specific book as discussed (with a date).

## 🖼 Screenshots
![Top](screenshots/2026-04-04_screenshot_top.png)
![List](screenshots/2026-04-04_screenshot_list.png)
![Settings](screenshots/2026-04-04_screenshot_settings.png)

## 🚀 Getting Started

### Prerequisites
- Docker and Docker Compose
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Setup
1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd book-club-bot
   ```

2. **Configure environment variables:**
   Create a `.env` file in the project root with the following content:
   ```env
   BOT_TOKEN="your_token_from_BotFather"
   ADMIN_IDS="ID_1,ID_2"
   GITHUB_REPO="https://github.com/yourusername/your-repo"
   ALLOWED_CHAT_ID="CHAT_ID"  # Optional: Restrict bot usage to members of this chat
   ```

3. **Run the bot using Docker:**
   ```bash
   mkdir -p data
   docker compose up -d
   ```

(if not yet installed before, install docker as in https://docs.docker.com/engine/install/ubuntu/)

## 🛡️ Backups

To ensure your data is safe, a backup script is provided in `scripts/remote_backup.sh`. It creates a "safe" snapshot of the SQLite database while the bot is running to avoid corruption.


### Off-site Backups (Pulling from another machine)

If you want to run the backup from a **different Linux machine** (e.g., a dedicated backup server), use `scripts/remote_backup.sh`. This script connects to your bot server via SSH, triggers a safe backup, and pulls the file back to the local machine.

1.  **Copy the script** to your backup machine.
2.  **Configure the variables** inside `scripts/remote_backup.sh` (IP address, user, paths).
3.  **Ensure SSH Key-based authentication** is set up between the machines for automation.
4.  **Run it:** `./remote_backup.sh`

### Regular Backups (Recommended)
Add a cron job to run the backup daily at 2:00 AM:
1. Open crontab: `crontab -e`
2. Add the following line (adjust the path to your bot directory):
   ```cron
   0 2 * * * /bin/bash /path/to/remote_backup.sh >> /path/to/book-club-bot/logs/backup.log 2>&1
   ```

## 🧪 Testing

The project includes a suite of unit and integration tests.

To run tests using Docker:
```bash
docker compose run --rm bot python -m unittest discover tests
```

### Git Pre-commit Hook

To ensure tests pass before every commit, a Git pre-commit hook has been added. It automatically runs the test suite using Docker.

If you need to install it manually on another machine:
1. Create `.git/hooks/pre-commit` with the following content:
```bash
#!/bin/bash
docker compose run --rm bot python -m unittest discover tests
```
2. Make it executable: `chmod +x .git/hooks/pre-commit`

Or manually in a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover tests
```
