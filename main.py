"""
Main application entry point.
Initializes configuration, logging, signal handlers, and application loop.
"""

import asyncio
import logging
import signal
import sys

from config import Config
from bale_client import BaleClient
from telegram_client import TelegramClient
from bridge import MessageBridge


def setup_logging() -> None:
    """Configure structured logging output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


async def async_main() -> None:
    """Asynchronous setup and execution loop."""
    setup_logging()
    logger = logging.getLogger("Main")
    logger.info("Starting Bale -> Telegram Channel Mirror Application...")

    # Load configuration
    try:
        config = Config.load()
    except ValueError as err:
        logger.critical("Configuration error: %s", err)
        sys.exit(1)

    # Initialize Telegram Bot Client
    telegram_client = TelegramClient(
        token=config.telegram_bot_token,
        channel_id=config.telegram_channel_id,
    )
    await telegram_client.initialize()

    # Initialize Bale Userbot Client
    bale_client = BaleClient(
        phone_number=config.bale_phone,
        session_name=config.bale_session,
        target_channel_id=config.bale_channel_id,
    )

    # Initialize Bridge
    _ = MessageBridge(
        bale_client=bale_client,
        telegram_client=telegram_client,
    )

    # Setup Graceful Shutdown via Signals
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_shutdown_signal(sig_name: str) -> None:
        logger.info("Received signal %s. Shutting down gracefully...", sig_name)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig.name: _on_shutdown_signal(s))
        except NotImplementedError:
            pass  # Windows signal handling fallback

    # Authenticate and start Bale client
    try:
        await bale_client.authenticate_and_start()
    except Exception as e:
        logger.critical("Failed to start Bale client: %s", e)
        sys.exit(1)

    bale_task = asyncio.create_task(bale_client.run_forever())

    logger.info("Mirror application is active. Press Ctrl+C to terminate.")

    # Wait until shutdown signal or Bale task failure
    await asyncio.wait(
        [bale_task, asyncio.create_task(stop_event.wait())],
        return_when=asyncio.FIRST_COMPLETED,
    )

    logger.info("Stopping components...")
    await bale_client.stop()

    bale_task.cancel()
    try:
        await bale_task
    except asyncio.CancelledError:
        pass

    logger.info("Application stopped gracefully.")


def main() -> None:
    """Application entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()