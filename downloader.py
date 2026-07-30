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

    # ارسال پیش‌نمایش و اطلاعات پلی‌لیست در صورت وجود
    if "playlist" in url or "list=" in url or "album" in url:
        send_playlist_info(message.chat.id, url)

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_high = types.InlineKeyboardButton("🎥 کیفیت 1080p", callback_data="quality_1080")
    btn_mid = types.InlineKeyboardButton("🎥 کیفیت 720p", callback_data="quality_720")
    btn_low = types.InlineKeyboardButton("🎥 کیفیت 480p", callback_data="quality_480")
    btn_audio = types.InlineKeyboardButton("🎵 دانلود به صورت موزیک (MP3 + کاور)", callback_data="audio_mp3")

    markup.add(btn_high, btn_mid, btn_low, btn_audio)
    bot.send_message(message.chat.id, "لطفاً کیفیت یا نوع دانلود را انتخاب کنید:", reply_markup=markup)

def send_playlist_info(chat_id, url):
    """استخراج مشخصات کلی پلی‌لیست قبل از شروع دانلود"""
    bot.send_message(chat_id, "در حال دریافت اطلاعات پلی‌لیست/آلبوم...")
    
    ydl_opts = {
        'extract_flat': True,
        'skip_download': True,
        'ignoreerrors': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return

            title = info.get('title', 'نامشخص')
            uploader = info.get('uploader', info.get('channel', 'نامشخص'))
            entries = info.get('entries', [])
            total_tracks = len(list(entries)) if entries else 1
            
            thumbnails = info.get('thumbnails', [])
            thumb_url = thumbnails[-1]['url'] if thumbnails else None

            caption = (
                f"📋 **اطلاعات آلبوم / پلی‌لیست**\n\n"
                f"📌 **عنوان:** {title}\n"
                f"👤 **سازنده:** {uploader}\n"
                f"🔢 **تعداد:** {total_tracks} ترک"
            )

            if thumb_url:
                bot.send_photo(chat_id, photo=thumb_url, caption=caption, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, caption, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(chat_id, f"خطا در دریافت اطلاعات اولیه: {str(e)}")

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    url = user_data.get(chat_id)

    if not url:
        bot.answer_callback_query(call.id, "لینک یافت نشد! لطفاً دوباره لینک را ارسال کنید.")
        return

    bot.answer_callback_query(call.id, "دانلود شروع شد...")
    status_msg = bot.send_message(chat_id, "🚀 شروع پردازش و دانلود تک‌به‌تک...")

    # هوک اختصاصی برای ارسال لحظه‌ای فایل به محض پایان دانلود هر ترک
    def my_hook(d):
        if d['status'] == 'finished':
            filepath = d['filename']
            # اگر فرمت اولیه تبدیل شده باشد، مسیر فایل را تصحیح می‌کند
            if call.data == "audio_mp3":
                base, _ = os.path.splitext(filepath)
                filepath = base + ".mp3"
            
            upload_single_file(chat_id, filepath, call.data)

    if call.data == "audio_mp3":
        ydl_opts = {
            'format': 'bestaudio/best',
            'writethumbnail': True,
            'ignoreerrors': True,
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                },
                {
                    'key': 'EmbedThumbnail',
                },
                {
                    'key': 'FFmpegMetadata',
                }
            ],
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'progress_hooks': [my_hook],
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
            'ignoreerrors': True,
            'progress_hooks': [my_hook],
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        bot.send_message(chat_id, "✅ دانلود و ارسال تمام فایل‌ها با موفقیت به پایان رسید.")

    except Exception as e:
        bot.send_message(chat_id, f"خطا در پروسه دانلود: {str(e)}")

def upload_single_file(chat_id, filepath, download_type):
    """ارسال تک‌به‌تک فایل بلافاصله پس از دانلود و حذف آن از سرور"""
    if not os.path.exists(filepath):
        # بررسی پسوند در صورت تغییر نام توسط ffmpeg
        base, _ = os.path.splitext(filepath)
        if os.path.exists(base + ".mp3"):
            filepath = base + ".mp3"
        elif os.path.exists(base + ".mp4"):
            filepath = base + ".mp4"
        else:
            return

    try:
        if download_type == "audio_mp3":
            with open(filepath, 'rb') as audio:
                bot.send_audio(chat_id, audio)
        else:
            with open(filepath, 'rb') as video:
                bot.send_video(chat_id, video, supports_streaming=True)
    except Exception as e:
        bot.send_message(chat_id, f"خطا در ارسال فایل: {str(e)}")
    finally:
        # حذف آنی فایل برای خالی ماندن فضای سرور
        if os.path.exists(filepath):
            os.remove(filepath)

bot.infinity_polling()