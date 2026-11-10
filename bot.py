import asyncio
import logging
import os
import sys
import sqlite3
import re
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

# إعداد الـ Logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout
)

TOKEN = os.getenv("TOKEN", "6485657013:AAE6oSf5STLnQqcTR1IqvFBaVcvEzzKfgV8")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5166153612"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@YourChannelUsername")

bot = Bot(token=TOKEN)
dp = Dispatcher()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# دالة مساعدة متطورة جداً لربط الكوكيز وتخطي حماية إنستجرام والتليجرام
def get_ydl_opts(base_opts: dict) -> dict:
    if os.path.exists("cookies.txt"):
        base_opts['cookiefile'] = "cookies.txt"
    
    # إعدادات متطورة جداً لتجاوز حظر الـ IP وحماية إنستجرام عبر محاكاة متصفح موبايل
    base_opts.update({
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'referer': 'https://www.instagram.com/',
        'http_headers': {
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Site': 'same-origin',
        }
    })
    return base_opts

# --- قاعدة بيانات مبسطة للمشاركات فقط ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            referrals_count INTEGER DEFAULT 0,
            referred_by INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            url TEXT,
            title TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_user(user_id, username, full_name, referrer_id=None):
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone()
        if not exists:
            ref = referrer_id if referrer_id and referrer_id != user_id else None
            cursor.execute('INSERT INTO users (user_id, username, full_name, referrals_count, referred_by) VALUES (?, ?, ?, 0, ?)', 
                           (user_id, username, full_name, ref))
            if ref:
                cursor.execute('UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?', (ref,))
            conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"DB Error: {e}")

def add_history(user_id, url, title):
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO history (user_id, url, title) VALUES (?, ?, ?)', (user_id, url, title))
        conn.commit()
        conn.close()
    except Exception:
        pass

init_db()

async def check_subscription(user_id: int) -> bool:
    if not CHANNEL_USERNAME or CHANNEL_USERNAME == "@YourChannelUsername":
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception:
        pass
    return False

# --- أوامر البوت (اختيار اللغات أولاً) ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    args = message.text.split()
    referrer_id = int(args[1].replace("REF", "")) if len(args) > 1 and args[1].startswith("REF") else None
    
    add_user(user.id, user.username, user.full_name, referrer_id)

    if CHANNEL_USERNAME and CHANNEL_USERNAME != "@YourChannelUsername":
        if not await check_subscription(user.id):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
                [InlineKeyboardButton(text="✅ تحقق من الاشتراك", callback_data="check_sub")]
            ])
            return await message.answer("⚠️ **يجب عليك الاشتراك في قناة البوت أولاً!**\nاشترك ثم اضغط تحقق 👇", reply_markup=keyboard)

    # أزرار اختيار اللغة
    lang_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇪🇬 العربية", callback_data="lang_ar"),
            InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")
        ]
    ])
    
    await message.answer(
        "👋 **Welcome / أهلاً بك**\n\n"
        "الرجاء اختيار اللغة المفضلة لديك:\n"
        "Please choose your preferred language:",
        reply_markup=lang_keyboard
    )

@dp.callback_query(F.data == "check_sub")
async def callback_check_sub(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        lang_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇪🇬 العربية", callback_data="lang_ar"), InlineKeyboardButton(text="🇺🇸 English", callback_data="lang_en")]
        ])
        await callback.message.answer("✅ **شكراً لاشتراكك!**\nاختر لغتك المفضلة / Choose your language:", reply_markup=lang_keyboard)
    else:
        await callback.answer("❌ لم تقم بالاشتراك في القناة بعد!", show_alert=True)

# --- معالجة اختيار اللغة العربية ---
@dp.callback_query(F.data == "lang_ar")
async def set_lang_ar(callback: types.CallbackQuery):
    user = callback.from_user
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=REF{user.id}"
    
    welcome_ar = (
        f"أهلاً بك يا **{user.first_name}** في بوت التحميل الشامل 🚀👑\n\n"
        "✨ **مميزات البوت:**\n"
        "• تحميل الفيديوهات والريلز بجودات عالية جداً.\n"
        "• دعم منصات متعددة (إنستجرام، تيك توك، يوتيوب، فيسبوك وغيرها).\n"
        "• تحميل ستوري وحسابات إنستجرام بسهولة تامة.\n\n"
        f"🔗 **رابط مشاركتك لدعوة الأصدقاء:**\n`{ref_link}`\n\n"
        "📥 **فقط أرسل أي رابط وسأقوم بتحميله لك فوراً!**"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 سجل تحميلاتي السابقة", callback_data="show_history")]
    ])
    
    await callback.message.edit_text(welcome_ar, parse_mode="Markdown", reply_markup=keyboard)

# --- معالجة اختيار اللغة الإنجليزية ---
@dp.callback_query(F.data == "lang_en")
async def set_lang_en(callback: types.CallbackQuery):
    user = callback.from_user
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=REF{user.id}"
    
    welcome_en = (
        f"Welcome **{user.first_name}** to the Ultimate Media Downloader Bot 🚀👑\n\n"
        "✨ **Bot Features:**\n"
        "• Download videos & reels in high quality.\n"
        "• Support multiple platforms (Instagram, TikTok, YouTube, Facebook, etc.).\n"
        "• Easily download Instagram stories and profiles.\n\n"
        f"🔗 **Your referral link to invite friends:**\n`{ref_link}`\n\n"
        "📥 **Just send any link and I will download it for you instantly!**"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Download History", callback_data="show_history")]
    ])
    
    await callback.message.edit_text(welcome_en, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data == "show_history")
async def callback_show_history(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT title, url FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 5', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return await callback.answer("📭 ليس لديك سجل تحميلات سابقة / No download history.", show_alert=True)
        
        text = "📜 **آخر روابط تم تحميلها / Recent downloads:**\n\n"
        for idx, (title, url) in enumerate(rows, 1):
            text += f"{idx}. [{title[:40]}...]({url})\n"
        
        await callback.message.answer(text, parse_mode="Markdown", disable_web_page_preview=True)
        await callback.answer()
    except Exception:
        await callback.answer("❌ حدث خطأ / Error occurred.", show_alert=True)

# --- معالجة الروابط مباشرة وتطبيق إعدادات الكوكيز ---
@dp.message(F.text.regexp(r'https?://\S+'))
async def handle_media_url(message: types.Message):
    user_id = message.from_user.id

    if CHANNEL_USERNAME and CHANNEL_USERNAME != "@YourChannelUsername":
        if not await check_subscription(user_id):
            return await message.answer("⚠️ يجب عليك الاشتراك في القناة أولاً! اضغط `/start`.")

    url_match = re.search(r'https?://\S+', message.text)
    if not url_match:
        return await message.answer("❌ لم أتمكن من العثور على رابط صحيح.")
    
    url = url_match.group(0)
    process_msg = await message.answer("⏳ **جاري تحليل الرابط والتحميل الفوري عبر المتصفح...**", parse_mode="Markdown")

    try:
        loop = asyncio.get_running_loop()
        
        # دمج خيارات الـ yt-dlp مع الكوكيز وتخطي الحظر
        ydl_opts = get_ydl_opts({
            'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
            'format': 'best/bestvideo+bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True
        })

        def download_media():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                return info, filename

        info, filename = await loop.run_in_executor(None, download_media)
        title = info.get('title', 'محتوى بدون عنوان')
        add_history(user_id, url, title)

        if filename and os.path.exists(filename):
            file_size = os.path.getsize(filename) / (1024 * 1024)
            if file_size > 50:
                await process_msg.edit_text("⚠️ عذراً، حجم الملف أكبر من الحد المسموح لتليجرام (50 ميجابايت).")
                os.remove(filename)
                return

            input_file = types.FSInputFile(filename)
            if filename.endswith(('.mp4', '.mkv', '.webm', '.mov')):
                await message.answer_video(video=input_file, caption=f"✅ **{title[:80]}**", parse_mode="Markdown")
            elif filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                await message.answer_photo(photo=input_file, caption=f"✅ **{title[:80]}**", parse_mode="Markdown")
            else:
                await message.answer_document(document=input_file, caption=f"✅ **{title[:80]}**", parse_mode="Markdown")
            
            await process_msg.delete()
            try:
                os.remove(filename)
            except:
                pass
        else:
            await process_msg.edit_text("❌ لم يتم العثور على الملف المحمل.")

    except Exception as e:
        logging.error(f"Download Error: {e}")
        await process_msg.edit_text("❌ عذراً، حدث خطأ أثناء التحميل. تأكد من صحة الرابط أو أن الحساب عام (Public).")

@dp.message(F.text)
async def handle_other_text(message: types.Message):
    await message.answer("💡 أهلاً بك! أرسل رابط الفيديو مباشرة للتحميل الفوري 🚀\nWelcome! Send a video link directly to download.")

async def main():
    logging.info("🚀 البوت يعمل الآن بكامل طاقته وتجاوز حماية إنستجرام...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    asyncio.run(main())
