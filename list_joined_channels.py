"""
Script to list all joined Bale channels and chats using aiobale's load_dialogs().
"""

import asyncio
import inspect
from config import Config
from aiobale import Client


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
    conn_task = asyncio.create_task(client.start())

    # Wait for connection to authorize
    for _ in range(10):
        await asyncio.sleep(0.5)
        try:
            if hasattr(client, "get_me") and callable(getattr(client, "get_me")):
                me = await client.get_me()
                if me:
                    break
        except Exception:
            pass

    print("Connected successfully!\n")

    print("Fetching dialogs via client.load_dialogs()...\n")

    dialogs = []
    try:
        dialogs = await client.load_dialogs()
    except Exception as e:
        print(f"Error calling load_dialogs(): {e}")

    print("=" * 70)
    print("                 ALL JOINED BALE CHANNELS & CHATS              ")
    print("=" * 70 + "\n")

    if dialogs:
        for idx, d in enumerate(dialogs, 1):
            # Inspect properties of dialog object
            chat = getattr(d, "chat", d)
            peer = getattr(d, "peer", None)

            chat_id = (
                getattr(chat, "id", None)
                or getattr(d, "peer_id", None)
                or getattr(d, "id", None)
                or getattr(peer, "id", None)
            )

            title = (
                getattr(chat, "title", None)
                or getattr(chat, "first_name", None)
                or getattr(d, "title", None)
                or getattr(d, "name", None)
                or getattr(peer, "title", None)
                or "Unknown Title"
            )

            chat_type = (
                getattr(chat, "type", None)
                or getattr(d, "type", None)
                or getattr(peer, "type", None)
                or "Chat"
            )

            username = (
                getattr(chat, "username", None)
                or getattr(d, "username", None)
                or getattr(peer, "username", None)
            )

            username_str = f" (@{username})" if username else ""
            print(f"{idx:02d}. [{str(chat_type).upper()}] {title}{username_str}")
            print(f"    ├─ Channel ID for .env : {chat_id}")

            # Print non-private fields for full visibility
            raw_attrs = {
                k: getattr(d, k)
                for k in dir(d)
                if not k.startswith("_") and not callable(getattr(d, k))
            }
            print(f"    └─ Attributes : {raw_attrs}\n")
    else:
        print("No dialogs returned by client.load_dialogs().")

    print("=" * 70)

    conn_task.cancel()
    try:
        if hasattr(client, "stop") and callable(getattr(client, "stop")):
            await client.stop()
    except Exception:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")