"""Bale User Account Client (Userbot) Protocol Wrapper.

This module provides real-time update monitoring for a personal Bale user account.
It connects via Bale's client WebSocket interface, manages authentications/sessions,
handles automatic reconnections, and emits message updates.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Callable, Dict, Optional
import aiohttp

logger = logging.getLogger("bridge.bale_client")

BALE_WS_URL = "wss://clientws.bale.ai"
BALE_AUTH_API = "https://tapi.bale.ai"


class BaleUserClient:
    """Client for monitoring a personal Bale account using session tokens."""

    def __init__(
        self,
        phone_number: str,
        session_token: str,
        channel_id: str,
        on_message_callback: Callable[[Dict[str, Any]], Any],
    ) -> None:
        self.phone_number = phone_number
        self.session_token = session_token
        self.channel_id = str(channel_id)
        self.on_message_callback = on_message_callback
        self.is_running = False

    @staticmethod
    async def login_interactive(phone_number: str) -> str:
        """Interactive helper to perform OTP phone authentication and return a session token."""
        print(f"\n--- Bale Personal Account Login ---")
        print(f"Requesting authentication code for: {phone_number}")

        async with aiohttp.ClientSession() as session:
            # Step 1: Request OTP Code
            async with session.post(
                f"{BALE_AUTH_API}/user/send_code",
                json={"phone_number": phone_number},
            ) as resp:
                if resp.status != 200:
                    data = await resp.text()
                    raise RuntimeError(f"Failed to request auth code from Bale: {data}")

            print("OTP activation code has been sent to your Bale app / SMS.")
            code = input("Enter the OTP activation code: ").strip()

            # Step 2: Validate OTP Code and receive session token
            async with session.post(
                f"{BALE_AUTH_API}/user/verify_code",
                json={"phone_number": phone_number, "code": code},
            ) as resp:
                data = await resp.json()
                if resp.status != 200 or not data.get("ok"):
                    raise RuntimeError(f"Failed to verify auth code: {data}")

                session_token = data.get("result", {}).get("session_token")
                if not session_token:
                    raise RuntimeError("Response missing session_token.")

                print("\n[SUCCESS] Authentication successful!")
                print(f"BALE_SESSION={session_token}\n")
                return session_token

    def _parse_message(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parses incoming WebSocket frame into standardized payload.

        Extracts only Text, Photo, or Video messages. Ignores all other update types.
        """
        try:
            update_type = raw_data.get("type") or raw_data.get("kind")
            if update_type not in ("message", "Message", "NewMessage"):
                return None

            msg = raw_data.get("message") or raw_data.get("body") or raw_data
            chat_id = str(
                msg.get("chat_id")
                or msg.get("peer_id")
                or msg.get("chat", {}).get("id", "")
            )

            # Filter for specific target channel only
            if chat_id != self.channel_id:
                return None

            msg_id = str(msg.get("id") or msg.get("message_id"))
            if not msg_id:
                return None

            # Detect Content Types
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
                photo_data = msg.get("photo", {})
                media_url = photo_data.get("file_url") or photo_data.get("url")
                caption = msg.get("caption") or msg.get("text")
                if media_url:
                    return {
                        "id": msg_id,
                        "type": "photo",
                        "text": None,
                        "media_url": media_url,
                        "caption": caption,
                    }

            # 3. Video Message
            if "video" in msg or msg.get("media_type") == "video":
                video_data = msg.get("video", {})
                media_url = video_data.get("file_url") or video_data.get("url")
                caption = msg.get("caption") or msg.get("text")
                if media_url:
                    return {
                        "id": msg_id,
                        "type": "video",
                        "text": None,
                        "media_url": media_url,
                        "caption": caption,
                    }

            # Explicitly return None for unsupported types (voice, audio, stickers, docs, etc.)
            return None

        except Exception as e:
            logger.debug(f"Non-parsable message received: {e}")
            return None

    async def start(self) -> None:
        """Starts the real-time WebSocket monitoring loop with automatic reconnection."""
        self.is_running = True
        backoff = 1.0

        if not self.session_token:
            raise ValueError(
                "BALE_SESSION is missing. Run login_interactive first or provide a session token."
            )

        logger.info(
            f"Connecting Bale userbot for account {self.phone_number} to monitor channel {self.channel_id}..."
        )

        headers = {
            "Authorization": f"Bearer {self.session_token}",
            "User-Agent": "BaleUserbot/1.0",
        }

        while self.is_running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        f"{BALE_WS_URL}?token={self.session_token}",
                        headers=headers,
                        heartbeat=20.0,
                    ) as ws:
                        logger.info("Successfully connected to Bale real-time update stream.")
                        backoff = 1.0  # Reset retry delay upon successful connection

                        # Subscribe to target channel updates
                        subscribe_msg = {
                            "action": "subscribe",
                            "channel_id": self.channel_id,
                        }
                        await ws.send_json(subscribe_msg)

                        async for msg in ws:
                            if not self.is_running:
                                break

                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                parsed_message = self._parse_message(data)

                                if parsed_message:
                                    asyncio.create_task(
                                        self.on_message_callback(parsed_message)
                                    )

                            elif msg.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.ERROR,
                            ):
                                logger.warning("Bale WebSocket connection closed or encountered error.")
                                break

            except asyncio.CancelledError:
                logger.info("Bale userbot loop task cancelled.")
                self.is_running = False
                break

            except Exception as e:
                logger.error(f"Bale connection loss or error: {e}. Reconnecting in {backoff}s...")

            if self.is_running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2.0, 60.0)

    def stop(self) -> None:
        """Stops the Bale client loop."""
        self.is_running = False


if __name__ == "__main__":
    # Interactive CLI session builder
    if "--login" in sys.argv:
        from config import Config

        cfg = Config()
        if not cfg.bale_phone_number:
            print("Please set BALE_PHONE_NUMBER in your .env file before logging in.")
            sys.exit(1)

        token = asyncio.run(BaleUserClient.login_interactive(cfg.bale_phone_number))
        print("Save the generated BALE_SESSION token into your .env file.")