# Bale-to-Telegram Channel Mirror

A robust Python 3.12 asynchronous application that monitors a **Bale Messenger** channel using a user self-account (`baleself`) and automatically mirrors text, photo, and video messages to a **Telegram** channel via Telegram Bot API.

## Features

- ⚡ **Python 3.12 & asyncio**: Modern, fast async loop architecture.
- 📱 **Bale Self-Account**: Connects directly using [`baleself`](https://github.com/Zellias/baleself).
- 🤖 **Telegram Bot Integration**: Sends text, photos, and videos via official API endpoints (`sendMessage`, `sendPhoto`, `sendVideo`).
- 📁 **Supported Formats**:
  - Text messages (exact content)
  - Photos (highest resolution with captions)
  - Videos (with captions)
  - *Ignores documents, audio, stickers, and voice messages.*
- 🛡️ **No Duplication & Old Message Prevention**: Ignores historical messages pre-dating application startup and maintains processed ID tracking.
- 🔄 **Auto-Reconnect & Failover**: Automatic exponential-backoff reconnects if Bale disconnects. Telegram send errors are logged while keeping the service running continuously.
- 🔐 **Session Persistence**: Persists Bale authentication session locally so login is required only once.

---

## Setup & Running Instructions

### 1. Prerequisites
- **Python 3.12** or higher installed.
- A Bale user account (added as a member/admin in the source Bale channel).
- A Telegram Bot token (from `@BotFather`) added as an Administrator in your destination Telegram Channel.

### 2. Installation

Clone the repository and enter the directory:
```bash
git clone https://github.com/your-username/mirror.git
cd mirror
```

Create and activate a virtual environment:
```bash
python3.12 -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

Install the dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configuration

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` with your values:
```env
BALE_PHONE=+989123456789
SOURCE_BALE_CHANNEL=my_bale_channel
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyZ
TELEGRAM_CHANNEL_ID=-1001234567890
```

### 4. Running the Application

Start the mirror application:
```bash
python main.py
```

*Note: On your first run, `baleself` may prompt for an SMS login code sent to your Bale account. Once completed, the session is saved inside `./session_data` for subsequent automatic logins.*