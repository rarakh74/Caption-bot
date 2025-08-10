
import logging, os
from io import BytesIO
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

ASK_CAPTION, ASK_FILENAME = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! فایل/عکس/ویدئو رو بفرست.\n"
        "برای document می‌تونم اسم فایل رو هم عوض کنم.\n"
        "بعد از دریافت مدیا، اول کپشن و بعد (در صورت document) اسم جدید رو می‌پرسم."
    )

async def got_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    ud = context.user_data
    ud.clear()

    if msg.document:
        ud["type"] = "document"
        ud["file_id"] = msg.document.file_id
        ud["orig_name"] = msg.document.file_name
    elif msg.photo:
        ud["type"] = "photo"
        ud["file_id"] = msg.photo[-1].file_id
    elif msg.video:
        ud["type"] = "video"
        ud["file_id"] = msg.video.file_id
    else:
        await msg.reply_text("فقط document/photo/video رو پشتیبانی می‌کنم.")
        return ConversationHandler.END

    await msg.reply_text("کپشن جدید رو بفرست. اگه کپشن نمی‌خوای، بنویس «-».")
    return ASK_CAPTION

async def got_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    caption = update.message.text
    ud["caption"] = None if caption.strip() == "-" else caption

    if ud.get("type") == "document":
        await update.message.reply_text(
            f"اسم فایل جدید رو بنویس (الان: {ud.get('orig_name')}).\n"
            "اگه نمی‌خوای عوض شه، بنویس «-»."
        )
        return ASK_FILENAME

    # برای photo/video
    t = ud.get("type")
    fid = ud.get("file_id")
    if t == "photo":
        await update.message.reply_photo(photo=fid, caption=ud.get("caption"))
    elif t == "video":
        await update.message.reply_video(video=fid, caption=ud.get("caption"))
    ud.clear()
    return ConversationHandler.END

async def got_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    new_name = update.message.text.strip()

    # دانلود فایل برای امکان تغییر نام
    fid = ud.get("file_id")
    file = await context.bot.get_file(fid)
    buf = BytesIO()
    await file.download_to_memory(out=buf)
    buf.seek(0)

    if new_name == "-" or new_name == "":
        # حفظ نام قبلی
        new_name = ud.get("orig_name") or "file.bin"

    # اگر کاربر پسوند نداد، از پسوند قبلی استفاده کن
    if "." not in new_name and ud.get("orig_name") and "." in ud["orig_name"]:
        ext = ud["orig_name"].split(".")[-1]
        new_name = f"{new_name}.{ext}"

    input_file = InputFile(buf, filename=new_name)
    await update.message.reply_document(document=input_file, caption=ud.get("caption"))
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
        states={
            ASK_CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_caption)],
            ASK_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_filename)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
