"""
PROJECT-ALPHA PMB Bot entrypoint.

PMB = Price Movement Bot.
Runs a background cycle loop and exposes Telegram controls.
Starts DISABLED — set PMB_ENABLED=true to activate the cycle loop.
"""

from __future__ import annotations

import asyncio
import logging
import os

from . import storage
from .config import POLL_INTERVAL_SECONDS, TELEGRAM_BOT_TOKEN
from .trading_engine import run_cycle

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("pmb_bot")

PMB_ENABLED = os.getenv("PMB_ENABLED", "false").lower() == "true"


async def background_loop() -> None:
    if not PMB_ENABLED:
        logger.info("PMB background loop DISABLED (set PMB_ENABLED=true to activate)")
        return
    logger.info("PMB background loop started  interval=%ss", POLL_INTERVAL_SECONDS)
    while True:
        try:
            summary = await run_cycle()
            logger.info("PMB cycle: %s", summary)
        except Exception:
            logger.exception("PMB background loop error; retrying")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def post_init(app) -> None:
    app.create_task(background_loop())


def build_application():
    from telegram.ext import ApplicationBuilder, CommandHandler
    from .telegram_handlers import (
        buy_cmd, sell_cmd, start_cmd, status_cmd, watchlist_cmd,
    )
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("PMB_BOT_TOKEN or BOT_TOKEN must be set.")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",     start_cmd))
    app.add_handler(CommandHandler("status",    status_cmd))
    app.add_handler(CommandHandler("buy",       buy_cmd))
    app.add_handler(CommandHandler("sell",      sell_cmd))
    app.add_handler(CommandHandler("watchlist", watchlist_cmd))
    return app


def main() -> None:
    storage.ensure_storage()
    logger.info("PMB Bot starting (enabled=%s)", PMB_ENABLED)
    build_application().run_polling()


if __name__ == "__main__":
    main()
