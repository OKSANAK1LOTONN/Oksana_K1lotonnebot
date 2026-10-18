
import os
import time
import random
import asyncio
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"].rstrip("/")
PORT = int(os.environ.get("PORT", "10000"))
DB_PATH = os.environ.get("DB_PATH", "game.db")


# ---------- DATABASE ----------

def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 1,
            stored INTEGER NOT NULL DEFAULT 0,
            last_ts INTEGER NOT NULL DEFAULT 0
        )
    """)
    con.commit()
    return con


def ensure_player(user_id):
    con = db()
    con.execute(
        "INSERT OR IGNORE INTO players(user_id, last_ts) VALUES (?, ?)",
        (user_id, int(time.time()))
    )
    con.commit()
    con.close()


def get_player(user_id):
    ensure_player(user_id)

    con = db()
    row = con.execute(
        "SELECT balance, level, stored, last_ts FROM players WHERE user_id=?",
        (user_id,)
    ).fetchone()

    balance, level, stored, last_ts = row
    now = int(time.time())

    rate = 20 * level
    capacity = rate * 3
    elapsed = max(0, now - last_ts)
    room = max(0, capacity - stored)
    produced = min(room, elapsed * rate // 3600)

    if produced > 0:
        stored += produced
        advanced = (produced * 3600 + rate - 1) // rate
        con.execute(
            "UPDATE players SET stored=?, last_ts=? WHERE user_id=?",
            (stored, last_ts + advanced, user_id)
        )
        con.commit()

    con.close()
    return balance, level, stored, rate, capacity


# ---------- MENU ----------

def keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏭 Фабрика", callback_data="factory"),
            InlineKeyboardButton(
                "📦 Забрать килокалории",
                callback_data="collect"
            ),
        ],
        [
            InlineKeyboardButton(
                "⬆️ Улучшить фабрику",
                callback_data="upgrade"
            ),
        ],
        [
            InlineKeyboardButton("🎮 Мини-игры", callback_data="games"),
            InlineKeyboardButton("ℹ️ Помощь", callback_data="help"),
        ],
    ])


def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ В меню", callback_data="menu")]
    ])


# ---------- COMMANDS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ensure_player(uid)

    msg = (
        "🍶 Добро пожаловать в «Oksana килотонна»!\n\n"
        "Развивай майонезную фабрику, копи килокалории "
        "и открывай улучшения!"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            msg, reply_markup=keyboard()
        )
    else:
        await update.effective_message.reply_text(
            msg, reply_markup=keyboard()
        )


async def show_factory(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    q = update.callback_query
    await q.answer()

    balance, level, stored, rate, capacity = get_player(q.from_user.id)
    cost = 100 * level * level

    msg = (
        "🏭 Майонезная фабрика\n\n"
        f"💰 Баланс: {balance} килокалорий\n"
        f"⬆️ Уровень: {level}\n"
        f"⚙️ Доход: {rate} килокалорий/час\n"
        f"📦 Хранилище: {stored}/{capacity}\n"
        f"🛠 Следующее улучшение: {cost} килокалорий"
    )

    await q.edit_message_text(msg, reply_markup=keyboard())


async def collect(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    q = update.callback_query
    await q.answer()

    get_player(q.from_user.id)

    con = db()
    row = con.execute(
        "SELECT balance, stored FROM players WHERE user_id=?",
        (q.from_user.id,)
    ).fetchone()

    balance, amount = row

    con.execute(
        """UPDATE players
           SET balance=balance+?, stored=0, last_ts=?
           WHERE user_id=?""",
        (amount, int(time.time()), q.from_user.id)
    )
    con.commit()
    con.close()

    balance += amount

    await q.edit_message_text(
        f"📦 Собрано: {amount} килокалорий!\n"
        f"💰 Баланс: {balance} килокалорий",
        reply_markup=keyboard()
    )


async def upgrade(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    q = update.callback_query
    await q.answer()

    balance, level, stored, rate, capacity = get_player(q.from_user.id)
    cost = 100 * level * level

    if balance < cost:
        await q.edit_message_text(
            f"❌ Недостаточно килокалорий!\n"
            f"Нужно: {cost}\n"
            f"У тебя: {balance}",
            reply_markup=keyboard()
        )
        return

    con = db()
    con.execute(
        """UPDATE players
           SET balance=balance-?, level=level+1
           WHERE user_id=? AND balance>=?""",
        (cost, q.from_user.id, cost)
    )
    con.commit()
    con.close()

    balance, level, stored, rate, capacity = get_player(q.from_user.id)

    await q.edit_message_text(
        f"🎉 Фабрика улучшена!\n\n"
        f"⬆️ Уровень: {level}\n"
        f"⚙️ Доход: {rate} килокалорий/час\n"
        f"💰 Баланс: {balance}",
        reply_markup=keyboard()
    )


# ---------- MINI-GAMES ----------

async def games(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    q = update.callback_query
    await q.answer()

    await q.edit_message_text(
        "🎮 Мини-игры\n\n"
        "🎲 Нажми кнопку и получи случайный результат.\n"
        "Выпадет 3 — бонус 10 килокалорий!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Сыграть", callback_data="guess")],
            [InlineKeyboardButton("⬅️ В меню", callback_data="menu")],
        ])
    )


async def guess(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    q = update.callback_query
    await q.answer()

    ensure_player(q.from_user.id)

    number = random.randint(1, 3)
    reward = 10 if number == 3 else 0

    if reward:
        con = db()
        con.execute(
            "UPDATE players SET balance=balance+? WHERE user_id=?",
            (reward, q.from_user.id)
        )
        con.commit()
        con.close()

        result = (
            f"🎉 Выпало число {number}!\n"
            f"🎁 Бонус: +{reward} килокалорий!"
        )
    else:
        result = (
            f"🎲 Выпало число {number}.\n"
            "Попробуй ещё раз!"
        )

    await q.edit_message_text(
        result,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Ещё раз", callback_data="guess")],
            [InlineKeyboardButton("⬅️ В меню", callback_data="menu")],
        ])
    )


# ---------- HELP ----------

async def help_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    q = update.callback_query
    await q.answer()

    await q.edit_message_text(
        "ℹ️ Как играть:\n\n"
        "🏭 Фабрика производит 20 × уровень килокалорий в час.\n"
        "📦 Хранилище вмещает примерно 3 часа производства.\n"
        "💰 Забирай накопленное, чтобы пополнять баланс.\n"
        "⬆️ Улучшай фабрику для увеличения дохода.\n"
        "🎮 В мини-игре можно получить бонус.",
        reply_markup=keyboard()
    )


# ---------- BUTTON HANDLER ----------

async def callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    data = update.callback_query.data

    handlers = {
        "menu": start,
        "factory": show_factory,
        "collect": collect,
        "upgrade": upgrade,
        "games": games,
        "guess": guess,
        "help": help_cmd,
    }

    handler = handlers.get(data)

    if handler:
        await handler(update, context)
    else:
        await update.callback_query.answer(
            "Неизвестная команда", show_alert=True
        )


# ---------- ASYNC STARTUP FOR RENDER ----------

async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback))

    await app.initialize()

    try:
        await app.updater.start_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TOKEN}",
            drop_pending_updates=True,
        )

        await app.start()

        print("Bot started successfully!")

        # Keep the service running.
        await asyncio.Event().wait()

    finally:
        if app.updater.running:
            await app.updater.stop()

        if app.running:
            await app.stop()

        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
    
