
import logging, os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

ASK_CAPTION = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! فایل/عکس/ویدئو رو برام بفرست.\n"
        "بعدش کپشن جدید رو می‌گیرم و همونو دوباره برات می‌فرستم.\n"
        "اگه کپشن نمی‌خوای، فقط بنویس: -"
    )

async def got_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    ud = context.user_data
    ud.clear()

    if msg.document:
        ud["type"] = "document"
        ud["file_id"] = msg.document.file_id
    elif msg.photo:
        ud["type"] = "photo"
        ud["file_id"] = msg.photo[-1].file_id
    elif msg.video:
        ud["type"] = "video"
        ud["file_id"] = msg.video.file_id
    else:
        await msg.reply_text("فقط document/photo/video رو پشتیبانی می‌کنم.")
        return ConversationHandler.END

    await msg.reply_text("کپشن جدید رو بفرست. اگه نمی‌خوای کپشن داشته باشه، بنویس «-».")
    return ASK_CAPTION

async def got_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    caption = update.message.text
    if caption.strip() == "-":
        caption = None

    t = ud.get("type")
    fid = ud.get("file_id")

    if t == "document":
        await update.message.reply_document(document=fid, caption=caption)
    elif t == "photo":
        await update.message.reply_photo(photo=fid, caption=caption)
    elif t == "video":
        await update.message.reply_video(video=fid, caption=caption)
    else:
        await update.message.reply_text("مشکلی پیش اومد. دوباره امتحان کن.")

    ud.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("لغو شد.")
    return ConversationHandler.END

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN environment variable is not set.")
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, got_media)],
        states={ASK_CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_caption)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
