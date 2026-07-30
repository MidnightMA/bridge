"""Bale Personal Account Client (Userbot) Engine.

Supports both direct token/cookie WebSocket connection and Selenium Web Automation
(similar to Zellias/baleself).
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Callable, Dict, Optional
import aiohttp

logger = logging.getLogger("bridge.bale_client")

BALE_WEB_URL = "https://web.bale.ai"
BALE_WS_URL = "wss://next-ws.bale.ai/ws/"


class BaleUserClient:
    """Client for monitoring personal Bale account via Web Session or Selenium."""

    def __init__(
        self,
        phone_number: str,
        session_token: str,
        channel_id: str,
        on_message_callback: Callable[[Dict[str, Any]], Any],
        use_selenium: bool = False,
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

    async def _run_websocket_client(self) -> None:
        """Connects directly to Bale Web WebSocket stream using BALE_SESSION token."""
        backoff = 2.0
        headers = {
            "Cookie": f"access_token={self.session_token}",
            "Authorization": f"Bearer {self.session_token}",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": BALE_WEB_URL,
        }

        logger.info(f"Connecting to Bale Web WebSocket stream for channel {self.channel_id}...")

        while self.is_running:
            try:
                async with aiohttp.ClientSession() as session:
                    ws_endpoint = f"{BALE_WS_URL}?token={self.session_token}"
                    async with session.ws_connect(
                        ws_endpoint,
                        headers=headers,
                        heartbeat=25.0,
                    ) as ws:
                        logger.info("Successfully connected to Bale real-time update stream.")
                        backoff = 2.0

                        # Send channel subscription frame
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
                                logger.warning("Bale WebSocket connection disconnected.")
                                break

            except asyncio.CancelledError:
                self.is_running = False
                break
            except Exception as e:
                logger.error(f"Bale WebSocket error: {e}. Reconnecting in {backoff}s...")

            if self.is_running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 60.0)

    async def _run_selenium_client(self) -> None:
        """Runs Selenium WebDriver wrapper to automate web.bale.ai (baleself approach)."""
        logger.info("Initializing Selenium WebDriver for Bale userbot automation...")
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            logger.error("Selenium required for this mode. Run: pip install selenium webdriver-manager")
            return

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")

        user_data_dir = os.path.abspath("bale_selenium_profile")
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=chrome_options
        )

        try:
            driver.get(BALE_WEB_URL)
            logger.info("Opened web.bale.ai in Selenium Chrome driver.")

            if self.session_token:
                driver.add_cookie({
                    "name": "access_token",
                    "value": self.session_token,
                    "domain": ".bale.ai",
                    "path": "/",
                })
                driver.refresh()

            processed_ids = set()

            while self.is_running:
                await asyncio.sleep(3)
                try:
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
                    logger.debug(f"Selenium polling cycle exception: {ex}")

        finally:
            driver.quit()

    async def start(self) -> None:
        """Starts monitoring stream."""
        self.is_running = True
        if self.use_selenium:
            await self._run_selenium_client()
        else:
            await self._run_websocket_client()

    def stop(self) -> None:
        """Stops the client."""
        self.is_running = False


if __name__ == "__main__":
    print("\n[Bale Userbot Token Setup]")
    print("1. Open https://web.bale.ai in Chrome/Firefox and log into your account.")
    print("2. Open Developer Tools (F12) -> Application -> Cookies -> https://web.bale.ai")
    print("3. Copy the value of 'access_token' and paste it into your .env file as:")
    print("   BALE_SESSION=your_copied_access_token_value\n")