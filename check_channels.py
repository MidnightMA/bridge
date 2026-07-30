"""
Diagnostic script to discover Bale Channel / Chat IDs.
Run this script, post a message in your Bale channel, and inspect the printed Chat ID.
"""

import asyncio
import logging
import sys

from config import Config
from aiobale import Client, Dispatcher
from aiobale.types import Message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ChannelInspector")


async def main() -> None:
    logger.info("Loading configuration...")
    config = Config.load()

    dp = Dispatcher()
    client = Client(dispatcher=dp)

    @dp.message()
    async def _on_any_message(message: Message) -> None:
        print("\n" + "=" * 60)
        print("📩 INCOMING BALE UPDATE DETECTED")
        print("=" * 60)
        
        # Extract Chat / Peer information
        chat = getattr(message, "chat", None)
        chat_id = getattr(chat, "id", None) if chat else None
        chat_title = getattr(chat, "title", None) if chat else None
        chat_type = getattr(chat, "type", None) if chat else None
        chat_username = getattr(chat, "username", None) if chat else None
        
        peer_id = getattr(message, "peer_id", None)
        msg_id = getattr(message, "id", getattr(message, "message_id", None))
        text = getattr(message, "text", getattr(message, "caption", ""))

        print(f"• Message ID  : {msg_id}")
        print(f"• Chat ID     : {chat_id}")
        print(f"• Peer ID     : {peer_id}")
        print(f"• Chat Title  : {chat_title}")
        print(f"• Chat Type   : {chat_type}")
        print(f"• Username    : @{chat_username}" if chat_username else "• Username    : None")
        print(f"• Text Content: {text[:50] if text else '[Media/Empty]'}")
        print("=" * 60)
        print("👉 Copy the 'Chat ID' or 'Peer ID' above and set it as BALE_CHANNEL_ID in your .env file.\n")

    logger.info("Connecting to Bale...")
    await client.connect()
    logger.info("Connected!")

    # Attempt to list recent dialogs / chats if supported
    try:
        if hasattr(client, "get_dialogs"):
            dialogs = await client.get_dialogs()
            print("\n--- MEMBER CHATS / CHANNELS LIST ---")
            for d in dialogs:
                d_chat = getattr(d, "chat", d)
                print(f"Title: {getattr(d_chat, 'title', 'N/A')} | ID: {getattr(d_chat, 'id', 'N/A')} | Type: {getattr(d_chat, 'type', 'N/A')}")
            print("------------------------------------\n")
    except Exception as e:
        logger.debug("Could not automatically fetch dialog list: %s", e)

    print("Listening for ANY posts or messages... Send a test post in your Bale channel now!")
    
    if hasattr(client, "run_until_disconnected"):
        await client.run_until_disconnected()
    elif hasattr(client, "idle"):
        await client.idle()
    else:
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInspector stopped.")