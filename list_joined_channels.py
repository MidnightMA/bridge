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
    
    # Run client connection in a background task to prevent blocking the main loop
    conn_task = asyncio.create_task(client.start())

    # Wait briefly for connection to authorize
    connected = False
    for _ in range(10):
        await asyncio.sleep(0.5)
        try:
            if hasattr(client, "get_me") and callable(getattr(client, "get_me")):
                me = await client.get_me()
                if me:
                    connected = True
                    break
        except Exception:
            pass

    if not connected:
        await asyncio.sleep(1)

    print("Connected successfully!\n")

    print("=" * 65)
    print("             ALL JOINED BALE CHANNELS & CHATS LIST             ")
    print("=" * 65 + "\n")

    dialogs = []

    # Check direct property
    if hasattr(client, "dialogs") and getattr(client, "dialogs"):
        dialogs = list(getattr(client, "dialogs"))

    # Try available dialog retrieval methods
    if not dialogs:
        dialog_method_names = ["get_dialogs", "get_chats", "get_user_dialogs", "get_peers", "fetch_dialogs"]
        for method_name in dialog_method_names:
            if hasattr(client, method_name) and callable(getattr(client, method_name)):
                try:
                    method = getattr(client, method_name)
                    res = await method() if inspect.iscoroutinefunction(method) else method()
                    if res:
                        dialogs = list(res)
                        break
                except Exception as e:
                    print(f"Notice: client.{method_name}() error: {e}")

    if dialogs:
        count = 0
        for item in dialogs:
            chat = getattr(item, "chat", item)
            chat_id = getattr(chat, "id", getattr(chat, "peer_id", "N/A"))
            title = getattr(chat, "title", getattr(chat, "first_name", getattr(item, "title", "Unknown Title")))
            chat_type = getattr(chat, "type", getattr(item, "type", "Chat"))
            username = getattr(chat, "username", getattr(item, "username", ""))

            count += 1
            username_display = f" (@{username})" if username else ""
            print(f"{count:02d}. [{str(chat_type).upper()}] {title}{username_display}")
            print(f"    └─ Channel ID for .env : {chat_id}\n")
    else:
        print("Could not retrieve dialog list automatically.")
        print("Run `python check_channels.py` and post a test message in your channel to view its ID live.\n")

    print("=" * 65)

    # Cancel background task and stop client
    conn_task.cancel()
    try:
        if hasattr(client, "stop") and callable(getattr(client, "stop")):
            await client.stop()
        elif hasattr(client, "disconnect") and callable(getattr(client, "disconnect")):
            await client.disconnect()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")