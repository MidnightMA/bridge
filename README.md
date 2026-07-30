# Bale Messenger to Telegram Channel Bridge

A production-quality, asynchronous message bridge that automatically monitors updates from a specific **Bale Messenger channel** (via personal user account) and forwards supported content to a **Telegram channel** (via Telegram Bot API).

---

## Key Features

- **Personal Account Monitoring**: Uses a user account session rather than a Bale bot.
- **One-Way Forwarding**: Strict unidirectionality from Bale Channel to Telegram Channel.
- **Supported Formats**: Text, Photo (with caption), and Video (with caption).
- **Idempotency & Deduplication**: SQLite persistent storage prevents duplicate forwarding across restarts.
- **Auto Reconnection**: Exponential backoff reconnect logic for socket drops and API rate limits.
- **Resource Cleanup**: Automated temp file management for media uploads.

---

## Setup & Installation

### 1. Prerequisites
- Python 3.12+
- A personal Bale Messenger account
- A Telegram Bot token (from `@BotFather`) set as Admin in your Telegram channel

### 2. Installation Steps
```bash
git clone <repository_url> bridge
cd bridge

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment configuration file
cp .env.example .env
```

---

## Session / Login Instructions for Bale Account

Since the Bale client operates as a **userbot**, you must authenticate your personal account and obtain a session token (`BALE_SESSION`).

1. Open `.env` and configure your phone number:
   ```env
   BALE_PHONE_NUMBER=+989123456789
   ```

2. Run the interactive auth login helper:
   ```bash
   python bale_client.py --login
   ```

3. Enter the activation code sent to your Bale app / SMS when prompted.
4. The login tool will output your `BALE_SESSION` key. Copy and paste it into your `.env` file:
   ```env
   BALE_SESSION=ey...your_token_value_here
   ```

---

## Forwarding Pipeline Explanation

```text
[ Bale Channel ]
       │
       ▼ (BaleUserClient WebSocket Stream)
[ Parse Message ] ─── Filters out unsupported types (Voice, Audio, Polls, etc.)
       │
       ▼
[ MessageDeduplicator ] ─── Checks SQLite DB (processed_messages.db)
       │
       ├─── (If already forwarded) ──► Skip
       │
       ▼
[ Downloader ] ─── (If Photo/Video) Downloads media to temp_media/
       │
       ▼
[ TelegramClient ] ─── Uploads to Telegram via sendPhoto/sendVideo/sendMessage
       │
       ▼
[ SQLite DB ] ─── Marks Message ID as forwarded
       │
       ▼
[ Cleanup ] ─── Removes local temp file
```

---

## Running continuously with systemd on Linux

To ensure the service runs 24/7 and restarts automatically upon reboot or system failure:

1. Create a systemd service file:
   ```bash
   sudo nano /etc/systemd/system/bale-telegram-bridge.service
   ```

2. Add the following configuration (replace paths and user):
   ```ini
   [Unit]
   Description=Bale to Telegram Message Bridge
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/bridge
   ExecStart=/home/ubuntu/bridge/venv/bin/python main.py
   Restart=always
   RestartSec=10
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```

3. Reload systemd daemon, enable, and start service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable bale-telegram-bridge
   sudo systemctl start bale-telegram-bridge
   ```

4. Monitor status and logs:
   ```bash
   sudo systemctl status bale-telegram-bridge
   journalctl -u bale-telegram-bridge -f
   ```