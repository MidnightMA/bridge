"""
Script to list all channels, groups, and chats you have joined on Bale with their IDs.
"""

import asyncio
import inspect
from config import Config
from aiobale import Client, Dispatcher


async def main() -> None:
    print("Loading project configuration...")
    config = Config.load()

    # Pass saved session credentials
    sig = inspect.signature(Client.__init__)
    params = sig.parameters

    client_kwargs = {}
    if "phone_number" in params and config.bale_phone:
        client_kwargs["phone_number"] = config.bale_phone

    for session_param in ("session_name", "session_file", "session_path", "name", "session_id"):
        if session_param in params:
            client_kwargs[session_param] = config.bale_session
            break

    client = Client(**client_kwargs)

    print("Connecting to Bale...")
    await client.connect()
    print("Connected successfully!\n")

    print("=" * 65)
    print("             ALL JOINED BALE CHANNELS & CHATS LIST             ")
    print("=" * 65 + "\n")

    dialogs = []

    # Fetch dialogs/chats using available client methods
    if hasattr(client, "get_dialogs") and callable(getattr(client, "get_dialogs")):
        try:
            dialogs = await client.get_dialogs()
        except Exception as e:
            print(f"Notice: get_dialogs() error: {e}")

    if not dialogs and hasattr(client, "get_chats") and callable(getattr(client, "get_chats")):
        try:
            dialogs = await client.get_chats()
        except Exception as e:
            print(f"Notice: get_chats() error: {e}")

    if dialogs:
        count = 0
        for item in dialogs:
            chat = getattr(item, "chat", item)
            chat_id = getattr(chat, "id", getattr(chat, "peer_id", "N/A"))
            title = getattr(chat, "title", getattr(chat, "first_name", "Unknown Title"))
            chat_type = getattr(chat, "type", "Chat")
            username = getattr(chat, "username", "")

            count += 1
            username_display = f" (@{username})" if username else ""
            print(f"{count:02d}. [{str(chat_type).upper()}] {title}{username_display}")
            print(f"    └─ Channel ID for .env : {chat_id}\n")
    else:
        print("Could not retrieve dialog list automatically.")
        print("You can run `python check_channels.py` and post a test message in your channel to catch its ID live.\n")

    print("=" * 65)

    if hasattr(client, "disconnect") and callable(getattr(client, "disconnect")):
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")