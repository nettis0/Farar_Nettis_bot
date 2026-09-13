import os
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
PORT = int(os.environ.get("PORT", 10000))
EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")  # задаётся Render автоматически

TZ = ZoneInfo("Asia/Yekaterinburg")  # время Перми

BELL_SCHEDULE_BUTTON = "Расписание звонков"
LESSON_STATUS_BUTTON = "Какой сейчас урок"

TEMPLATES = {
    "start": "Приветствую Фарид",
    "bell_schedule": (
        "1. 8:30 – 9:10\n"
        "2. 9:20 – 10:00\n"
        "3. 10:15 – 10:55\n"
        "4. 11:10 – 11:50\n"
        "5. 12:05 – 12:45\n"
        "6. 13:00 – 13:40\n"
        "7. 13:55 – 14:35\n"
        "8. 14:50 – 15:30"
    ),
}

SCHEDULE = [
    (1, time(8, 30), time(9, 10)),
    (2, time(9, 20), time(10, 0)),
    (3, time(10, 15), time(10, 55)),
    (4, time(11, 10), time(11, 50)),
    (5, time(12, 5), time(12, 45)),
    (6, time(13, 0), time(13, 40)),
    (7, time(13, 55), time(14, 35)),
    (8, time(14, 50), time(15, 30)),
]

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [[BELL_SCHEDULE_BUTTON], [LESSON_STATUS_BUTTON]],
    resize_keyboard=True,
)


def minutes_until(now: datetime, target: time) -> int:
    target_dt = datetime.combine(now.date(), target, TZ)
    return int((target_dt - now).total_seconds() // 60) + 1


def get_lesson_status() -> str:
    now = datetime.now(TZ)
    now_t = now.time()

    for num, start, end in SCHEDULE:
        if start <= now_t <= end:
            mins = minutes_until(now, end)
            return f"Сейчас {num} урок. До звонка: {mins} мин."

    for i in range(len(SCHEDULE) - 1):
        _, _, end_prev = SCHEDULE[i]
        _, start_next, _ = SCHEDULE[i + 1]
        if end_prev < now_t < start_next:
            mins = minutes_until(now, start_next)
            return f"Сейчас перемена. До конца перемены: {mins} мин."

    first_start = SCHEDULE[0][1]
    last_end = SCHEDULE[-1][2]
    if now_t < first_start:
        mins = minutes_until(now, first_start)
        return f"Уроки ещё не начались. До 1 урока: {mins} мин."
    if now_t > last_end:
        return "Уроки на сегодня закончились."
    return "Не удалось определить."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TEMPLATES["start"], reply_markup=MAIN_KEYBOARD)


async def bell_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TEMPLATES["bell_schedule"], reply_markup=MAIN_KEYBOARD)


async def lesson_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_lesson_status(), reply_markup=MAIN_KEYBOARD)


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Text([BELL_SCHEDULE_BUTTON]), bell_schedule))
    app.add_handler(MessageHandler(filters.Text([LESSON_STATUS_BUTTON]), lesson_status))
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{EXTERNAL_URL}/{BOT_TOKEN}",
    )


if __name__ == "__main__":
    main()
