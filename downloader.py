import os
import requests
import telebot
from telebot import types
import yt_dlp
from mutagen.id3 import ID3, APIC, error

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
    """دریافت و ارسال اطلاعات و کاور پلی‌لیست"""
    bot.send_message(chat_id, "در حال دریافت اطلاعات آلبوم / پلی‌لیست...")
    
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
            
            thumb_url = info.get('thumbnail')
            if not thumb_url and entries:
                first_entry = list(entries)[0]
                if isinstance(first_entry, dict):
                    thumb_url = first_entry.get('thumbnail')

            caption = (
                f"📋 **اطلاعات آلبوم / پلی‌لیست**\n\n"
                f"📌 **عنوان:** {title}\n"
                f"👤 **سازنده:** {uploader}\n"
                f"🔢 **تعداد ترک‌ها:** {total_tracks}"
            )

            if thumb_url:
                try:
                    bot.send_photo(chat_id, photo=thumb_url, caption=caption, parse_mode="Markdown")
                except Exception:
                    bot.send_message(chat_id, caption, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, caption, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(chat_id, f"خطا در دریافت اطلاعات اولیه: {str(e)}")

def embed_cover_art(mp3_path, thumb_path):
    """تزریق دستی عکس کاور به داخل متادیتای ID3 فایل MP3"""
    if not os.path.exists(mp3_path) or not os.path.exists(thumb_path):
        return
    try:
        audio = ID3(mp3_path)
    except error:
        audio = ID3()

    try:
        with open(thumb_path, 'rb') as albumart:
            audio.add(
                APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,
                    desc=u'Cover',
                    data=albumart.read()
                )
            )
        audio.save(mp3_path)
    except Exception as e:
        print(f"Error embedding cover: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    url = user_data.get(chat_id)

    if not url:
        bot.answer_callback_query(call.id, "لینک یافت نشد! لطفاً دوباره لینک را ارسال کنید.")
        return

    bot.answer_callback_query(call.id, "دانلود شروع شد...")
    bot.send_message(chat_id, "🚀 شروع پردازش و دانلود...")

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
                    'key': 'FFmpegMetadata',
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
            'ignoreerrors': True,
        }

    try:
        os.makedirs('downloads', exist_ok=True)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if info is not None:
                if 'entries' in info and info['entries']:
                    for entry in info['entries']:
                        if entry:
                            process_file_and_send(chat_id, ydl, entry, call.data)
                else:
                    process_file_and_send(chat_id, ydl, info, call.data)

        bot.send_message(chat_id, "✅ پروسه دانلود به پایان رسید.")

    except Exception as e:
        bot.send_message(chat_id, f"خطا در پروسه دانلود: {str(e)}")

def process_file_and_send(chat_id, ydl, entry, download_type):
    """پردازش، ارسال و پاکسازی قطعی فایل از روی سرور حتی در صورت بروز خطا"""
    base_name = ydl.prepare_filename(entry)
    base_no_ext, _ = os.path.splitext(base_name)

    files_to_delete = []

    try:
        if download_type == "audio_mp3":
            mp3_file = base_no_ext + ".mp3"
            files_to_delete.append(mp3_file)
            
            thumb_file = None
            for ext in ['.jpg', '.png', '.webp', '.jpeg']:
                t_path = base_no_ext + ext
                if os.path.exists(t_path):
                    thumb_file = t_path
                    files_to_delete.append(t_path)
                    break

            if os.path.exists(mp3_file):
                if thumb_file:
                    embed_cover_art(mp3_file, thumb_file)

                with open(mp3_file, 'rb') as audio:
                    if thumb_file and os.path.exists(thumb_file):
                        with open(thumb_file, 'rb') as t_img:
                            bot.send_audio(
                                chat_id, 
                                audio, 
                                title=entry.get('title'), 
                                performer=entry.get('uploader'),
                                thumb=t_img
                            )
                    else:
                        bot.send_audio(
                            chat_id, 
                            audio, 
                            title=entry.get('title'), 
                            performer=entry.get('uploader')
                        )
        else:
            mp4_file = base_no_ext + ".mp4"
            files_to_delete.append(mp4_file)
            
            if os.path.exists(mp4_file):
                with open(mp4_file, 'rb') as video:
                    bot.send_video(chat_id, video, supports_streaming=True)

    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا در ارسال فایل `{entry.get('title', 'نامشخص')}`: {str(e)}")

    finally:
        # بلاک finally تحت هر شرایطی (چه موفقیت چه خطا) اجرا می‌شود و فایل‌ها را پاک می‌کند
        for fpath in files_to_delete:
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception as del_err:
                    print(f"Error removing file {fpath}: {del_err}")

bot.infinity_polling()