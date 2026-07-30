# Bale to Telegram Channel Mirror

A production-quality Python 3.11+ application that mirrors text, photo, and video messages from a **Bale channel** to a **Telegram channel** in real time.

The application operates as a **real user account on Bale** (via `aiobale`) and posts updates to Telegram using the official **Telegram Bot API**.

---

## Features

- 👤 **Bale Userbot**: Logs into a real Bale account using phone number and session file.
- 🤖 **Telegram Bot Integration**: Posts messages directly to your Telegram channel.
- 📷 **Full Media Support**: Forwards plain text, photos (with captions), and videos (with captions).
- 🚫 **Media Filtering**: Automatically ignores stickers, voice notes, files, polls, contacts, locations, and audio clips.
- 🔁 **Automatic Reconnection**: Automatically reconnects to Bale if connection drops.
- 🛡️ **Duplicate Prevention**: In-memory cache ensures messages are not re-sent after reconnects.
- 🛑 **Graceful Shutdown**: Listens for SIGINT/SIGTERM signals to shut down cleanly.

---

## Requirements

- **Python 3.11+**
- A real **Bale Account** with access to the source channel.
- A **Telegram Bot** (created via [@BotFather](https://t.me/BotFather)) added as an **Administrator** in the destination Telegram channel.

---

## Installation

### 1. Clone or Download Project
```bash
git clone https://github.com/MidnightMA/bridge.git
cd bridge
```

### 2. Create and Activate Virtual Environment
```bash
python3 -m venv venv

# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## Configuration

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your settings:

   ```env
   # Bale Side (Real User Account)
   BALE_PHONE=+989123456789
   BALE_SESSION=bale_userbot_session
   BALE_CHANNEL_ID=-1001234567890

   # Telegram Side (Bot API)
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   TELEGRAM_CHANNEL_ID=-1009876543210
   ```

### Finding Channel IDs

- **Bale Channel ID**: Obtain the ID or username of the Bale channel you wish to monitor.
- **Telegram Channel ID**: Add `@BotFather` bot to your target Telegram channel as Administrator, then retrieve the channel ID (usually starts with `-100`).

---

## First Login & Session Creation

On the first run, `aiobale` will require interactive authentication to create your session file:

1. Launch the application:
   ```bash
   python main.py
   ```
2. You will be prompted in the terminal to enter:
   - Your phone number (if not set in `.env`)
   - The OTP login code sent to your Bale account / SMS.
3. Once authenticated, a session file (`bale_userbot_session.session`) will be saved locally.
4. Subsequent runs will use this saved session automatically without prompting.

---

## Running the Application

To run in the foreground:
```bash
python main.py
```

### Output Example
```text
2026-07-30 20:00:00 [INFO] Main: Starting Bale -> Telegram Channel Mirror Application...
2026-07-30 20:00:01 [INFO] telegram_client: Connected to Telegram as @MyMirrorBot (Bot ID: 987654321)
2026-07-30 20:00:02 [INFO] bale_client: Connected to Bale
2026-07-30 20:00:02 [INFO] bale_client: Logged in successfully
2026-07-30 20:00:02 [INFO] bale_client: Watching channel -1001234567890 ...
2026-07-30 20:01:10 [INFO] bale_client: New photo
2026-07-30 20:01:12 [INFO] bridge: Forwarded successfully
```

---

## Production Deployment (Systemd)

To run the application continuously on a Linux server:

1. Create a Systemd service file:
   ```bash
   sudo nano /etc/systemd/system/bale-mirror.service
   ```

2. Paste the following configuration (adjust paths and user):
   ```ini
   [Unit]
   Description=Bale to Telegram Mirror Service
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/bale-telegram-mirror
   ExecStart=/home/ubuntu/bale-telegram-mirror/venv/bin/python main.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable bale-mirror
   sudo systemctl start bale-mirror
   ```