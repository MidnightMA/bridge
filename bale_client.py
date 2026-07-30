"""
Bale Client wrapper module utilizing the baleself library.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

try:
    import baleself
except ImportError as err:
    raise ImportError("The 'baleself' library is required. Install via git repo or pip.") from err

logger = logging.getLogger(__name__)


class BaleClientWrapper:
    """
    Wrapper for baleself user account client with persistent login
    and auto-reconnect logic.
    """

    def __init__(
        self,
        phone: str,
        source_channel: str,
        session_dir: str = "./session_data",
        reconnect_delay: int = 5
    ) -> None:
        self.phone = phone
        self.source_channel = str(source_channel).strip()
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.reconnect_delay = reconnect_delay
        
        self.client: Optional[Any] = None
        self._message_handler: Optional[Callable[[Any], Awaitable[None]]] = None
        self._is_running = False

    def set_message_handler(self, handler: Callable[[Any], Awaitable[None]]) -> None:
        """Registers external async handler for processed messages."""
        self._message_handler = handler

    def _create_client_instance(self) -> Any:
        """Instantiates baleself Client with designated session file path."""
        session_file = str(self.session_dir / f"session_{self.phone.replace('+', '')}")
        logger.info(f"Using Bale session path: {session_file}")
        
        if hasattr(baleself, "Client"):
            return baleself.Client(session=session_file, phone=self.phone)
        if hasattr(baleself, "BaleClient"):
            return baleself.BaleClient(session=session_file, phone=self.phone)
        
        raise AttributeError("Could not resolve Client class from baleself package.")

    async def _on_raw_message(self, message: Any) -> None:
        """Filters message by source channel and forwards to application handler."""
        if not self._message_handler:
            return

        try:
            # Extract identifiers from incoming Bale message object
            peer_id = str(getattr(message, "chat_id", None) or getattr(message, "peer_id", None) or "")
            chat = getattr(message, "chat", None)
            chat_username = str(getattr(chat, "username", "") or "").lstrip("@")
            chat_title = str(getattr(chat, "title", "") or "")
            
            target = self.source_channel.lstrip("@").lower()

            # Matches either Chat ID, Username, or Channel Title
            if target in (peer_id.lower(), chat_username.lower(), chat_title.lower()):
                logger.debug(f"Matched incoming message from source Bale channel: {self.source_channel}")
                await self._message_handler(message)
            else:
                logger.debug(f"Ignored message from unmonitored source: peer_id={peer_id}, title={chat_title}")
        except Exception as e:
            logger.error(f"Error filtering Bale message: {e}", exc_info=True)

    async def start(self) -> None:
        """Main connection and auto-reconnect event loop."""
        self._is_running = True

        while self._is_running:
            try:
                logger.info("Connecting to Bale userbot account...")
                self.client = self._create_client_instance()

                # Register event callback
                if hasattr(self.client, "on_message"):
                    @self.client.on_message()
                    async def event_wrapper(msg):
                        await self._on_raw_message(msg)
                elif hasattr(self.client, "add_event_handler"):
                    self.client.add_event_handler(self._on_raw_message)

                if hasattr(self.client, "start"):
                    await self.client.start()
                elif hasattr(self.client, "connect"):
                    await self.client.connect()

                logger.info("Bale client connected and active.")

                # Keep loop active listening for events
                if hasattr(self.client, "run_until_disconnected"):
                    await self.client.run_until_disconnected()
                elif hasattr(self.client, "idle"):
                    await self.client.idle()
                else:
                    while self._is_running:
                        await asyncio.sleep(1)

            except asyncio.CancelledError:
                logger.info("Bale client task cancellation requested.")
                self._is_running = False
                break
            except Exception as e:
                logger.error(
                    f"Bale client connection error: {e}. Reconnecting in {self.reconnect_delay} seconds...",
                    exc_info=True
                )
                await asyncio.sleep(self.reconnect_delay)

    async def stop(self) -> None:
        """Safely stops and disconnects the Bale client session."""
        self._is_running = False
        if self.client:
            try:
                if hasattr(self.client, "disconnect"):
                    await self.client.disconnect()
                elif hasattr(self.client, "stop"):
                    await self.client.stop()
                logger.info("Bale client disconnected successfully.")
            except Exception as e:
                logger.warning(f"Error during Bale client disconnection: {e}")