## AdLinkFly Telegram URL Shortener Bot

A simple Telegram bot that shortens URLs using your AdLinkFly instance's API. Designed for easy deployment on an Ubuntu VPS.

### 1) Prerequisites
- Python 3.10+
- A Telegram bot token from BotFather
- AdLinkFly admin panel access and an API token

### 2) Configuration
Copy the sample environment file and edit it:

```bash
cp .env.example .env
```

Set the following variables in `.env`:
- `TELEGRAM_BOT_TOKEN`: The token from BotFather
- `ADLINKFLY_BASE_URL`: Your AdLinkFly base URL, e.g. `https://short.example.com`
- `ADLINKFLY_API_KEY`: Your AdLinkFly API key/token
- `ADLINKFLY_API_PATH`: Optional. Defaults to `/api`. Leave as default unless your API path differs.
- `ALLOWED_USER_IDS`: Optional. Comma-separated Telegram user IDs allowed to use the bot. Leave empty to allow everyone.

### 3) Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4) Run locally
```bash
python -m src.bot
```

### 5) Systemd service (Ubuntu)
Create a user for the bot (optional but recommended):
```bash
sudo adduser --system --home /opt/adlinkfly-bot --group adlinkfly-bot
```

Copy the project to `/opt/adlinkfly-bot` and set permissions:
```bash
sudo rsync -a --delete ./ /opt/adlinkfly-bot/
cd /opt/adlinkfly-bot
sudo chown -R adlinkfly-bot:adlinkfly-bot .
```

Create virtualenv and install deps:
```bash
sudo -u adlinkfly-bot bash -lc 'python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt'
```

Copy systemd unit and enable:
```bash
sudo cp systemd/adlinkfly-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now adlinkfly-bot
sudo systemctl status adlinkfly-bot -l
```

### 6) Usage
- Send `/start` or `/help` for instructions
- Send a URL directly to get a shortened link
- Or use `/short <url> [alias]`

### 7) Notes
- Retries with exponential backoff are used for network/transient errors
- If your AdLinkFly API uses a different pattern, adjust `ADLINKFLY_API_PATH` in `.env`
