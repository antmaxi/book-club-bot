# 📚 Book Club Telegram Bot

A bilingual (English/Russian) Telegram bot to help book clubs manage their reading lists, vote on upcoming books, and track their reading history.

## 🌟 Features

- **Bilingual Support:** Switch between English and Russian in the `/settings` menu.
- **Book Management:** Add books with details like title, author, page count, fiction/non-fiction status, review links, and descriptions.
- **Voting System:** Users can vote on books with three options:
  - ✅ **Want to read** (+1 point)
  - 😐 **Don't care** (0 points)
  - ❌ **Don't want to read** (-1 point)
- **Top Rated Books:** View a list of undiscussed books ranked by their average score and vote count.
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

## 🚀 Getting Started

### Prerequisites
- Python 3.12+
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Setup
1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd book-club-bot
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure and run the bot:**
   Use the following command to install dependencies and run the bot in a `screen` session on your server:
   ```bash
   pip install -r requirements.txt

   ssh bot 'screen -dmS prodsession bash -c "cd book-club-bot;
   export BOT_TOKEN="your_token_from_BotFather";
   export ADMIN_IDS="ID_1,ID_2";
   export ALLOWED_CHAT_ID="CHAT_ID";  # Optional: Restrict bot usage to members of this chat
   .venv/bin/python3 bookclub_bot.py"'
   ```

## 🧪 Testing

The project includes a suite of unit and integration tests using `unittest`.

To run all tests:
```bash
.venv/bin/python3 -m unittest discover tests
```

---
*Developed with love for Book Clubs.*
