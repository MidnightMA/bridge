"""
Main application entry point for Bale-to-Telegram channel mirror service.
"""

import asyncio
import logging
import signal
import sys
import time

from bale_client import BaleClientWrapper
from config import settings
from handlers import MessageHandler
from media import MediaManager
from telegram_client import TelegramClient

# Setup Application Logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("bale_telegram_mirror")


async def main() -> None:
    """Main execution coroutine."""
    logger.info("Initializing Bale-to-Telegram Mirror service...")
    startup_timestamp = time.time()

    # Core system components
    media_manager = MediaManager(media_dir=settings.media_dir)
    telegram_client = TelegramClient(
        bot_token=settings.telegram_bot_token,
        channel_id=settings.telegram_channel_id
    )
    await telegram_client.start()

    message_handler = MessageHandler(
        telegram_client=telegram_client,
        media_manager=media_manager,
        startup_timestamp=startup_timestamp
    )

    bale_client = BaleClientWrapper(
        phone=settings.bale_phone,
        source_channel=settings.source_bale_channel,
        session_dir=settings.session_dir,
        reconnect_delay=settings.reconnect_delay
    )
    bale_client.set_message_handler(message_handler.process_message)

    # Setup Graceful Signal Handling
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown_signal_handler():
        logger.info("Received termination signal. Initiating shutdown sequence...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_signal_handler)
        except NotImplementedError:
            # Signal handling on Windows platforms
            pass

    # Launch Bale Client Task
    bale_task = asyncio.create_task(bale_client.start())

    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Cleaning up and stopping resources...")
        bale_task.cancel()
        await bale_client.stop()
        await telegram_client.stop()
        media_manager.cleanup_all()
        logger.info("Application successfully stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Process terminated by system.")