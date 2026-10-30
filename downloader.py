import os
import json
import logging
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import telebot
from telebot import types
import yt_dlp
from dotenv import load_dotenv

# ----------------------------------------------------
# Configuration & Logging (English Console Logs)
# ----------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("DownloaderBot")

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN") or "9171992034:AAE8bJ6US1VBp8oEgUV6OJRljip7VT551ns"
if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable not set! Please check your .env file.")
    raise ValueError("BOT_TOKEN یافت نشد! لطفاً فایل .env را تنظیم کنید.")

# Increase Telegram network timeouts to prevent aborted write connections on slow networks
telebot.apihelper.READ_TIMEOUT = 300
telebot.apihelper.CONNECT_TIMEOUT = 60

# ----------------------------------------------------
# Local Telegram Bot API Server Configuration (Up to 2GB)
# ----------------------------------------------------
LOCAL_BOT_API_URL = os.getenv("LOCAL_BOT_API_URL", "http://localhost:8081").strip().rstrip("/")

def is_local_bot_api_available(url):
    if not url:
        return False
    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(url)
        urllib.request.urlopen(req, timeout=1.5)
        return True
    except urllib.error.HTTPError:
        # If server responds with 400 or 404, the local bot-api server IS listening!
        return True
    except Exception:
        return False

if is_local_bot_api_available(LOCAL_BOT_API_URL):
    telebot.apihelper.API_URL = f"{LOCAL_BOT_API_URL}/bot{{0}}/{{1}}"
    telebot.apihelper.FILE_URL = f"{LOCAL_BOT_API_URL}/file/bot{{0}}/{{1}}"
    MAX_FILE_SIZE = 1950 * 1024 * 1024  # 1950 MB (approx 2 GB limit)
    logger.info(f"Connected to Local Telegram Bot API at {LOCAL_BOT_API_URL}! Max upload limit increased to 2000 MB (2 GB).")
else:
    MAX_FILE_SIZE = 49.5 * 1024 * 1024  # Standard Telegram 50MB ceiling
    logger.info("Using standard Telegram Bot API (50 MB upload limit).")

bot = telebot.TeleBot(BOT_TOKEN)

# ----------------------------------------------------
# FFmpeg Detection & Linux Container Compatibility
# ----------------------------------------------------
FFMPEG_PATH = None
FFMPEG_DIR = None
try:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    FFMPEG_PATH = ffmpeg_exe
    FFMPEG_DIR = os.path.dirname(ffmpeg_exe)
    if FFMPEG_DIR and FFMPEG_DIR not in os.environ.get("PATH", ""):
        os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")
    
    # Ensure binary named 'ffmpeg' exists for yt-dlp on Linux / Pterodactyl containers
    target_name = "ffmpeg.exe" if os.name == 'nt' else "ffmpeg"
    target_bin = os.path.join(FFMPEG_DIR, target_name)
    if not os.path.exists(target_bin) and os.path.exists(ffmpeg_exe):
        try:
            if hasattr(os, "symlink"):
                os.symlink(ffmpeg_exe, target_bin)
            else:
                shutil.copy2(ffmpeg_exe, target_bin)
            if hasattr(os, "chmod"):
                os.chmod(target_bin, 0o755)
        except Exception:
            pass
    logger.info(f"FFmpeg registered from imageio: {FFMPEG_PATH}")
except Exception as e:
    logger.debug(f"imageio_ffmpeg check failed: {e}")

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception as e:
    logger.debug(f"static_ffmpeg check failed: {e}")

if not FFMPEG_PATH:
    FFMPEG_PATH = shutil.which("ffmpeg")

# ----------------------------------------------------
# Netscape Cookie Validation & Smart Routing
# ----------------------------------------------------
BROWSER_COOKIES = os.getenv("BROWSER_COOKIES", "").strip().lower()

def get_valid_cookie_file(filepath):
    """Validates if a cookie file has Netscape format header to avoid crash."""
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        if os.path.getsize(filepath) < 30:
            return None
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            first_lines = "".join(f.readline() for _ in range(5))
            if "# Netscape HTTP Cookie File" in first_lines or "# HTTP Cookie File" in first_lines:
                return filepath
    except Exception as e:
        logger.warning(f"Error checking cookie file {filepath}: {e}")
    return None

def resolve_cookies_for_platform(platform: str, ydl_opts: dict):
    """
    مسیریابی هوشمند کوکی‌ها برای پلتفرم‌های مختلف:
    1. اولویت اول: فایل اختصاصی مانند cookies_twitter.txt، cookies_youtube.txt و ...
    2. اولویت دوم: فایل عمومی cookies.txt
    3. اولویت سوم: خواندن مستقیم کوکی مرورگر در صورت تنظیم BROWSER_COOKIES در .env
    """
    cookie_map = {
        "twitter": ["cookies_twitter.txt", "cookies_x.txt"],
        "youtube": ["cookies_youtube.txt"],
        "yt_music": ["cookies_youtube.txt"],
        "instagram": ["cookies_instagram.txt"],
        "tiktok": ["cookies_tiktok.txt"],
        "soundcloud": ["cookies_soundcloud.txt"]
    }

    # 1. بررسی فایل اختصاصی هر پلتفرم
    for candidate in cookie_map.get(platform, []):
        valid_file = get_valid_cookie_file(candidate)
        if valid_file:
            ydl_opts['cookiefile'] = valid_file
            logger.info(f"Using platform-specific cookie file '{valid_file}' for {platform}")
            return

    # 2. بررسی فایل عمومی cookies.txt
    general = get_valid_cookie_file("cookies.txt")
    if general:
        ydl_opts['cookiefile'] = general
        logger.info(f"Using general cookie file 'cookies.txt' for {platform}")
        return

    # 3. خواندن مستقیم کوکی از مرورگر در صورت تنظیم در .env
    if BROWSER_COOKIES and BROWSER_COOKIES in ['chrome', 'firefox', 'edge', 'brave', 'opera', 'safari', 'vivaldi']:
        ydl_opts['cookiesfrombrowser'] = (BROWSER_COOKIES,)
        logger.info(f"Using direct browser cookies from '{BROWSER_COOKIES}' for {platform}")

def configure_ydl_base_options(ydl_opts: dict, platform: str = "general"):
    """
    اعمال تنظیمات پایه و پایدار برای yt-dlp:
    1. فعال‌سازی دانلود خودکار چالش‌های جاوااسکریپتی یوتیوب (EJS solver)
    2. شناسایی ران‌تایم‌های مختلف جاوااسکریپت (Node.js, Deno, Bun)
    3. تنظیم خودکار مسیر FFmpeg
    4. اتصال هوشمند کوکی‌ها
    """
    ydl_opts['remote_components'] = ['ejs:github']
    ydl_opts['js_runtimes'] = ['deno', 'node', 'quickjs', 'bun']

    if FFMPEG_PATH:
        ydl_opts['ffmpeg_location'] = FFMPEG_PATH
    elif FFMPEG_DIR:
        ydl_opts['ffmpeg_location'] = FFMPEG_DIR

    resolve_cookies_for_platform(platform, ydl_opts)

# ----------------------------------------------------
# Concurrency & System Limits
# ----------------------------------------------------
MAX_CONCURRENT_DOWNLOADS = 3       # Resource optimization limit
MAX_PLAYLIST_ITEMS = 15            # Avoid server bandwidth starvation

executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS)
analysis_executor = ThreadPoolExecutor(max_workers=4)

active_downloads = set()
active_downloads_lock = threading.Lock()

user_data = {}
user_data_lock = threading.Lock()

DOWNLOADS_ROOT = os.path.abspath("downloads")
os.makedirs(DOWNLOADS_ROOT, exist_ok=True)

# ----------------------------------------------------
# Persistent User Settings (Language: Persian / English)
# ----------------------------------------------------
SETTINGS_FILE = "user_settings.json"
user_settings = {}
user_settings_lock = threading.Lock()

def load_user_settings():
    global user_settings
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                user_settings = json.load(f)
                logger.info(f"Loaded settings for {len(user_settings)} users.")
        except Exception as e:
            logger.error(f"Failed to load user settings: {e}")

def save_user_settings():
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(user_settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save user settings: {e}")

load_user_settings()

def get_user_lang(chat_id):
    with user_settings_lock:
        return user_settings.get(str(chat_id), {}).get("lang", "fa")

def set_user_lang(chat_id, lang):
    with user_settings_lock:
        if str(chat_id) not in user_settings:
            user_settings[str(chat_id)] = {}
        user_settings[str(chat_id)]["lang"] = lang
        save_user_settings()
    logger.info(f"User {chat_id} changed language to: {lang}")

# ----------------------------------------------------
# Localization Strings (FA / EN)
# ----------------------------------------------------
STRINGS = {
    "fa": {
        "welcome": (
            "👋 **سلام! به ربات دانلودر خوش آمدید.**\n\n"
            "کافیست لینک ویدیو یا موزیک مورد نظر خود را ارسال کنید تا با کیفیت عالی دریافت کنید.\n\n"
            "🌐 **پلتفرم‌های پشتیبانی شده:**\n"
            "• 🔴 **یوتیوب** (YouTube & Shorts)\n"
            "• 🟣 **اینستاگرام** (Reels & Posts)\n"
            "• ⚫ **تیک‌تاک** (TikTok)\n"
            "• 🔵 **توییتر / X**\n"
            "• 🟠 **ساندکلاد** (SoundCloud)\n"
            "• 🎵 **یوتیوب موزیک** (YouTube Music)\n\n"
            "⚙️ برای تنظیم زبان می‌توانید از دستور /settings یا دکمه زیر استفاده کنید."
        ),
        "settings_btn": "⚙️ تنظیمات | Settings",
        "settings_title": "⚙️ **تنظیمات ربات**\n\nزبان مورد نظر خود را انتخاب کنید:",
        "lang_fa": "🇮🇷 فارسی (فعال)",
        "lang_en": "🇬🇧 English",
        "lang_changed": "✅ زبان برنامه با موفقیت به فارسی تغییر کرد.",
        "back_btn": "🔙 بستن / بازگشت",
        "invalid_link": "⚠️ لطفاً یک لینک معتبر اینترنتی ارسال کنید (شروع با http یا https).",
        "analyzing": "🔍 در حال بررسی لینک و استخراج کیفیت‌های موجود...",
        "select_quality": "🎬 کیفیت مورد نظر برای دانلود را انتخاب کنید:",
        "select_audio_quality": "🎶 کیفیت مورد نظر برای دانلود صوت را انتخاب کنید:",
        "audio_mp3_btn": "🎵 دانلود صوت (MP3)",
        "audio_320_btn": "🎵 کیفیت عالی (320kbps)",
        "audio_192_btn": "🎵 کیفیت استاندارد (192kbps)",
        "audio_128_btn": "🎵 حجم کم (128kbps)",
        "audio_orig_btn": "🎼 کیفیت اورجینال",
        "video_best_btn": "🎬 بالاترین کیفیت موجود",
        "downloading": "⏳ **در حال دانلود و پردازش فایل...**\nلطفاً تا اتمام ارسال صبور باشید.",
        "in_queue": "🚀 درخواست شما در صف پردازش قرار گرفت...",
        "already_downloading": "⏳ این فایل در حال حاضر در حال دانلود است. لطفاً شکیبا باشید.",
        "expired_link": "⚠️ این لینک منقضی شده است. لطفاً مجدداً لینک را ارسال کنید.",
        "file_too_large": (
            "⚠️ **حجم فایل ({size_mb:.1f} مگابایت) بیشتر از سقف مجاز تلگرام ({limit_mb} مگابایت) است.**\n\n"
            "📌 نام فایل: `{title}`\n"
            "💡 لطفاً کیفیت پایین‌تر یا فرمت صوتی را انتخاب کنید."
        ),
        "file_not_found": "❌ فایل نهایی یافت نشد.",
        "process_complete": "✅ پروسه دانلود و ارسال به پایان رسید.",
        "tweet_unavailable": "❌ این توییت در توییتر وجود ندارد، حذف شده یا اکانت آن خصوصی (Private) است.",
        "youtube_bot_detected": "⚠️ یوتیوب درخواست ربات را محدود کرد. لطفاً فایل کوکی معتبر را در cookies.txt قرار دهید.",
        "private_content": "❌ این محتوا خصوصی است و امکان دسترسی بدون دسترسی به آن وجود ندارد.",
        "network_timeout": "⚠️ ارتباط شبکه با سرور مقصد قطع شد یا به دلیل کندی اینترنت تایم‌اوت داد. لطفاً مجدداً تلاش کنید.",
        "download_error": "❌ خطا در دانلود: {error}",
        "playlist_title": (
            "📋 **اطلاعات آلبوم / پلی‌لیست**\n\n"
            "📌 **عنوان:** {title}\n"
            "👤 **سازنده:** {uploader}\n"
            "🔢 **تعداد کل ترک‌ها:** {total_tracks}\n"
        ),
        "playlist_limit_notice": "⚠️ *توجه: حداکثر {limit} ترک اول دانلود خواهند شد.*"
    },
    "en": {
        "welcome": (
            "👋 **Hello! Welcome to Downloader Bot.**\n\n"
            "Send any video or music link to download it in top quality.\n\n"
            "🌐 **Supported Platforms:**\n"
            "• 🔴 **YouTube** (Videos & Shorts)\n"
            "• 🟣 **Instagram** (Reels & Posts)\n"
            "• ⚫ **TikTok**\n"
            "• 🔵 **Twitter / X**\n"
            "• 🟠 **SoundCloud**\n"
            "• 🎵 **YouTube Music**\n\n"
            "⚙️ Use /settings or the button below to change the language."
        ),
        "settings_btn": "⚙️ Settings",
        "settings_title": "⚙️ **Bot Settings**\n\nChoose your preferred language:",
        "lang_fa": "🇮🇷 فارسی",
        "lang_en": "🇬🇧 English (Active)",
        "lang_changed": "✅ Language successfully switched to English.",
        "back_btn": "🔙 Close / Back",
        "invalid_link": "⚠️ Please send a valid web link (starting with http or https).",
        "analyzing": "🔍 Analyzing link and checking available resolutions...",
        "select_quality": "🎬 Select your desired video quality:",
        "select_audio_quality": "🎶 Select your desired audio quality:",
        "audio_mp3_btn": "🎵 Download as Audio (MP3)",
        "audio_320_btn": "🎵 Ultra Quality (320kbps)",
        "audio_192_btn": "🎵 Standard Quality (192kbps)",
        "audio_128_btn": "🎵 Compact Size (128kbps)",
        "audio_orig_btn": "🎼 Original Format",
        "video_best_btn": "🎬 Best Available Quality",
        "downloading": "⏳ **Downloading and processing file...**\nPlease wait until delivery finishes.",
        "in_queue": "🚀 Your request is queued for processing...",
        "already_downloading": "⏳ This download is already in progress. Please wait.",
        "expired_link": "⚠️ This link has expired. Please send the link again.",
        "file_too_large": (
            "⚠️ **File size ({size_mb:.1f} MB) exceeds Telegram's limit ({limit_mb} MB).**\n\n"
            "📌 Title: `{title}`\n"
            "💡 Please choose a lower resolution or audio mode."
        ),
        "file_not_found": "❌ Final downloaded file was not found.",
        "process_complete": "✅ Download and delivery complete.",
        "tweet_unavailable": "❌ This tweet is unavailable, deleted, or from a private account.",
        "youtube_bot_detected": "⚠️ YouTube restricted this request. Please add valid cookies in cookies.txt.",
        "private_content": "❌ This post or video is private and cannot be downloaded.",
        "network_timeout": "⚠️ Connection timed out due to network latency. Please try again.",
        "download_error": "❌ Download error: {error}",
        "playlist_title": (
            "📋 **Album / Playlist Info**\n\n"
            "📌 **Title:** {title}\n"
            "👤 **Creator:** {uploader}\n"
            "🔢 **Total tracks:** {total_tracks}\n"
        ),
        "playlist_limit_notice": "⚠️ *Note: Only the first {limit} tracks will be downloaded.*"
    }
}

def get_text(lang, key):
    return STRINGS.get(lang, STRINGS["fa"]).get(key, STRINGS["fa"].get(key, ""))

def format_error_message(err_str: str, lang: str) -> str:
    err_lower = str(err_str).lower()
    if "bounced" in err_lower or "requested tweet is unavailable" in err_lower:
        return get_text(lang, "tweet_unavailable")
    if "sign in to confirm you’re not a bot" in err_lower or "sign in to confirm you're not a bot" in err_lower:
        return get_text(lang, "youtube_bot_detected")
    if "private" in err_lower:
        return get_text(lang, "private_content")
    if "timeout" in err_lower or "timed out" in err_lower or "connection aborted" in err_lower:
        return get_text(lang, "network_timeout")
    return get_text(lang, "download_error").format(error=str(err_str)[:150])


# ----------------------------------------------------
# URL and Content Classification
# ----------------------------------------------------
def classify_url(url: str):
    clean_url = url.lower().strip()
    parsed = urlparse(clean_url)
    domain = parsed.netloc

    if "soundcloud.com" in domain:
        return "soundcloud", True
    if "music.youtube.com" in domain:
        return "yt_music", True
    if any(clean_url.endswith(ext) for ext in [".mp3", ".wav", ".flac", ".ogg", ".m4a"]):
        return "direct_audio", True

    if "instagram.com" in domain:
        return "instagram", False
    if "tiktok.com" in domain:
        return "tiktok", False
    if "youtube.com" in domain or "youtu.be" in domain:
        return "youtube", False
    if "twitter.com" in domain or "x.com" in domain:
        return "twitter", False
    if "pinterest.com" in domain or "pin.it" in domain:
        return "pinterest", False

    return "general", False


def cleanup_old_user_data():
    now = time.time()
    with user_data_lock:
        keys_to_del = [k for k, v in user_data.items() if now - v.get('timestamp', now) > 7200]
        for k in keys_to_del:
            del user_data[k]


# ----------------------------------------------------
# Telegram Bot Handlers
# ----------------------------------------------------
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    lang = get_user_lang(message.chat.id)
    logger.info(f"Command /start received from chat_id={message.chat.id} (lang={lang})")
    markup = types.InlineKeyboardMarkup()
    btn_settings = types.InlineKeyboardButton(get_text(lang, "settings_btn"), callback_data="menu:settings")
    markup.add(btn_settings)

    bot.reply_to(message, get_text(lang, "welcome"), reply_markup=markup, parse_mode="Markdown")


@bot.message_handler(commands=['settings', 'language'])
def send_settings(message):
    lang = get_user_lang(message.chat.id)
    logger.info(f"Command /settings received from chat_id={message.chat.id}")
    show_settings_menu(message.chat.id, None, lang)


def show_settings_menu(chat_id, message_id=None, lang="fa"):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_fa = types.InlineKeyboardButton(get_text(lang, "lang_fa"), callback_data="set_lang:fa")
    btn_en = types.InlineKeyboardButton(get_text(lang, "lang_en"), callback_data="set_lang:en")
    btn_close = types.InlineKeyboardButton(get_text(lang, "back_btn"), callback_data="menu:close")
    markup.add(btn_fa, btn_en)
    markup.add(btn_close)

    text = get_text(lang, "settings_title")
    if message_id:
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="Markdown")
            return
        except Exception:
            pass
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    cleanup_old_user_data()
    chat_id = message.chat.id
    lang = get_user_lang(chat_id)
    url = message.text.strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        bot.reply_to(message, get_text(lang, "invalid_link"))
        return

    logger.info(f"Received URL from chat_id={chat_id}: {url}")

    status_msg = bot.reply_to(message, get_text(lang, "analyzing"))
    analysis_executor.submit(analyze_and_show_options, chat_id, message.message_id, status_msg.message_id, url, lang)


# ----------------------------------------------------
# Dynamic Quality Extraction & Prompt Builder
# ----------------------------------------------------
def analyze_and_show_options(chat_id, original_msg_id, status_msg_id, url, lang):
    platform, is_audio_only = classify_url(url)

    # Fast check for playlist
    if any(k in url.lower() for k in ["playlist", "list=", "album", "sets/"]):
        send_playlist_info(chat_id, url, lang)

    # Lightweight metadata check to find actually available resolutions
    ydl_opts = {
        'extract_flat': False,
        'skip_download': True,
        'ignoreerrors': False,
        'socket_timeout': 30,
        'retries': 5,
    }
    configure_ydl_base_options(ydl_opts, platform)

    info = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        logger.warning(f"Error during metadata extraction for {url}: {e}")
        err_msg = format_error_message(str(e), lang)
        try:
            bot.edit_message_text(err_msg, chat_id=chat_id, message_id=status_msg_id, parse_mode="Markdown")
        except Exception:
            pass
        return

    if not info:
        try:
            bot.edit_message_text(get_text(lang, "file_not_found"), chat_id=chat_id, message_id=status_msg_id)
        except Exception:
            pass
        return

    # Extract available video heights
    available_heights = set()
    formats = info.get('formats') or []
    for f in formats:
        h = f.get('height')
        vcodec = f.get('vcodec')
        if h and vcodec != 'none':
            available_heights.add(h)

    # If first item in playlist
    if not available_heights and info.get('entries'):
        first_entry = next((e for e in info['entries'] if e), None)
        if first_entry:
            for f in first_entry.get('formats', []):
                h = f.get('height')
                vcodec = f.get('vcodec')
                if h and vcodec != 'none':
                    available_heights.add(h)

    # Save to user_data for callback retrieval
    with user_data_lock:
        user_data[(chat_id, original_msg_id)] = {
            'url': url,
            'title': info.get('title', 'Media'),
            'platform': platform,
            'is_audio_only': is_audio_only,
            'timestamp': time.time()
        }

    markup = types.InlineKeyboardMarkup(row_width=2)

    # 1. Audio Platforms (SoundCloud / YouTube Music)
    if is_audio_only:
        btn_320 = types.InlineKeyboardButton(get_text(lang, "audio_320_btn"), callback_data="dl:audio_320")
        btn_192 = types.InlineKeyboardButton(get_text(lang, "audio_192_btn"), callback_data="dl:audio_192")
        btn_128 = types.InlineKeyboardButton(get_text(lang, "audio_128_btn"), callback_data="dl:audio_128")
        btn_orig = types.InlineKeyboardButton(get_text(lang, "audio_orig_btn"), callback_data="dl:audio_orig")
        markup.add(btn_320, btn_192)
        markup.add(btn_128, btn_orig)
        caption = get_text(lang, "select_audio_quality")

    # 2. Video Platforms (YouTube, TikTok, Instagram, Twitter, etc.)
    else:
        # Standard resolutions list to check against available heights
        standard_qualities = [
            (2160, "4K (2160p)", "quality_2160", lambda heights: any(h >= 2160 for h in heights)),
            (1440, "2K (1440p)", "quality_1440", lambda heights: any(1440 <= h < 2160 for h in heights)),
            (1080, "1080p (FHD)", "quality_1080", lambda heights: any(1080 <= h < 1440 for h in heights)),
            (720,  "720p (HD)",   "quality_720",  lambda heights: any(720 <= h < 1080 for h in heights)),
            (480,  "480p",        "quality_480",  lambda heights: any(480 <= h < 720 for h in heights)),
            (360,  "360p",        "quality_360",  lambda heights: any(360 <= h < 480 for h in heights)),
            (240,  "240p",        "quality_240",  lambda heights: any(240 <= h < 360 for h in heights)),
            (144,  "144p",        "quality_144",  lambda heights: any(0 < h < 240 for h in heights)),
        ]

        active_video_buttons = []
        if available_heights:
            for height_val, label, code, check_fn in standard_qualities:
                if check_fn(available_heights):
                    active_video_buttons.append(types.InlineKeyboardButton(f"🎥 {label}", callback_data=f"dl:{code}"))

        # Fallback if specific heights could not be determined
        if not active_video_buttons:
            active_video_buttons.append(types.InlineKeyboardButton(get_text(lang, "video_best_btn"), callback_data="dl:video_best"))

        # Add video buttons in pairs
        for i in range(0, len(active_video_buttons), 2):
            markup.row(*active_video_buttons[i:i+2])

        # ALWAYS add Audio extraction option for any video as requested!
        btn_audio = types.InlineKeyboardButton(get_text(lang, "audio_mp3_btn"), callback_data="dl:audio_mp3")
        markup.add(btn_audio)

        caption = f"🎬 **{info.get('title', 'Video')}**\n\n{get_text(lang, 'select_quality')}"

    try:
        bot.edit_message_text(
            caption[:1024],
            chat_id=chat_id,
            message_id=status_msg_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to edit prompt message for chat_id={chat_id}: {e}")


def send_playlist_info(chat_id, url, lang):
    platform, _ = classify_url(url)
    ydl_opts = {
        'extract_flat': True,
        'skip_download': True,
        'ignoreerrors': True,
        'socket_timeout': 20,
    }
    configure_ydl_base_options(ydl_opts, platform)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return
            title = info.get('title', 'Playlist')
            uploader = info.get('uploader', info.get('channel', 'Unknown'))
            entries = info.get('entries') or []
            total_tracks = len(entries) if entries else 1

            caption = get_text(lang, "playlist_title").format(
                title=title,
                uploader=uploader,
                total_tracks=total_tracks
            )
            if total_tracks > MAX_PLAYLIST_ITEMS:
                caption += "\n" + get_text(lang, "playlist_limit_notice").format(limit=MAX_PLAYLIST_ITEMS)

            thumb_url = info.get('thumbnail')
            if not thumb_url and entries:
                first = entries[0] if isinstance(entries, list) else None
                if isinstance(first, dict):
                    thumb_url = first.get('thumbnail')

            if thumb_url:
                try:
                    bot.send_photo(chat_id, photo=thumb_url, caption=caption, parse_mode="Markdown")
                    return
                except Exception:
                    pass
            bot.send_message(chat_id, caption, parse_mode="Markdown")
    except Exception as e:
        logger.debug(f"Playlist info extraction skipped: {e}")


# ----------------------------------------------------
# Download & Delivery Worker
# ----------------------------------------------------
def process_file_and_send(chat_id, task_temp_dir, entry, call_action, lang):
    is_audio = call_action.startswith("audio_")
    title = entry.get('title', 'Downloaded Media')
    uploader = entry.get('uploader') or entry.get('artist') or entry.get('creator') or 'Unknown'
    duration = int(entry.get('duration') or 0)
    entry_id = str(entry.get('id', ''))

    all_files = []
    for root, _, files in os.walk(task_temp_dir):
        for f in files:
            all_files.append(os.path.join(root, f))

    thumb_file = None
    for fpath in all_files:
        ext = os.path.splitext(fpath)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.webp'] and not thumb_file:
            thumb_file = fpath
            break

    media_file = None
    extra_cleanup = []

    if is_audio:
        audio_candidates = [
            f for f in all_files 
            if os.path.splitext(f)[1].lower() in ['.mp3', '.m4a', '.opus', '.ogg', '.wav', '.flac']
        ]
        matching = [f for f in audio_candidates if entry_id and entry_id in os.path.basename(f)]
        media_file = matching[0] if matching else (audio_candidates[0] if audio_candidates else None)
    else:
        video_candidates = []
        audio_streams = []

        for fpath in all_files:
            fname = os.path.basename(fpath).lower()
            ext = os.path.splitext(fname)[1]
            if ext in ['.mp4', '.mkv', '.webm', '.mov']:
                # Filter out pure audio streams like fhls-audio-0.mp4
                if any(k in fname for k in ['-audio-', 'fhls-audio', 'audio_only', '.audio.']):
                    audio_streams.append(fpath)
                else:
                    video_candidates.append(fpath)

        # Match entry_id if available
        matching_vids = [f for f in video_candidates if entry_id and entry_id in os.path.basename(f)]
        target_vid = matching_vids[0] if matching_vids else (video_candidates[0] if video_candidates else None)

        matching_auds = [f for f in audio_streams if entry_id and entry_id in os.path.basename(f)]
        target_aud = matching_auds[0] if matching_auds else (audio_streams[0] if audio_streams else None)

        # If both a video stream and an audio stream exist, merge them with FFmpeg
        if target_vid and target_aud and target_vid != target_aud:
            ffmpeg_bin = FFMPEG_PATH or shutil.which("ffmpeg") or "ffmpeg"
            merged_file = os.path.join(task_temp_dir, f"merged_{entry_id or 'vid'}.mp4")
            try:
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", target_vid,
                    "-i", target_aud,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    merged_file
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
                if res.returncode == 0 and os.path.exists(merged_file) and os.path.getsize(merged_file) > 1000:
                    media_file = merged_file
                    extra_cleanup.extend([target_vid, target_aud])
                    logger.info(f"FFmpeg successfully merged separated streams for {entry_id}")
                else:
                    media_file = target_vid
            except Exception as e:
                logger.warning(f"FFmpeg merge exception: {e}")
                media_file = target_vid
        else:
            media_file = target_vid

    if not media_file or not os.path.exists(media_file):
        logger.error(f"Final media file not found in {task_temp_dir} for {title}")
        bot.send_message(chat_id, get_text(lang, "file_not_found"))
        return

    file_size = os.path.getsize(media_file)
    logger.info(f"Sending file '{os.path.basename(media_file)}' ({file_size / (1024*1024):.2f} MB) to {chat_id}")

    if file_size > MAX_FILE_SIZE:
        size_mb = file_size / (1024 * 1024)
        limit_mb = int(MAX_FILE_SIZE / (1024 * 1024))
        logger.warning(f"File exceeds {limit_mb}MB limit: {size_mb:.2f} MB. Sending warning.")
        bot.send_message(
            chat_id,
            get_text(lang, "file_too_large").format(size_mb=size_mb, limit_mb=limit_mb, title=title),
            parse_mode="Markdown"
        )
        try:
            os.remove(media_file)
        except Exception:
            pass
        return

    thumb_handle = open(thumb_file, 'rb') if thumb_file and os.path.exists(thumb_file) else None
    try:
        with open(media_file, 'rb') as f_media:
            if is_audio:
                bot.send_audio(
                    chat_id,
                    f_media,
                    title=title,
                    performer=uploader,
                    duration=duration,
                    thumb=thumb_handle
                )
            else:
                bot.send_video(
                    chat_id,
                    f_media,
                    caption=f"🎬 **{title}**"[:1024],
                    duration=duration,
                    thumb=thumb_handle,
                    supports_streaming=True,
                    parse_mode="Markdown"
                )
        logger.info(f"Successfully uploaded {title} to chat_id={chat_id}")
    finally:
        if thumb_handle:
            thumb_handle.close()
        # Immediately delete sent file and its raw streams so next playlist entries don't re-send it
        try:
            if os.path.exists(media_file):
                os.remove(media_file)
            for ex in extra_cleanup:
                if os.path.exists(ex):
                    os.remove(ex)
        except Exception:
            pass


def download_task(call, url, original_msg_id, call_action, lang):
    chat_id = call.message.chat.id
    task_temp_dir = tempfile.mkdtemp(prefix=f"task_{chat_id}_{original_msg_id}_", dir=DOWNLOADS_ROOT)
    logger.info(f"Starting download task in temp dir: {task_temp_dir} for action: {call_action}")

    try:
        is_audio = call_action.startswith("audio_")
        platform = classify_url(url)[0]

        if is_audio:
            if call_action == "audio_320":
                bitrate = '320'
            elif call_action == "audio_128":
                bitrate = '128'
            else:
                bitrate = '192'

            ydl_opts = {
                'format': 'bestaudio/best',
                'writethumbnail': True,
                'ignoreerrors': True,
                'socket_timeout': 60,
                'retries': 10,
                'fragment_retries': 10,
                'outtmpl': os.path.join(task_temp_dir, '%(autonumber)s_%(id)s.%(ext)s'),
                'playlistend': MAX_PLAYLIST_ITEMS,
                'quiet': True,
                'no_warnings': True,
            }

            if call_action != "audio_orig":
                ydl_opts['postprocessors'] = [
                    {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': bitrate},
                    {'key': 'FFmpegMetadata'},
                ]
        else:
            # For Twitter, prefer progressive MP4 (audio+video already merged) to avoid broken HLS audio streams
            if platform == "twitter":
                if call_action.startswith("quality_"):
                    target_h = int(call_action.replace("quality_", ""))
                    fmt = (
                        f'best[height<={target_h}][ext=mp4]/'
                        f'bestvideo[height<={target_h}][ext=mp4]+bestaudio[ext=m4a]/'
                        f'bestvideo[height<={target_h}]+bestaudio/'
                        f'best[height<={target_h}]/best'
                    )
                else:
                    fmt = 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
            else:
                if call_action.startswith("quality_"):
                    target_h = int(call_action.replace("quality_", ""))
                    fmt = (
                        f'bestvideo[height<={target_h}][ext=mp4]+bestaudio[ext=m4a]/'
                        f'bestvideo[height<={target_h}]+bestaudio/'
                        f'best[height<={target_h}]/'
                        f'bv*[height<={target_h}]+ba/b[height<={target_h}]/'
                        f'bv*+ba/b'
                    )
                else:
                    fmt = (
                        'bestvideo[ext=mp4]+bestaudio[ext=m4a]/'
                        'bestvideo+bestaudio/'
                        'best/'
                        'bv*+ba/b'
                    )

            ydl_opts = {
                'format': fmt,
                'merge_output_format': 'mp4',
                'writethumbnail': True,
                'ignoreerrors': True,
                'socket_timeout': 60,
                'retries': 10,
                'fragment_retries': 10,
                'outtmpl': os.path.join(task_temp_dir, '%(autonumber)s_%(id)s.%(ext)s'),
                'playlistend': MAX_PLAYLIST_ITEMS,
                'quiet': True,
                'no_warnings': True,
            }

        # If a single video was requested (e.g. /video/1), do not download the entire tweet
        if "/video/" in url.lower():
            ydl_opts['noplaylist'] = True

        configure_ydl_base_options(ydl_opts, platform)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                bot.send_message(chat_id, get_text(lang, "file_not_found"))
                return

            entries = info.get('entries')
            if entries:
                for entry in entries:
                    if entry:
                        process_file_and_send(chat_id, task_temp_dir, entry, call_action, lang)
                        time.sleep(1)
            else:
                process_file_and_send(chat_id, task_temp_dir, info, call_action, lang)

        bot.send_message(chat_id, get_text(lang, "process_complete"))

    except Exception as e:
        logger.error(f"Download task failed for {url}: {e}")
        err_msg = format_error_message(str(e), lang)
        bot.send_message(chat_id, err_msg)

    finally:
        # 100% Guaranteed cleanup of all files and isolated folder
        try:
            shutil.rmtree(task_temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up temp directory: {task_temp_dir}")
        except Exception as e:
            logger.warning(f"Error removing {task_temp_dir}: {e}")

        with active_downloads_lock:
            active_downloads.discard((chat_id, original_msg_id))


# ----------------------------------------------------
# Inline Button Callbacks
# ----------------------------------------------------
@bot.callback_query_handler(func=lambda call: True)
def callback_router(call):
    chat_id = call.message.chat.id
    lang = get_user_lang(chat_id)
    data = call.data

    # 1. Settings menu interactions
    if data == "menu:settings":
        show_settings_menu(chat_id, call.message.message_id, lang)
        bot.answer_callback_query(call.id)
        return

    if data == "menu:close":
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
        bot.answer_callback_query(call.id)
        return

    if data.startswith("set_lang:"):
        new_lang = data.split(":")[1]
        set_user_lang(chat_id, new_lang)
        bot.answer_callback_query(call.id, get_text(new_lang, "lang_changed"), show_alert=True)
        show_settings_menu(chat_id, call.message.message_id, new_lang)
        return

    # 2. Download interactions (prefixed with 'dl:')
    if data.startswith("dl:"):
        call_action = data.split(":", 1)[1]
        original_message = call.message.reply_to_message
        if not original_message:
            bot.answer_callback_query(call.id, get_text(lang, "expired_link"), show_alert=True)
            return

        key = (chat_id, original_message.message_id)

        with user_data_lock:
            cached = user_data.get(key)

        if not cached:
            bot.answer_callback_query(call.id, get_text(lang, "expired_link"), show_alert=True)
            return

        url = cached['url']

        with active_downloads_lock:
            if key in active_downloads:
                bot.answer_callback_query(call.id, get_text(lang, "already_downloading"), show_alert=True)
                return
            active_downloads.add(key)

        bot.answer_callback_query(call.id, get_text(lang, "in_queue"))

        try:
            bot.edit_message_text(
                get_text(lang, "downloading"),
                chat_id=chat_id,
                message_id=call.message.message_id,
                parse_mode="Markdown"
            )
        except Exception:
            pass

        executor.submit(download_task, call, url, original_message.message_id, call_action, lang)


if __name__ == "__main__":
    logger.info("Bot started successfully and is listening for messages...")
    bot.infinity_polling(timeout=30, skip_pending=True)
