import os
import telebot
from telebot import types
import yt_dlp

BOT_TOKEN = "8643780189:AAHHrzfft00QxbHSLZuGp5UFlqFrIaPLjtA"
bot = telebot.TeleBot(BOT_TOKEN)

# ذخیره موقت لینک‌ها
user_data = {}

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, "لطفاً یک لینک معتبر ارسال کنید.")
        return

    # ذخیره لینک ارسال شده توسط کاربر
    user_data[message.chat.id] = url

    # ساخت منوی شیشه‌ای
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_high = types.InlineKeyboardButton("🎥 کیفیت 1080p", callback_data="quality_1080")
    btn_mid = types.InlineKeyboardButton("🎥 کیفیت 720p", callback_data="quality_720")
    btn_low = types.InlineKeyboardButton("🎥 کیفیت 480p", callback_data="quality_480")
    btn_audio = types.InlineKeyboardButton("🎵 دانلود به صورت موزیک (MP3)", callback_data="audio_mp3")

    markup.add(btn_high, btn_mid, btn_low, btn_audio)

    bot.send_message(message.chat.id, "لطفاً کیفیت یا نوع دانلود را انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    url = user_data.get(chat_id)

    if not url:
        bot.answer_callback_query(call.id, "لینک یافت نشد! لطفاً دوباره لینک را ارسال کنید.")
        return

    bot.answer_callback_query(call.id, "در حال پردازش درخواست...")
    bot.edit_message_text("در حال دانلود، لطفاً صبر کنید...", chat_id=chat_id, message_id=call.message.message_id)

    # تنظیمات yt-dlp بر اساس دکمه انتخاب شده
    ydl_opts = {}
    
    if call.data == "audio_mp3":
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': 'downloads/%(title)s.%(ext)s',
        }
    elif call.data == "quality_1080":
        ydl_opts = {'format': 'bestvideo[height<=1080]+bestaudio/best', 'outtmpl': 'downloads/%(title)s.%(ext)s'}
    elif call.data == "quality_720":
        ydl_opts = {'format': 'bestvideo[height<=720]+bestaudio/best', 'outtmpl': 'downloads/%(title)s.%(ext)s'}
    elif call.data == "quality_480":
        ydl_opts = {'format': 'bestvideo[height<=480]+bestaudio/best', 'outtmpl': 'downloads/%(title)s.%(ext)s'}

    # اجرای دانلود و ارسال فایل
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            if call.data == "audio_mp3":
                filename = os.path.splitext(filename)[0] + ".mp3"
                with open(filename, 'rb') as audio:
                    bot.send_audio(chat_id, audio)
            else:
                with open(filename, 'rb') as video:
                    bot.send_video(chat_id, video)

            # پاک‌سازی فایل دانلود شده بعد از ارسال
            if os.path.exists(filename):
                os.remove(filename)

    except Exception as e:
        bot.send_message(chat_id, f"خطا در دانلود: {str(e)}")

bot.infinity_polling()