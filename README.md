[README.md](https://github.com/user-attachments/files/34202585/README.md)
# 🚀 Hosi Downloader Bot (ربات دانلودر همه‌کاره تلگرام)

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram_Bot-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)
![yt-dlp](https://img.shields.io/badge/yt--dlp-FF0000?style=for-the-badge&logo=youtube&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Deno](https://img.shields.io/badge/Deno-000000?style=for-the-badge&logo=deno&logoColor=white)

**یک ربات تلگرام حرفه‌ای، سریع و ماژولار برای دانلود مدیا از پلتفرم‌های مختلف با قابلیت آپلود فایل‌های حجیم تا ۲ گیگابایت**

[ویژگی‌ها](#-ویژگی‌های-کلیدی) •
[پلتفرم‌های پشتیبانی‌شده](#-پلتفرم‌های-پشتیبانی‌شده) •
[نصب و راه‌اندازی سریع](#-نصب-و-راه‌اندازی-سریع-one-click-setup) •
[متغیرهای محیطی](#-متغیرهای-محیطی-env) •
[معماری و ساختار](#-معماری-و-ساختار-پروژه)

---

</div>

## 🌟 ویژگی‌های کلیدی

- ⚡ **آپلود تا سقف ۲ گیگابایت (2000 MB):** اتصال خودکار به سرور محلی تلگرام (`Local Telegram Bot API`) جهت دور زدن محدودیت ۵۰ مگابایتی تلگرام.
- 🎯 **انتخاب کیفیت هوشمند:** استخراج کیفیت‌های موجود (از 144p تا 4K) و امکان انتخاب استخراج فقط فایل صوتی (MP3).
- 🧩 **حل چالش‌های جاوااسکریپت یوتیوب:** مجهز به موتور جاوااسکریپت Deno و افزونه `yt-dlp-ejs` جهت حل چالش‌های امضای دیجیتال و `n-sig` یوتیوب بدون بلاک شدن.
- 🎬 **پشتیبانی کامل از استریم‌های HLS توییتر/X:** ادغام خودکار ویدیو و صدای باکیفیت بدون مشکل تکه‌تکه شدن صدا.
- 🌐 **رابط کاربری دوزبانه (فارسی و انگلیسی):** امکان سوییچ سریع زبان توسط کاربر با ذخیره پایدار تنظیمات.
- 🧹 **پاک‌سازی ۱۰۰٪ خودکار حافظه موقت:** ایجاد دایرکتوری‌های مجزا برای هر تسک و حذف کامل پس از ارسال برای جلوگیری از پر شدن حافظه هارد دیسک.
- 🛡️ **پایداری ۲۴/۷ سرور:** مجهز به سرویس Systemd و تنظیمات اختصاصی Swap جهت جلوگیری از خطای کمبود حافظه (Out-Of-Memory) روی سرورهای ۱ گیگابایت رم.

---

## 📺 پلتفرم‌های پشتیبانی‌شده

| پلتفرم | قابلیت‌ها | فرمت‌های خروجی |
| :--- | :--- | :--- |
| **YouTube** | ویدیوهای عادی، Shorts، استخراج صوت | 144p تا 4K (MP4) + صوتی (MP3) |
| **Twitter / X** | ویدیوها، گیف‌ها، پست‌های حساس با کوکی | MP4 ادغام‌شده کامل |
| **Instagram** | ریلز، پست‌های ویدیویی، IGTV | کیفیت اصلی MP4 |
| **TikTok** | ویدیوهای تیک‌تاک بدون واترمارک | کیفیت اصلی MP4 |
| **SoundCloud & YT Music** | دانلود موزیک و آهنگ‌های باکیفیت | فایل صوتی با بیت‌ریت بالا |

---

## 🚀 نصب و راه‌اندازی سریع (One-Click Setup)

روی هر سرور اوبونتو خام (Ubuntu 22.04 / 24.04)، می‌توانید کل سرویس‌ها (Docker, Local Bot API, Deno, Swap, Python Venv, Systemd) را با یک اسکریپت ظرف ۳ دقیقه راه‌اندازی کنید:

```bash
# ۱. کلون کردن ریپازیتوری
git clone https://github.com/Shokrgozar06/Hosi-Downloader-Bot-Version.git
cd Hosi-Downloader-Bot-Version

# ۲. ایجاد فایل تنظیمات محیطی (.env)
cp .env.example .env
nano .env  # توکن ربات تلگرام خود را وارد کنید

# ۳. اعطای دسترسی و اجرای اسکریپت نصب
chmod +x setup.sh
./setup.sh
```

اسکریپت `setup.sh` به صورت خودکار:
1. پکیج‌های پیش‌نیاز (`docker.io`, `ffmpeg`, `nodejs`, `npm`, `python3-venv`) را نصب می‌کند.
2. برای جلوگیری از خطای رم، ۴ گیگابایت **Swap** پایدار می‌سازد.
3. محیط ران‌تایم **Deno** را با `npm` نصب می‌کند.
4. کانتینر داکر **Local Telegram Bot API** را روی پورت `8081` اجرا می‌کند.
5. محیط مجازی پایتون را ساخته و پکیج‌های `requirements.txt` را نصب می‌نماید.
6. بات را در قالب سرویس **Systemd (`hosi-bot.service`)** پایدار می‌کند تا ۲۴ ساعته فعال باشد.

---

## ⚙️ متغیرهای محیطی (.env)

فایل `.env` را در پوشه اصلی ایجاد کرده و مقادیر زیر را تنظیم کنید:

```env
# توکن دریافتی از BotFather
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# آدرس سرور محلی تلگرام (اختیاری - پیش‌فرض http://localhost:8081)
LOCAL_BOT_API_URL=http://localhost:8081

# مشخص کردن کوکی مرورگر در صورت نیاز (اختیاری: chrome, firefox, edge)
BROWSER_COOKIES=
```

---

## 🍪 راهنمای استفاده از کوکی‌ها (Cookies)

برای دانلود ویدیوهای محدودشده به سن یوتیوب یا توییت‌های خصوصی/حساس توییتر:
1. افزونه **Get cookies.txt LOCALLY** را روی مرورگر خود نصب کنید.
2. وارد اکانت یوتیوب یا توییتر شوید و خروجی کوکی با فرمت Netscape را اکسپورت بگیرید.
3. فایل را در پوشه ربات ذخیره کنید:
   - برای یوتیوب: با نام `cookies.txt`
   - برای توییتر: با نام `cookies_twitter.txt`

---

## 🛠️ دستورات مدیریت سرویس روی سرور

پس از نصب با `setup.sh`، می‌توانید با دستورات زیر وضعیت ربات را مدیریت کنید:

```bash
# مشاهده لاگ‌های زنده ربات
sudo journalctl -u hosi-bot -f

# ریستارت کردن ربات
sudo systemctl restart hosi-bot

# متوقف کردن ربات
sudo systemctl stop hosi-bot

# بررسی وضعیت کانتینر تلگرام
docker ps -a
docker logs -f telegram-bot-api
```

---

## 📂 معماری و ساختار پروژه

```text
Hosi-Downloader-Bot-Version/
├── downloader.py          # هسته اصلی ربات، مدیریت دانلود و هندلرها
├── setup.sh               # اسکریپت نصب خودکار یک‌کلیکه برای لینوکس
├── requirements.txt       # کتابخانه‌های پایتونی مورد نیاز
├── .env.example           # نمونه فایل تنظیمات محیطی
├── .gitignore             # نادیده گرفتن فایل‌های موقت، کش و سشن‌ها
├── README/
│   └── README.md          # مستندات کامل پروژه
└── downloads/             # پوشه خودکار دانلودهای موقت (پاک‌سازی خودکار)
```

---

## 👨‍💻 نویسنده و توسعه‌دهنده

- **Hossein Shokrgozar** - [GitHub Profile](https://github.com/Shokrgozar06)

---

<div align="center">
ساخته‌شده با ❤️ برای دسترسی آزاد به محتوا و سهولت در دانلود مدیا
</div>
