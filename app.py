
import logging, os, tempfile, shutil, subprocess
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

ASK_CAPTION, ASK_FILENAME, ASK_PDF_QUALITY = range(3)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! فایل/عکس/ویدئو رو بفرست.\n"
        "برای document می‌تونم اسم فایل رو هم عوض کنم و اگر PDF بود حجمش رو کم کنم."
    )

async def got_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    ud = context.user_data
    ud.clear()

    if msg.document:
        ud["type"] = "document"
        ud["file_id"] = msg.document.file_id
        ud["orig_name"] = msg.document.file_name or "file.bin"
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

    # photo/video: فقط کپشن
    t, fid = ud.get("type"), ud.get("file_id")
    if t == "photo":
        await update.message.reply_photo(photo=fid, caption=ud.get("caption"))
    elif t == "video":
        await update.message.reply_video(video=fid, caption=ud.get("caption"))
    ud.clear()
    return ConversationHandler.END

def _guess_with_ext(name: str, fallback: str) -> str:
    name = (name or "").strip()
    if not name or name == "-":
        return fallback
    if "." not in name and "." in fallback:
        ext = fallback.split(".")[-1]
        return f"{name}.{ext}"
    return name

def compress_pdf(input_path: str, output_path: str, level: str):
    # level: "1"=printer, "2"=ebook, "3"=screen
    preset = {"1":"printer", "2":"ebook", "3":"screen"}.get(level, "ebook")
    subprocess.run([
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS=/{preset}",
        "-dNOPAUSE", "-dQUIET", "-dBATCH",
        f"-sOutputFile={output_path}",
        input_path
    ], check=True)

async def got_filename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    new_name = _guess_with_ext(update.message.text, ud.get("orig_name") or "file.bin")

    # دانلود فایل روی دیسک (برای فایل‌های بزرگ پایدارتره)
    tmpdir = tempfile.mkdtemp(prefix="tgdoc_")
    ud["tmpdir"] = tmpdir
    src_path = os.path.join(tmpdir, "src.pdf" if new_name.lower().endswith(".pdf") else "src.bin")
    dst_path = os.path.join(tmpdir, "dst.pdf")

    file = await context.bot.get_file(ud.get("file_id"))
    await file.download_to_drive(custom_path=src_path)

    ud["final_name"] = new_name
    if new_name.lower().endswith(".pdf"):
        ud["src_path"] = src_path
        ud["dst_path"] = dst_path
        await update.message.reply_text(
            "میخوای حجم PDF رو کم کنم؟ یکی رو انتخاب کن:\n"
            "1️⃣ بالا (کیفیت بهتر، کاهش کمتر)\n"
            "2️⃣ متوسط (پیشنهادی)\n"
            "3️⃣ پایین (حجم خیلی کم)"
        )
        return ASK_PDF_QUALITY

    # غیر PDF: فقط rename/caption و آپلود
    with open(src_path, "rb") as f:
        await update.message.reply_document(document=InputFile(f, filename=new_name), caption=ud.get("caption"))

    shutil.rmtree(tmpdir, ignore_errors=True)
    ud.clear()
    return ConversationHandler.END

async def got_pdf_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    choice = update.message.text.strip()
    src_path, dst_path = ud.get("src_path"), ud.get("dst_path")
    try:
        compress_pdf(src_path, dst_path, choice)
        send_path = dst_path if os.path.exists(dst_path) and os.path.getsize(dst_path) < os.path.getsize(src_path) else src_path
    except Exception as e:
        logger.exception("PDF compress failed: %s", e)
        await update.message.reply_text("نتونستم فشرده‌سازی PDF رو انجام بدم، همون فایل اصلی رو می‌فرستم.")
        send_path = src_path

    with open(send_path, "rb") as f:
        await update.message.reply_document(document=InputFile(f, filename=ud.get("final_name")), caption=ud.get("caption"))

    tmpdir = ud.get("tmpdir")
    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)
    ud.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    tmpdir = ud.get("tmpdir")
    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)
    ud.clear()
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
            ASK_PDF_QUALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_pdf_quality)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
