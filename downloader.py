import os
import threading
import time
import telebot
from telebot import types
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

bot = telebot.TeleBot(BOT_TOKEN)

# ذخیره اطلاعات به ازای هر پیام (برای جلوگیری از تداخل)
user_data = {}  # کلید: (chat_id, message_id) -> url

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "لطفاً یک لینک معتبر ارسال کنید.")
        return

    # ذخیره URL همراه با message_id
    user_data[(message.chat.id, message.message_id)] = url

    # اگر پلی‌لیست تشخیص داده شد، اطلاعات را ارسال کن
    if "playlist" in url or "list=" in url or "album" in url:
        send_playlist_info(message.chat.id, url)

    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_high = types.InlineKeyboardButton("🎥 کیفیت 1080p", callback_data="quality_1080")
    btn_mid = types.InlineKeyboardButton("🎥 کیفیت 720p", callback_data="quality_720")
    btn_low = types.InlineKeyboardButton("🎥 کیفیت 480p", callback_data="quality_480")
    btn_audio = types.InlineKeyboardButton("🎵 دانلود به صورت موزیک (MP3 + کاور)", callback_data="audio_mp3")
    markup.add(btn_high, btn_mid, btn_low, btn_audio)

    bot.send_message(
        message.chat.id,
        "لطفاً کیفیت یا نوع دانلود را انتخاب کنید:",
        reply_markup=markup,
        reply_to_message_id=message.message_id
    )

def send_playlist_info(chat_id, url):
    """دریافت و ارسال اطلاعات و کاور پلی‌لیست (همگام)"""
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
            total_tracks = len(entries) if entries else 1

            thumb_url = info.get('thumbnail')
            if not thumb_url and entries:
                first_entry = entries[0] if isinstance(entries, list) else next(iter(entries), None)
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
                except:
                    bot.send_message(chat_id, caption, parse_mode="Markdown")
            else:
                bot.send_message(chat_id, caption, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"خطا در دریافت اطلاعات اولیه: {str(e)}")

def process_file_and_send(chat_id, ydl, entry, download_type, message_id):
    """پردازش، ارسال و پاک‌سازی فایل (با شناسه پیام برای نام‌گذاری یکتا)"""
    base_name = ydl.prepare_filename(entry)
    base_no_ext, _ = os.path.splitext(base_name)

    # نام فایل با شناسه یکتا (برای جلوگیری از تداخل)
    unique_id = f"{chat_id}_{message_id}_{entry.get('id', 'unknown')}"
    final_mp3 = f"downloads/{unique_id}.mp3"
    final_mp4 = f"downloads/{unique_id}.mp4"

    files_to_delete = []

    try:
        if download_type == "audio_mp3":
            mp3_file = base_no_ext + ".mp3"
            # اگر فایل با نام اصلی وجود دارد، به نام یکتا تغییر نام بده
            if os.path.exists(mp3_file):
                os.rename(mp3_file, final_mp3)
                files_to_delete.append(final_mp3)
            else:
                # احتمالاً فایل از قبل با نام یکتا ذخیره شده
                if os.path.exists(final_mp3):
                    pass
                else:
                    raise FileNotFoundError("فایل MP3 پیدا نشد")

            # پیدا کردن تصویر کاور
            thumb_file = None
            for ext in ['.jpg', '.png', '.webp', '.jpeg']:
                t_path = base_no_ext + ext
                if os.path.exists(t_path):
                    thumb_file = t_path
                    files_to_delete.append(t_path)
                    break

            if os.path.exists(final_mp3):
                # ارسال فایل صوتی
                with open(final_mp3, 'rb') as audio:
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
            # ویدیو
            video_file = base_no_ext + ".mp4"
            if os.path.exists(video_file):
                os.rename(video_file, final_mp4)
                files_to_delete.append(final_mp4)

            if os.path.exists(final_mp4):
                with open(final_mp4, 'rb') as video:
                    bot.send_video(chat_id, video, supports_streaming=True, caption=entry.get('title'))
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا در ارسال فایل `{entry.get('title', 'نامشخص')}`: {str(e)}")
    finally:
        for fpath in files_to_delete:
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except:
                    pass

def download_and_send(call, url, message_id):
    """تابع دانلود که در ترد جداگانه اجرا می‌شود"""
    chat_id = call.message.chat.id
    bot.send_message(chat_id, "🚀 شروع پردازش و دانلود...")

    if call.data == "audio_mp3":
        ydl_opts = {
            'format': 'bestaudio/best',
            'writethumbnail': True,
            'ignoreerrors': True,
            'postprocessors': [
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'},
                {'key': 'FFmpegMetadata'}
            ],
            'outtmpl': f'downloads/{chat_id}_{message_id}_%(id)s.%(ext)s',
            'embedthumbnail': False,  # ما خودمان کاور را تزریق می‌کنیم
        }
    else:
        height_map = {"quality_1080": 1080, "quality_720": 720, "quality_480": 480}
        max_h = height_map.get(call.data, 720)
        ydl_opts = {
            'format': f'bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': f'downloads/{chat_id}_{message_id}_%(id)s.%(ext)s',
            'merge_output_format': 'mp4',
            'ignoreerrors': True,
        }

    try:
        os.makedirs('downloads', exist_ok=True)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is not None:
                entries = info.get('entries')
                if entries:
                    total = len(entries)
                    for idx, entry in enumerate(entries):
                        if entry:
                            process_file_and_send(chat_id, ydl, entry, call.data, message_id)
                            # تأخیر برای جلوگیری از محدودیت نرخ
                            time.sleep(2)
                            # گزارش پیشرفت
                            if (idx + 1) % 5 == 0:
                                bot.send_message(chat_id, f"پیشرفت: {idx+1}/{total}")
                else:
                    process_file_and_send(chat_id, ydl, info, call.data, message_id)
        bot.send_message(chat_id, "✅ پروسه دانلود به پایان رسید.")
    except Exception as e:
        bot.send_message(chat_id, f"خطا در پروسه دانلود: {str(e)}")

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    original_message = call.message.reply_to_message
    if not original_message:
        bot.answer_callback_query(call.id, "لینک یافت نشد! لطفاً دوباره لینک را ارسال کنید.")
        return

    # بازیابی URL از پیام اصلی (با message_id)
    url = user_data.get((call.message.chat.id, original_message.message_id))
    if not url:
        bot.answer_callback_query(call.id, "لینک منقضی شده، لطفاً دوباره ارسال کنید.")
        return

    bot.answer_callback_query(call.id, "دانلود شروع شد...")
    # اجرای دانلود در ترد جداگانه
    threading.Thread(target=download_and_send, args=(call, url, original_message.message_id)).start()

if __name__ == "__main__":
    bot.infinity_polling(timeout=30, skip_pending=True)
