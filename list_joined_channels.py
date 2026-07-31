"""
Script to list all channels, groups, and chats you have joined on Bale with their IDs
by reflecting on aiobale methods and session storage.
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

    print("=" * 65)
    print("              INSPECTING AIOBALE CLIENT API                   ")
    print("=" * 65)

    # 1. Print all public methods on Client
    public_methods = [
        m for m in dir(client)
        if not m.startswith("_") and callable(getattr(client, m))
    ]
    print(f"\n[+] Public methods available on aiobale.Client:\n{public_methods}\n")

    # 2. Identify candidate methods that fetch chats/dialogs/peers
    candidate_methods = [
        m for m in dir(client)
        if any(keyword in m.lower() for keyword in ("dialog", "chat", "peer", "channel", "group", "get", "fetch", "list"))
        and callable(getattr(client, m))
    ]

    dialogs = []

    # Attempt calling each candidate method
    for method_name in candidate_methods:
        if method_name in ("start", "stop", "connect", "disconnect", "download", "download_file", "upload_file", "send_message"):
            continue
        try:
            method = getattr(client, method_name)
            sig_m = inspect.signature(method)
            kwargs = {}
            if "limit" in sig_m.parameters:
                kwargs["limit"] = 100

            res = await method(**kwargs) if inspect.iscoroutinefunction(method) else method(**kwargs)
            if res:
                print(f"[✓] client.{method_name}() returned data: {type(res).__name__}")
                if isinstance(res, (list, tuple, set)):
                    dialogs.extend(res)
                elif hasattr(res, "chats") or hasattr(res, "dialogs") or hasattr(res, "peers"):
                    items = getattr(res, "chats", None) or getattr(res, "dialogs", None) or getattr(res, "peers", None)
                    if items:
                        dialogs.extend(items)
        except Exception as e:
            pass

    # 3. Inspect internal storage or session objects
    for storage_attr in ("storage", "_storage", "session", "_session", "db", "_db"):
        st = getattr(client, storage_attr, None)
        if st is not None:
            for sub in ("chats", "peers", "dialogs", "channels", "_chats", "_peers"):
                val = getattr(st, sub, None)
                if val:
                    print(f"[✓] Found {sub} in client.{storage_attr}")
                    if isinstance(val, (dict, list, tuple)):
                        dialogs.extend(val.values() if isinstance(val, dict) else val)

    print("\n" + "=" * 65)
    print("                     JOINED BALE CHANNELS LIST                 ")
    print("=" * 65 + "\n")

    if dialogs:
        seen = set()
        count = 0
        for item in dialogs:
            chat = getattr(item, "chat", item)
            chat_id = getattr(chat, "id", getattr(chat, "peer_id", getattr(item, "id", "N/A")))

            if chat_id in seen or chat_id == "N/A":
                continue
            seen.add(chat_id)

            title = getattr(chat, "title", getattr(chat, "first_name", getattr(item, "title", "Unknown Title")))
            chat_type = getattr(chat, "type", getattr(item, "type", "Chat"))
            username = getattr(chat, "username", getattr(item, "username", ""))

            count += 1
            username_display = f" (@{username})" if username else ""
            print(f"{count:02d}. [{str(chat_type).upper()}] {title}{username_display}")
            print(f"    └─ Channel ID for .env : {chat_id}\n")
    else:
        print("No dialogs returned by automated inspection methods.")

    print("=" * 65)

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