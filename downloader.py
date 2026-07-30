import os
import telebot
#import static_ffmpeg
import yt_dlp

# Automatically setup FFmpeg paths
#static_ffmpeg.add_paths()

DOWNLOAD_DIR = 'temp_downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Retrieve BOT_TOKEN from environment variables or set it directly
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8643780189:AAHHrzfft00QxbHSLZuGp5UFlqFrIaPLjtA")

bot = telebot.TeleBot(BOT_TOKEN)

def download_media_file(url, message_id):
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{message_id}_%(title)s.%(ext)s")
        
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': outtmpl,
        'ignoreerrors': True,
        'max_filesize': 50 * 1024 * 1024,  # Telegram's 50MB limit
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        # Adjust file extension after MP3 conversion
        base_path = os.path.splitext(filename)[0]
        mp3_path = base_path + ".mp3"
        if os.path.exists(mp3_path):
            return mp3_path
            
        return filename

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(
        message, 
        "Welcome! Send me a link to a video or music (YouTube, SoundCloud, etc.) and I will download it for you."
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    url = message.text.strip()
    
    if not url.startswith("http"):
        bot.reply_to(message, "Please provide a valid URL.")
        return

    status_msg = bot.reply_to(message, "⏳ Processing link and downloading...")
    file_path = None

    try:
        file_path = download_media_file(url, message.message_id)

        if not file_path or not os.path.exists(file_path):
            bot.edit_message_text(
                "❌ Download failed or file size exceeds Telegram's 50MB limit.", 
                chat_id=status_msg.chat.id, 
                message_id=status_msg.message_id
            )
            return

        bot.edit_message_text(
            "⬆️ Uploading to Telegram...", 
            chat_id=status_msg.chat.id, 
            message_id=status_msg.message_id
        )
        
        with open(file_path, 'rb') as audio_file:
            bot.send_audio(message.chat.id, audio_file, caption="Here is your audio file! 🎧")
            
        bot.delete_message(chat_id=status_msg.chat.id, message_id=status_msg.message_id)

    except Exception as e:
        bot.edit_message_text(
            f"❌ Error occurred:\n`{str(e)[:150]}`", 
            chat_id=status_msg.chat.id, 
            message_id=status_msg.message_id, 
            parse_mode="Markdown"
        )

    finally:
        # Cleanup temporary downloaded file
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()