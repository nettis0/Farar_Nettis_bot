import os
import json
import logging
import requests
from datetime import datetime, time
from zoneinfo import ZoneInfo
from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    filters, ConversationHandler, CallbackQueryHandler,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
PORT = int(os.environ.get("PORT", 10000))
EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

JSONBIN_API_KEY = os.environ["JSONBIN_API_KEY"]
JSONBIN_BIN_ID = os.environ["JSONBIN_BIN_ID"]
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"

TZ = ZoneInfo("Asia/Yekaterinburg")  # время Перми


def load_data():
    try:
        r = requests.get(
            JSONBIN_URL + "/latest",
            headers={"X-Master-Key": JSONBIN_API_KEY},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["record"]
    except Exception:
        logging.exception("Не удалось загрузить данные из jsonbin, использую пустые")
        return {"owner_id": None, "commands": {}}


def save_data():
    try:
        requests.put(
            JSONBIN_URL,
            json=DATA,
            headers={"X-Master-Key": JSONBIN_API_KEY, "Content-Type": "application/json"},
            timeout=10,
        )
    except Exception:
        logging.exception("Не удалось сохранить данные в jsonbin")


DATA = load_data()

BTN_BELL = "Расписание звонков"
BTN_LESSON = "Какой сейчас урок"
BTN_ADD = "➕ Добавить команду"
BTN_LIST = "📋 Мои команды"
BTN_HW_SET = "Выбор урока"
BTN_HW_GET = "Узнать дз"
BTN_CANCEL = "Отмена"

SUBJECTS = [
    "Алгебра и начала мат. анализа",
    "Биология",
    "Вероятность и статистика",
    "География",
    "Геометрия",
    "Иностранный (английский) язык",
    "Информатика",
    "История",
    "Литература",
    "Обществознание",
    "ОБЗР",
    "Русский язык",
    "Физика",
    "Физическая культура",
    "Химия",
]

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
    [[BTN_BELL, BTN_LESSON], [BTN_HW_SET, BTN_HW_GET], [BTN_ADD, BTN_LIST]],
    resize_keyboard=True,
)

CANCEL_KEYBOARD = ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)

WAITING_TRIGGER, WAITING_RESPONSE = range(2)


def minutes_until(now, target):
    target_dt = datetime.combine(now.date(), target, TZ)
    return int((target_dt - now).total_seconds() // 60) + 1


def get_lesson_status():
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


def is_owner(update: Update) -> bool:
    if DATA.get("owner_id") is None:
        DATA["owner_id"] = update.effective_user.id
        save_data()
        return True
    return update.effective_user.id == DATA["owner_id"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_owner(update)
    await update.message.reply_text(TEMPLATES["start"], reply_markup=MAIN_KEYBOARD)


async def bell_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TEMPLATES["bell_schedule"], reply_markup=MAIN_KEYBOARD)


async def lesson_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_lesson_status(), reply_markup=MAIN_KEYBOARD)


# ---- Добавление команды (по кнопке) ----

async def addcmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "Напиши слово-команду (триггер), на которое бот будет отвечать.",
        reply_markup=CANCEL_KEYBOARD,
    )
    return WAITING_TRIGGER


async def addcmd_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == BTN_CANCEL:
        return await addcmd_cancel(update, context)
    trigger = update.message.text.strip().lower()
    context.user_data["new_trigger"] = trigger
    await update.message.reply_text(
        "Теперь пришли ответ: текст, фото, голосовое или видео.",
        reply_markup=CANCEL_KEYBOARD,
    )
    return WAITING_RESPONSE


async def addcmd_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == BTN_CANCEL:
        return await addcmd_cancel(update, context)

    trigger = context.user_data.pop("new_trigger", None)
    if not trigger:
        return ConversationHandler.END
    msg = update.message

    if msg.photo:
        entry = {"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption or ""}
    elif msg.voice:
        entry = {"type": "voice", "file_id": msg.voice.file_id}
    elif msg.video:
        entry = {"type": "video", "file_id": msg.video.file_id, "caption": msg.caption or ""}
    elif msg.video_note:
        entry = {"type": "video_note", "file_id": msg.video_note.file_id}
    elif msg.document:
        entry = {"type": "document", "file_id": msg.document.file_id, "caption": msg.caption or ""}
    elif msg.text:
        entry = {"type": "text", "text": msg.text}
    else:
        await update.message.reply_text("Такой тип не поддерживается, попробуй ещё раз.")
        return WAITING_RESPONSE

    DATA["commands"][trigger] = entry
    save_data()
    await update.message.reply_text(f"Готово! Команда «{trigger}» сохранена.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


async def addcmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_trigger", None)
    await update.message.reply_text("Отменено.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ---- Список / удаление команд (по кнопкам) ----

def commands_inline_keyboard():
    rows = [
        [InlineKeyboardButton(trigger, callback_data=f"show:{trigger}")]
        for trigger in DATA["commands"]
    ]
    return InlineKeyboardMarkup(rows)


async def listcmd_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    if not DATA["commands"]:
        await update.message.reply_text("Пока нет ни одной команды.", reply_markup=MAIN_KEYBOARD)
        return
    await update.message.reply_text(
        "Твои команды — нажми, чтобы посмотреть или удалить:",
        reply_markup=commands_inline_keyboard(),
    )


async def on_show_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger = query.data.split(":", 1)[1]
    entry = DATA["commands"].get(trigger)
    if not entry:
        await query.edit_message_text("Эта команда уже удалена.")
        return
    preview = entry.get("text") or f"[{entry['type']}]"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Удалить", callback_data=f"del:{trigger}")]])
    await query.edit_message_text(f"«{trigger}» →\n{preview}", reply_markup=kb)


async def on_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    trigger = query.data.split(":", 1)[1]
    DATA["commands"].pop(trigger, None)
    save_data()
    await query.edit_message_text(f"Команда «{trigger}» удалена.")


# ---- Домашние задания ----

def subjects_inline_keyboard(prefix: str):
    rows = []
    for i in range(0, len(SUBJECTS), 2):
        row = [InlineKeyboardButton(s, callback_data=f"{prefix}:{s}") for s in SUBJECTS[i:i + 2]]
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def hw_set_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    await update.message.reply_text(
        "Выбери предмет:",
        reply_markup=subjects_inline_keyboard("hwset"),
    )


async def hw_get_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        return
    await update.message.reply_text(
        "Выбери предмет:",
        reply_markup=subjects_inline_keyboard("hwget"),
    )


async def on_hw_set_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data.split(":", 1)[1]
    context.user_data["hw_subject"] = subject
    await query.edit_message_text(f"«{subject}» — пришли фото или напиши дз текстом.")


async def on_hw_get_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data.split(":", 1)[1]
    hw = DATA.get("homework", {}).get(subject)
    if not hw:
        await query.edit_message_text(f"«{subject}» — дз ещё не сохранено.")
        return
    header = f"«{subject}», {hw['date']} {hw['time']}:"
    if hw["type"] == "text":
        await query.edit_message_text(f"{header}\n{hw['text']}")
    else:
        await query.message.reply_text(header)
        if hw["type"] == "photo":
            await context.bot.send_photo(chat_id=query.message.chat_id, photo=hw["file_id"], caption=hw.get("caption") or None)


async def hw_save_incoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = context.user_data.pop("hw_subject", None)
    if not subject:
        return
    msg = update.message
    now = datetime.now(TZ)
    record = {"date": now.strftime("%d.%m.%Y"), "time": now.strftime("%H:%M")}
    if msg.photo:
        record.update({"type": "photo", "file_id": msg.photo[-1].file_id, "caption": msg.caption or ""})
    elif msg.text:
        record.update({"type": "text", "text": msg.text})
    else:
        await update.message.reply_text("Пришли фото или текст, другое не поддерживается.")
        context.user_data["hw_subject"] = subject
        return

    DATA.setdefault("homework", {})[subject] = record
    save_data()
    await update.message.reply_text(f"Дз по предмету «{subject}» сохранено.", reply_markup=MAIN_KEYBOARD)


# ---- Авто-ответ в бизнес-чатах ----

async def send_entry(bot, chat_id, entry, business_connection_id=None):
    kwargs = {"business_connection_id": business_connection_id} if business_connection_id else {}
    t = entry["type"]
    if t == "text":
        await bot.send_message(chat_id=chat_id, text=entry["text"], **kwargs)
    elif t == "photo":
        await bot.send_photo(chat_id=chat_id, photo=entry["file_id"], caption=entry.get("caption") or None, **kwargs)
    elif t == "voice":
        await bot.send_voice(chat_id=chat_id, voice=entry["file_id"], **kwargs)
    elif t == "video":
        await bot.send_video(chat_id=chat_id, video=entry["file_id"], caption=entry.get("caption") or None, **kwargs)
    elif t == "video_note":
        await bot.send_video_note(chat_id=chat_id, video_note=entry["file_id"], **kwargs)
    elif t == "document":
        await bot.send_document(chat_id=chat_id, document=entry["file_id"], caption=entry.get("caption") or None, **kwargs)


async def business_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bm = update.business_message
    if not bm or not bm.text:
        return
    text_lower = bm.text.lower()
    for trigger, entry in DATA["commands"].items():
        if trigger in text_lower:
            await send_entry(context.bot, bm.chat_id, entry, business_connection_id=bm.business_connection_id)
            break


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & filters.Text([BTN_BELL]), bell_schedule))
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & filters.Text([BTN_LESSON]), lesson_status))
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & filters.Text([BTN_LIST]), listcmd_button))
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & filters.Text([BTN_HW_SET]), hw_set_start))
    app.add_handler(MessageHandler(filters.UpdateType.MESSAGE & filters.Text([BTN_HW_GET]), hw_get_start))
    app.add_handler(CallbackQueryHandler(on_hw_set_subject, pattern=r"^hwset:"))
    app.add_handler(CallbackQueryHandler(on_hw_get_subject, pattern=r"^hwget:"))
    app.add_handler(MessageHandler(
        filters.UpdateType.MESSAGE & (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
        hw_save_incoming,
    ), group=1)

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.UpdateType.MESSAGE & filters.Text([BTN_ADD]), addcmd_start),
        ],
        states={
            WAITING_TRIGGER: [MessageHandler(filters.UpdateType.MESSAGE & filters.TEXT, addcmd_trigger)],
            WAITING_RESPONSE: [MessageHandler(filters.UpdateType.MESSAGE, addcmd_response)],
        },
        fallbacks=[MessageHandler(filters.UpdateType.MESSAGE & filters.Text([BTN_CANCEL]), addcmd_cancel)],
    )
    app.add_handler(conv)

    app.add_handler(CallbackQueryHandler(on_show_command, pattern=r"^show:"))
    app.add_handler(CallbackQueryHandler(on_delete_command, pattern=r"^del:"))

    app.add_handler(MessageHandler(filters.UpdateType.BUSINESS_MESSAGE, business_message_handler))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{EXTERNAL_URL}/{BOT_TOKEN}",
    )


if __name__ == "__main__":
    main()
