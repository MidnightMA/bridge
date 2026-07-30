"""Main application entry point."""

import asyncio
import signal
import sys
from typing import Any

from bale_client import BaleUserClient
from config import Config
from downloader import Downloader
from forwarder import MessageForwarder
from logger import setup_logger
from telegram_client import TelegramClient


async def main() -> None:
    """Initializes and executes the message bridge application."""
    # 1. Load configuration
    config = Config()
    config.validate()

    # 2. Setup Logger
    logger = setup_logger("bridge", config.log_level)
    logger.info("Initializing Bale -> Telegram Message Bridge Service...")

    # 3. Instantiate components
    downloader = Downloader(temp_dir=config.temp_dir)
    
    telegram_client = TelegramClient(
        bot_token=config.telegram_bot_token,
        target_channel_id=config.telegram_channel_id,
        max_retries=config.max_retries,
        retry_delay=config.retry_delay,
    )

    forwarder = MessageForwarder(
        telegram_client=telegram_client,
        downloader=downloader,
        db_path=config.db_path,
    )

    # 4. Initialize Bale User Client
    bale_client = BaleUserClient(
        phone_number=config.bale_phone_number,
        session_token=config.bale_session,
        channel_id=config.bale_channel_id,
        on_message_callback=forwarder.process_message,
    )

    # 5. Register signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown_handler(sig_name: str) -> None:
        logger.info(f"Received shutdown signal ({sig_name}). Stopping service...")
        bale_client.stop()
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig.name: shutdown_handler(s))
        except NotImplementedError:
            # Signal handling on non-Unix systems (e.g. Windows)
            pass

    # 6. Run Bale monitoring loop
    bale_task = asyncio.create_task(bale_client.start())

    logger.info("Service initialized and actively monitoring updates...")
    await stop_event.wait()

    # Cancel tasks and clean up
    bale_task.cancel()
    try:
        await bale_task
    except asyncio.CancelledError:
        pass

    logger.info("Bridge service stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)