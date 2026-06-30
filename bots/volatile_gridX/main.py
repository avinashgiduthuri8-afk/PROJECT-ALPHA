"""
PROJECT-ALPHA Trading Bot
Railway Production Main File
"""

import asyncio
import atexit

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler
)

# ============================================================
# CORE MODULES
# ============================================================

from .config import *
from . import storage

from .analytics import (
    stats_cmd,
    history_cmd,
    analytics_cmd,
    update_stats
)

from .telegram_handlers import (
    start_cmd,
    status_cmd,
    help_cmd,
    buy_cmd,
    sell_cmd,
    tradeamount_cmd,
    mode_cmd,
    setmode_cmd,
    threshold_cmd,
    setthreshold_cmd
)

from .market_data import (
    update_market_cache
)

from .alerts import auto_alerts

from .exit_engine import auto_sell


# NEST ASYNC
# ============================================================



# ============================================================
# STARTUP
# ============================================================

def startup():

    print("================================")

    print("PROJECT-ALPHA STARTING")

    print("Loading Storage...")

    storage.load_data()

    print(

        f"Balance : ₹{storage.virtual_balance}"

    )

    print(


    )

    print("Startup Complete")

    print("================================")


# ============================================================
# BACKGROUND LOOP
# ============================================================

async def background_loop():

    print("Background Engine Started")

    while True:

        try:

            # MARKET CACHE

            update_market_cache()

            # ALERT ENGINE

            await auto_alerts()

            # AUTO EXIT ENGINE

            auto_sell()

            # UPDATE ANALYTICS

            update_stats()

            # SAVE

            storage.save_data()

        except Exception as e:

            print(

                "[BACKGROUND ERROR]",

                e

            )

        await asyncio.sleep(

            STORAGE_SYNC_INTERVAL

        )


# ============================================================
# POST INIT
# ============================================================

async def post_init(app):

    asyncio.create_task(

        background_loop()

    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:
        print("[VGX] BOT_TOKEN not set — Telegram bot disabled")
        print("[VGX] Running headless (scanner + trading engine only)")
        return

    startup()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )


    # ======================================
    # COMMANDS
    # ======================================

    app.add_handler(

        CommandHandler(

            "start",

            start_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "status",

            status_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "help",

            help_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "buy",

            buy_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "sell",

            sell_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "tradeamount",

            tradeamount_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "mode",

            mode_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "setmode",

            setmode_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "threshold",

            threshold_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "setthreshold",

            setthreshold_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "stats",

            stats_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "history",

            history_cmd

        )

    )

    app.add_handler(

        CommandHandler(

            "analytics",

            analytics_cmd

        )

    )


    # SAVE ON EXIT

    atexit.register(

        storage.save_data

    )


    print(

        "🚀 PROJECT-ALPHA LIVE"

    )

    app.run_polling()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
