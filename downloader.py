import os
import telebot
from telebot import types
import yt_dlp

BOT_TOKEN = "8643780189:AAHHrzfft00QxbHSLZuGp5UFlqFrIaPLjtA"
bot = telebot.TeleBot(BOT_TOKEN)

user_data = {}

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "لطفاً یک لینک معتبر ارسال کنید.")
        return

    user_data[message.chat.id] = url

    # بررسی اینکه آیا لینک مربوط به پلی‌لیست است یا خیر
    if "playlist" in url or "list=" in url:
        send_playlist_info(message.chat.id, url)

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_high = types.InlineKeyboardButton("🎥 کیفیت 1080p", callback_data="quality_1080")
    btn_mid = types.InlineKeyboardButton("🎥 کیفیت 720p", callback_data="quality_720")
    btn_low = types.InlineKeyboardButton("🎥 کیفیت 480p", callback_data="quality_480")
    btn_audio = types.InlineKeyboardButton("🎵 دانلود به صورت موزیک (MP3 + کاور)", callback_data="audio_mp3")

    markup.add(btn_high, btn_mid, btn_low, btn_audio)
    bot.send_message(message.chat.id, "لطفاً کیفیت یا نوع دانلود را انتخاب کنید:", reply_markup=markup)

def send_playlist_info(chat_id, url):
    """استخراج مشخصات و کاور پلی‌لیست و ارسال آن قبل از دانلود"""
    bot.send_message(chat_id, "در حال دریافت اطلاعات پلی‌لیست...")
    
    ydl_opts = {
        'extract_flat': True,  # فقط دریافت متادیتا بدون دانلود فایل‌ها
        'skip_download': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            title = info.get('title', 'نامشخص')
            uploader = info.get('uploader', info.get('channel', 'نامشخص'))
            entries = info.get('entries', [])
            total_tracks = len(list(entries)) if entries else 0
            
            # دریافت کاور پلی‌لیست یا اولین ویدیو
            thumbnails = info.get('thumbnails', [])
            thumb_url = thumbnails[-1]['url'] if thumbnails else None

            caption = (
                f"📋 **اطلاعات پلی‌لیست**\n\n"
                f"📌 **عنوان:** {title}\n"
                f"👤 **سازنده:** {uploader}\n"
                f"🔢 **تعداد ترک‌ها:** {total_tracks} عدد"
            )

            if thumb_url:
                bot.send_photo(chat_id, photo=thumb_url, caption=caption, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, caption, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(chat_id, f"خطا در دریافت اطلاعات پلی‌لیست: {str(e)}")

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    url = user_data.get(chat_id)

    if not url:
        bot.answer_callback_query(call.id, "لینک یافت نشد! لطفاً دوباره لینک را ارسال کنید.")
        return

    bot.answer_callback_query(call.id, "در حال پردازش درخواست...")
    bot.edit_message_text("در حال دانلود، لطفاً صبر کنید...", chat_id=chat_id, message_id=call.message.message_id)

    if call.data == "audio_mp3":
        ydl_opts = {
            'format': 'bestaudio/best',
            'writethumbnail': True,  # دانلود کاور
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                },
                {
                    'key': 'EmbedThumbnail',  # تزریق کاور به درون فایل MP3
                },
                {
                    'key': 'FFmpegMetadata',  # تزریق عنوان، خواننده و متادیتا
                }
            ],
            'outtmpl': 'downloads/%(title)s.%(ext)s',
        }
    else:
        height_map = {
            "quality_1080": 1080,
            "quality_720": 720,
            "quality_480": 480
        }
        max_h = height_map.get(call.data, 720)
        
        ydl_opts = {
            'format': f'bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'merge_output_format': 'mp4',
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # در صورتی که لینک یک پلی‌لیست باشد
            if 'entries' in info:
                for entry in info['entries']:
                    process_and_send_file(chat_id, ydl, entry, call.data)
            else:
                process_and_send_file(chat_id, ydl, info, call.data)

    except Exception as e:
        bot.send_message(chat_id, f"خطا در دانلود: {str(e)}")

def process_and_send_file(chat_id, ydl, info, download_type):
    """ارسال فایل دانلود شده به تلگرام و پاکسازی آن"""
    filename = ydl.prepare_filename(info)

    if download_type == "audio_mp3":
        filename = os.path.splitext(filename)[0] + ".mp3"
        if os.path.exists(filename):
            with open(filename, 'rb') as audio:
                bot.send_audio(
                    chat_id, 
                    audio, 
                    title=info.get('title'), 
                    performer=info.get('uploader')
                )
    else:
        if not filename.endswith('.mp4'):
            base, _ = os.path.splitext(filename)
            if os.path.exists(base + '.mp4'):
                filename = base + '.mp4'

        if os.path.exists(filename):
            with open(filename, 'rb') as video:
                bot.send_video(chat_id, video, supports_streaming=True)

    # پاکسازی فایل پس از ارسال
    if os.path.exists(filename):
        os.remove(filename)

bot.infinity_polling()