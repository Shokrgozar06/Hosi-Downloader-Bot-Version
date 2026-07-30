import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import static_ffmpeg
import yt_dlp

# تنظیم خودکار مسیرهای FFmpeg
static_ffmpeg.add_paths()

# اطلاعات ربات (از my.telegram.org و BotFather@)
API_ID = int(os.environ.get("API_ID", "1234567"))
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")

app = Client("downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    await message.reply_text("سلام! لینک ویدیو یا موزیک (SoundCloud, YouTube و...) را بفرستید تا دانلود کنم.")

@app.on_message(filters.text & ~filters.command(["start", "help"]))
async def handle_download(client: Client, message: Message):
    url = message.text.strip()
    
    if not url.startswith("http"):
        await message.reply_text("لطفاً یک لینک معتبر وارد کنید.")
        return

    status_msg = await message.reply_text("⏳ در حال بررسی لینک و دانلود...")
    
    download_dir = "downloads"
    os.makedirs(download_dir, exist_ok=True)
    out_template = os.path.join(download_dir, f"{message.id}_%(title)s.%(ext)s")

    # تنظیمات پیش‌فرض برای دانلود صوتی با فرمت MP3
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': out_template,
        'ignoreerrors': True,
        'max_filesize': 50 * 1024 * 1024,  # محدودیت ۵۰ مگابایت تلگرام
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    loop = asyncio.get_event_loop()

    try:
        def run_dl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        file_path = await loop.run_in_executor(None, run_dl)

        # اصلاح پسوند فایل در صورت تبدیل به MP3
        base_path = os.path.splitext(file_path)[0]
        mp3_path = base_path + ".mp3"
        if os.path.exists(mp3_path):
            file_path = mp3_path

        if not os.path.exists(file_path):
            await status_msg.edit_text("❌ دانلود ناموفق بود یا حجم فایل بیشتر از ۵۰ مگابایت است.")
            return

        await status_msg.edit_text("⬆️ در حال آپلود فایل به تلگرام...")
        
        await message.reply_audio(audio=file_path, caption="خدمت شما! 🎧")
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ خطا:\n`{str(e)[:150]}`")

    finally:
        # پاکسازی فایل از سرور جهت جلوگیری از پر شدن حافظه
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    print("Bot is running...")
    app.run()