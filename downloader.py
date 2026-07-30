import json
import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import static_ffmpeg
import yt_dlp

# تنظیم خودکار مسیرهای FFmpeg برای تبدیل‌های صوتی
static_ffmpeg.add_paths()

CONFIG_FILE = 'config.json'
DOWNLOAD_DIR = 'temp_downloads'

# مطمئن می‌شویم پوشه موقت دانلود وجود دارد
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def load_config():
    """Load settings from JSON file if available."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'format': 'bestaudio/best', 'choice_code': '5', 'is_audio_only': True}

# دریافت اطلاعات از متغیرهای محیطی یا مقادیر پیش‌فرض
API_ID = int(os.environ.get("API_ID", "1234567"))  # جایگزین با API_ID خودتان
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")

app = Client("media_downloader_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def download_media_file(url, config, message_id):
    is_audio = config.get('is_audio_only', True)
    
    # مسیردهی ایمن داخل پوشه temp_downloads
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{message_id}_%(title)s.%(ext)s")
        
    ydl_opts = {
        'format': config.get('format', 'bestaudio/best'),
        'outtmpl': outtmpl,
        'ignoreerrors': True,
        'max_filesize': 50 * 1024 * 1024,  # محدودیت ۵۰ مگابایتی تلگرام
    }
    
    if is_audio:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        # اگر فایل به mp3 تبدیل شده باشد، پسوند را اصلاح می‌کنیم
        if is_audio:
            base_path = os.path.splitext(filename)[0]
            mp3_path = base_path + ".mp3"
            if os.path.exists(mp3_path):
                return mp3_path
                
        return filename

@app.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    await message.reply_text("سلام! لینک ویدیو یا موزیک را بفرستید تا برایتان دانلود کنم.")

@app.on_message(filters.text & ~filters.command(["start", "help"]))
async def handle_download(client: Client, message: Message):
    url = message.text.strip()
    
    if not url.startswith("http"):
        await message.reply_text("لطفاً یک لینک معتبر وارد کنید.")
        return

    status_msg = await message.reply_text("⏳ در حال بررسی لینک و دانلود...")
    config = load_config()
    loop = asyncio.get_event_loop()
    file_path = None

    try:
        # اجرای دانلود در thread جداگانه برای جلوگیری از قفل شدن ربات
        file_path = await loop.run_in_executor(None, download_media_file, url, config, message.id)

        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text("❌ دانلود ناموفق بود یا حجم فایل بیشتر از ۵۰ مگابایت است.")
            return

        await status_msg.edit_text("⬆️ در حال آپلود فایل به تلگرام...")
        
        if config.get('is_audio_only', True):
            await message.reply_audio(audio=file_path, caption="خدمت شما! 🎧")
        else:
            await message.reply_video(video=file_path, caption="خدمت شما! 🎬")
            
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ خطا در پردازش:\n`{str(e)[:150]}`")

    finally:
        # پاکسازی فایل پس از ارسال
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

if __name__ == "__main__":
    print("Bot is running...")
    app.run()