"""Bale Personal Account Client (Userbot) Engine.

Supports:
1. Selenium Web Automation with persistent browser profiles (Zellias/baleself style).
2. Direct WebSocket monitoring using LocalStorage / WebSocket tokens.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import aiohttp

logger = logging.getLogger("bridge.bale_client")

BALE_WEB_URL = "https://web.bale.ai"
BALE_WS_URL = "wss://next-ws.bale.ai/ws/"
PROFILE_DIR = os.path.abspath("bale_browser_profile")


class BaleUserClient:
    """Client for monitoring personal Bale account via Web Session or Selenium."""

    def __init__(
        self,
        phone_number: str,
        session_token: str,
        channel_id: str,
        on_message_callback: Callable[[Dict[str, Any]], Any],
        use_selenium: bool = True,
    ) -> None:
        self.phone_number = phone_number
        self.session_token = session_token
        self.channel_id = str(channel_id)
        self.on_message_callback = on_message_callback
        self.use_selenium = use_selenium
        self.is_running = False

    def _parse_message(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parses raw update payloads into standardized structure."""
        try:
            msg = raw_data.get("message") or raw_data.get("body") or raw_data
            chat_id = str(
                msg.get("chat_id")
                or msg.get("peer_id")
                or msg.get("chat", {}).get("id", "")
            )

            # Filter for specific target channel
            if chat_id and chat_id != self.channel_id:
                return None

            msg_id = str(msg.get("id") or msg.get("message_id") or msg.get("msg_id", ""))
            if not msg_id:
                return None

            # 1. Text Message
            if "text" in msg and not msg.get("photo") and not msg.get("video"):
                return {
                    "id": msg_id,
                    "type": "text",
                    "text": msg["text"],
                    "media_url": None,
                    "caption": None,
                }

            # 2. Photo Message
            if "photo" in msg or msg.get("media_type") == "photo":
                photo_info = msg.get("photo", {})
                url = photo_info.get("file_url") or photo_info.get("url") or photo_info.get("src")
                caption = msg.get("caption") or msg.get("text")
                if url:
                    return {
                        "id": msg_id,
                        "type": "photo",
                        "text": None,
                        "media_url": url,
                        "caption": caption,
                    }

            # 3. Video Message
            if "video" in msg or msg.get("media_type") == "video":
                video_info = msg.get("video", {})
                url = video_info.get("file_url") or video_info.get("url") or video_info.get("src")
                caption = msg.get("caption") or msg.get("text")
                if url:
                    return {
                        "id": msg_id,
                        "type": "video",
                        "text": None,
                        "media_url": url,
                        "caption": caption,
                    }

            return None
        except Exception as e:
            logger.debug(f"Parsing update failed: {e}")
            return None

    async def _run_selenium_client(self) -> None:
        """Runs Selenium WebDriver wrapper with saved profile (baleself approach)."""
        logger.info("Initializing Selenium WebDriver for Bale userbot automation...")
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            logger.error("Selenium required. Install via: pip install selenium webdriver-manager")
            return

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"--user-data-dir={PROFILE_DIR}")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=chrome_options
        )

        try:
            driver.get(BALE_WEB_URL)
            logger.info("Bale Web loaded successfully in Selenium driver.")
            processed_ids = set()

            while self.is_running:
                await asyncio.sleep(3)
                try:
                    # Extracts channel messages directly from the DOM
                    messages = driver.execute_script("""
                        let msgs = [];
                        let elements = document.querySelectorAll('.message-item, [data-message-id]');
                        elements.forEach(el => {
                            let id = el.getAttribute('data-message-id') || el.id;
                            let text = el.innerText || '';
                            let img = el.querySelector('img');
                            let video = el.querySelector('video');
                            let mediaUrl = img ? img.src : (video ? video.src : null);
                            let type = video ? 'video' : (img ? 'photo' : 'text');
                            if (id) {
                                msgs.push({id: id, type: type, text: text, media_url: mediaUrl, caption: text});
                            }
                        });
                        return msgs;
                    """)

                    for m in messages:
                        m_id = str(m.get("id"))
                        if m_id and m_id not in processed_ids:
                            processed_ids.add(m_id)
                            parsed = self._parse_message(m)
                            if parsed:
                                await self.on_message_callback(parsed)

                except Exception as ex:
                    logger.debug(f"Selenium polling cycle error: {ex}")

        finally:
            driver.quit()

    async def _run_websocket_client(self) -> None:
        """Runs direct WebSocket listener using token."""
        backoff = 2.0
        headers = {
            "Authorization": f"Bearer {self.session_token}",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Origin": BALE_WEB_URL,
        }

        while self.is_running:
            try:
                async with aiohttp.ClientSession() as session:
                    ws_endpoint = f"{BALE_WS_URL}?token={self.session_token}"
                    async with session.ws_connect(ws_endpoint, headers=headers, heartbeat=25.0) as ws:
                        logger.info("Connected to Bale WebSocket stream.")
                        backoff = 2.0
                        await ws.send_json({"action": "subscribe", "channel_id": self.channel_id})

                        async for msg in ws:
                            if not self.is_running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                    parsed = self._parse_message(data)
                                    if parsed:
                                        asyncio.create_task(self.on_message_callback(parsed))
                                except json.JSONDecodeError:
                                    pass
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}. Reconnecting in {backoff}s...")

            if self.is_running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 60.0)

    async def start(self) -> None:
        """Starts monitoring stream."""
        self.is_running = True
        if self.use_selenium or not self.session_token:
            await self._run_selenium_client()
        else:
            await self._run_websocket_client()

    def stop(self) -> None:
        """Stops client loop."""
        self.is_running = False


def setup_selenium_login() -> None:
    """Helper CLI tool to initialize browser session interactively (baleself style)."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("Please install selenium: pip install selenium webdriver-manager")
        sys.exit(1)

    print("\n--- Bale Selenium Account Login ---")
    print(f"Saving browser profile to: {PROFILE_DIR}")

    chrome_options = Options()
    # Runs non-headless so you can enter phone number and SMS OTP code
    chrome_options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=chrome_options
    )
    driver.get(BALE_WEB_URL)

    print("\n1. Login to your Bale account in the opened Chrome browser window.")
    print("2. Once logged in and viewing your chat list, press ENTER in this terminal to save session.\n")
    input("Press ENTER when logged in: ")

    driver.quit()
    print(f"[SUCCESS] Profile saved to '{PROFILE_DIR}'. You can now run 'python main.py'.\n")


if __name__ == "__main__":
    if "--login-selenium" in sys.argv:
        setup_selenium_login()
    else:
        print("\nUsage options:")
        print("1. Automatic Selenium Login (Recommended):")
        print("   python bale_client.py --login-selenium\n")
        print("2. Manual LocalStorage Token Extraction:")
        print("   - Open F12 -> Application -> Local Storage -> https://web.bale.ai")
        print("   - Copy 'auth' or 'token' key value into .env BALE_SESSION\n")