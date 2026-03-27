```
pip install -r requirements.txt

ssh bot 'screen -dmS mysession bash -c "cd book-club-bot;
export BOT_TOKEN="your_token_from_BotFather";
export ADMIN_IDS="ID_1,ID_2";
.venv/bin/python3 bookclub_bot.py"'
```
