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

# التوكن الذي أرسلته
TOKEN = "6485657013:AAE6oSf5STLnQqcTR1IqvFBaVcvEzzKfgV8"
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@YourChannelUsername")

bot = Bot(token=TOKEN)
dp = Dispatcher()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

ACTIVE_USERS = set()      
URL_CACHE = {}            

# --- قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            points INTEGER DEFAULT 10,
            referred_by INTEGER,
            is_banned INTEGER DEFAULT 0
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
            cursor.execute('INSERT INTO users (user_id, username, full_name, points, referred_by, is_banned) VALUES (?, ?, ?, 10, ?, 0)', 
                           (user_id, username, full_name, ref))
            if ref:
                cursor.execute('UPDATE users SET points = points + 5 WHERE user_id = ?', (ref,))
            conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"DB Error: {e}")

def get_user_data(user_id):
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT points, is_banned FROM users WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        conn.close()
        return res if res else (0, 0)
    except Exception:
        return (0, 0)

def add_history(user_id, url, title):
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO history (user_id, url, title) VALUES (?, ?, ?)', (user_id, url, title))
        conn.commit()
        conn.close()
    except Exception:
        pass

def toggle_ban_user(user_id, status):
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_banned = ? WHERE user_id = ?', (status, user_id))
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_all_users():
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE is_banned = 0')
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    except Exception:
        return []

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

# --- أوامر البوت ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    args = message.text.split()
    referrer_id = int(args[1].replace("REF", "")) if len(args) > 1 and args[1].startswith("REF") else None
    
    points, is_banned = get_user_data(user.id)
    if is_banned:
        return await message.answer("❌ عذراً، تم حظرك من استخدام البوت.")

    add_user(user.id, user.username, user.full_name, referrer_id)
    points, _ = get_user_data(user.id)

    if CHANNEL_USERNAME and CHANNEL_USERNAME != "@YourChannelUsername":
        if not await check_subscription(user.id):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
                [InlineKeyboardButton(text="✅ تحقق من الاشتراك", callback_data="check_sub")]
            ])
            return await message.answer("⚠️ **يجب عليك الاشتراك في قناة البوت أولاً!**\nاشترك ثم اضغط تحقق 👇", reply_markup=keyboard)

    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=REF{user.id}"
    
    welcome_text = (
        f"أهلاً بك يا **{user.first_name}** في المنظومة الرقمية الشاملة! 👑🚀\n\n"
        f"💎 رصيدك: **{points} نقطة**\n"
        f"🔗 رابط دعوة الأصدقاء:\n`{ref_link}`\n\n"
        "✨ **ما يمكنك إرساله الآن:**\n"
        "• رابط **فيديو فردي أو ريلز أو بوست** (يوتيوب، تيك توك، إنستجرام، فيسبوك...)\n"
        "• رابط **حساب إنستجرام شخصي** لتحميل الستوري، الهايلات، أو المنشورات بمرونة كاملة!"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 سجل تحميلاتي", callback_data="show_history")],
        [InlineKeyboardButton(text="🎁 هدية النقاط اليومية", callback_data="daily_bonus")]
    ])
    
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data == "check_sub")
async def callback_check_sub(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("✅ **شكراً لاشتراكك!** أرسل رابطك الآن 🎯", parse_mode="Markdown")
    else:
        await callback.answer("❌ لم تقم بالاشتراك في القناة بعد!", show_alert=True)

@dp.callback_query(F.data == "daily_bonus")
async def callback_daily_bonus(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET points = points + 3 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        await callback.answer("🎉 مبروك! حصلت على هدية 3 نقاط.", show_alert=True)
    except Exception:
        await callback.answer("❌ حدث خطأ.", show_alert=True)

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
            return await callback.answer("📭 ليس لديك سجل تحميلات سابقة.", show_alert=True)
        
        text = "📜 **آخر 5 روابط تم تحميلها:**\n\n"
        for idx, (title, url) in enumerate(rows, 1):
            text += f"{idx}. [{title[:40]}...]({url})\n"
        
        await callback.message.answer(text, parse_mode="Markdown", disable_web_page_preview=True)
        await callback.answer()
    except Exception:
        await callback.answer("❌ تعذر جلب السجل.", show_alert=True)

# --- لوحة تحكم المطور ---
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if ADMIN_ID and message.from_user.id != ADMIN_ID:
        return
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        total = cursor.fetchone()[0]
        conn.close()
        await message.answer(f"🎛️ **لوحة التحكم:**\n👥 المشتركون: `{total}`", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"خطأ: {e}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if ADMIN_ID and message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("⚠️ اكتب النص بعد الأمر.")
    users = get_all_users()
    status = await message.answer(f"⏳ جاري الإرسال لـ {len(users)} مشترك...")
    success = 0
    for uid in users:
        try:
            await bot.send_message(uid, f"📢 **إعلان:**\n\n{parts[1]}", parse_mode="Markdown")
            success += 1
            await asyncio.sleep(0.03)
        except Exception:
            pass
    await status.edit_text(f"📊 تم الإرسال بنجاح إلى: {success}")

# --- معالجة الروابط (منشورات فردية أو حسابات إنستجرام) ---
@dp.message(F.text.regexp(r'https?://\S+'))
async def handle_media_url(message: types.Message):
    user_id = message.from_user.id
    _, is_banned = get_user_data(user_id)
    if is_banned:
        return await message.answer("❌ عذراً، أنت محظور.")

    if CHANNEL_USERNAME and CHANNEL_USERNAME != "@YourChannelUsername":
        if not await check_subscription(user_id):
            return await message.answer("⚠️ يجب عليك الاشتراك في القناة أولاً! اضغط `/start`.")

    if user_id in ACTIVE_USERS:
        return await message.answer("⚠️ لديك طلب قيد المعالجة حالياً، انتظر حتى ينتهي.")

    url_match = re.search(r'https?://\S+', message.text)
    if not url_match:
        return await message.answer("❌ لم أتمكن من العثور على رابط صحيح.")
    
    url = url_match.group(0)
    
    # 🔍 التحقق هل الرابط حساب إنستجرام (Profile) أم منشور عادي؟
    # روابط الحسابات عادة لا تحتوي على /p/ أو /reel/ أو /tv/ أو /stories/ وتكون مرتبطة باسم المستخدم
    is_ig_profile = "instagram.com" in url and not any(x in url for x in ["/p/", "/reel/", "/tv/", "/stories/"])

    cache_key = f"{user_id}_{message.message_id}"
    URL_CACHE[cache_key] = url
    ACTIVE_USERS.add(user_id)

    if is_ig_profile:
        # إذا كان رابط حساب إنستجرام، اعرض خيارات الستوري والهايلات والمنشورات
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📖 تحميل الستوري (Stories)", callback_data=f"ig_opt:stories:{cache_key}"),
                InlineKeyboardButton(text="✨ تحميل الهايلات (Highlights)", callback_data=f"ig_opt:highlights:{cache_key}")
            ],
            [
                InlineKeyboardButton(text="🎬 آخر 5 منشورات", callback_data=f"ig_opt:posts_5:{cache_key}"),
                InlineKeyboardButton(text="📦 الحساب بالكامل (الكل)", callback_data=f"ig_opt:posts_all:{cache_key}")
            ],
            [InlineKeyboardButton(text="❌ إلغاء", callback_data=f"cancel:{cache_key}")]
        ])
        await message.answer("👤 **تم التعرف على حساب إنستجرام!**\nما الذي ترغب في تحميله من هذا الحساب؟ 👇", parse_mode="Markdown", reply_markup=keyboard)
    else:
        # منشور فردي عادي (يوتيوب، تيك توك، إنستجرام بوست...)
        process_msg = await message.answer("⏳ **جاري تحليل الرابط واستخراج المعاينة الذكية...**", parse_mode="Markdown")

        try:
            loop = asyncio.get_running_loop()
            def extract_info():
                with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True}) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, extract_info)
            title = info.get('title', 'محتوى بدون عنوان')
            thumbnail = info.get('thumbnail')
            uploader = info.get('uploader') or info.get('channel') or 'غير معروف'
            
            add_history(user_id, url, title)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🎬 جودة عالية (HD)", callback_data=f"dl:best:{cache_key}"),
                    InlineKeyboardButton(text="📱 جودة متوسطة", callback_data=f"dl:medium:{cache_key}")
                ],
                [
                    InlineKeyboardButton(text="🎵 استخراج صوت (MP3)", callback_data=f"dl:audio:{cache_key}"),
                    InlineKeyboardButton(text="📝 استخراج الترجمة (SRT)", callback_data=f"dl:sub:{cache_key}")
                ],
                [InlineKeyboardButton(text="❌ إلغاء الطلب", callback_data=f"cancel:{cache_key}")]
            ])

            caption = (
                f"📌 **العنوان:** {title[:90]}\n"
                f"👤 **المصدر:** {uploader}\n\n"
                "اختر العملية المطلوبة أدناه 👇"
            )

            await process_msg.delete()
            if thumbnail:
                await message.answer_photo(photo=thumbnail, caption=caption, parse_mode="Markdown", reply_markup=keyboard)
            else:
                await message.answer(caption, parse_mode="Markdown", reply_markup=keyboard)

        except Exception as e:
            logging.error(f"Preview Error: {e}")
            ACTIVE_USERS.discard(user_id)
            await process_msg.edit_text("❌ عذراً، لم أتمكن من قراءة الرابط. قد يكون الحساب خاصاً أو غير مدعوم.")

# --- معالجة خيارات حسابات إنستجرام (ستوري، هايلات، منشورات) ---
@dp.callback_query(F.data.startswith("ig_opt:"))
async def process_ig_options(callback: types.CallbackQuery):
    data_parts = callback.data.split(":")
    option = data_parts[1]
    cache_key = data_parts[2]
    user_id = callback.from_user.id
    
    url = URL_CACHE.get(cache_key)
    if not url:
        ACTIVE_USERS.discard(user_id)
        return await callback.answer("❌ انتهت صلاحية الطلب، أرسل الرابط مجدداً.", show_alert=True)
    
    option_names = {
        "stories": "الستوريهات (Stories)",
        "highlights": "الهايلات (Highlights)",
        "posts_5": "آخر 5 منشورات",
        "posts_all": "جميع منشورات الحساب"
    }
    
    await callback.message.edit_text(f"⏳ **جاري جلب وتحميل {option_names.get(option, 'المحتوى')}... قد يستغرق ذلك بعض الوقت.**", parse_mode="Markdown")
    
    filename = None
    try:
        loop = asyncio.get_running_loop()
        
        # إعدادات yt-dlp للتعامل مع الستوري أو الحسابات
        ydl_opts = {
            'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
            'format': 'best',
            'quiet': True,
        }
        
        if option == "posts_5":
            ydl_opts['playlistend'] = 5
        elif option == "stories":
            # بعض الروابط تتطلب صيغة مخصصة للستوري عبر yt-dlp
            pass

        def download_profile():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl, info

        ydl_instance, info = await loop.run_in_executor(None, download_profile)
        
        # التعامل مع القوائم (Entries) إذا كان الحساب يضم عدة صور/فيديوهات
        if 'entries' in info:
            count = 0
            for entry in info['entries']:
                if entry and count < (5 if option == "posts_5" else 20):
                    entry_file = ydl_instance.prepare_filename(entry)
                    if os.path.exists(entry_file):
                        ext = entry_file.split('.')[-1].lower()
                        file_input = types.FSInputFile(entry_file)
                        if ext in ['mp4', 'mkv', 'webm']:
                            await callback.message.answer_video(video=file_input, caption="✨ منشور من الحساب")
                        elif ext in ['jpg', 'jpeg', 'png', 'webp']:
                            await callback.message.answer_photo(photo=file_input, caption="✨ صورة من الحساب")
                        count += 1
                        try:
                            os.remove(entry_file)
                        except:
                            pass
            await callback.message.answer("✅ تم الانتهاء من إرسال المحتوى المطلوبة بنجاح!")
        else:
            filename = ydl_instance.prepare_filename(info)
            if filename and os.path.exists(filename):
                file_input = types.FSInputFile(filename)
                await callback.message.answer_document(document=file_input, caption="✨ ملف الوسائط المُحمل")
            else:
                await callback.message.edit_text("❌ عذراً، الحساب خاص (Private) أو لا توجد محتويات متاحة للتحميل حالياً.")

    except Exception as e:
        logging.error(f"IG DL Error: {e}")
        await callback.message.edit_text("❌ حدث خطأ أثناء جلب محتوى الحساب. تأكد أن الحساب عام (Public).")
    
    finally:
        ACTIVE_USERS.discard(user_id)
        URL_CACHE.pop(cache_key, None)

# --- معالجة التحميل الفعلي للمنشورات العادية ---
@dp.callback_query(F.data.startswith("dl:"))
async def process_quality_choice(callback: types.CallbackQuery):
    data_parts = callback.data.split(":")
    quality_type = data_parts[1]
    cache_key = data_parts[2]
    user_id = callback.from_user.id
    
    url = URL_CACHE.get(cache_key)
    if not url:
        ACTIVE_USERS.discard(user_id)
        return await callback.answer("❌ انتهت صلاحية الطلب، أرسل الرابط مجدداً.", show_alert=True)
    
    if callback.message.photo:
        await callback.message.edit_caption(caption="⏳ **جاري تنفيذ العملية، يرجى الانتظار...**", parse_mode="Markdown")
    else:
        await callback.message.edit_text("⏳ **جاري تنفيذ العملية، يرجى الانتظار...**", parse_mode="Markdown")
    
    filename = None
    try:
        loop = asyncio.get_running_loop()
        
        if quality_type == "best":
            ydl_opts = {'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s', 'format': 'bestvideo+bestaudio/best', 'merge_output_format': 'mp4', 'noplaylist': True, 'quiet': True}
        elif quality_type == "medium":
            ydl_opts = {'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s', 'format': 'best[height<=480]/best', 'noplaylist': True, 'quiet': True}
        elif quality_type == "audio":
            ydl_opts = {'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s', 'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}], 'noplaylist': True, 'quiet': True}
        elif quality_type == "sub":
            ydl_opts = {'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s', 'writesubtitles': True, 'writeautomaticsub': True, 'skip_download': True, 'subtitleslangs': ['ar', 'en'], 'quiet': True}

        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl, info

        ydl_instance, info = await loop.run_in_executor(None, download)
        
        if quality_type == "audio":
            base_filename = ydl_instance.prepare_filename(info)
            filename = os.path.splitext(base_filename)[0] + '.mp3'
        elif quality_type == "sub":
            base_filename = ydl_instance.prepare_filename(info)
            filename = None
            for ext in ['.vtt', '.srt']:
                potential_sub = os.path.splitext(base_filename)[0] + ext
                if os.path.exists(potential_sub):
                    filename = potential_sub
                    break
        else:
            filename = ydl_instance.prepare_filename(info)
            if filename and not os.path.exists(filename):
                base, _ = os.path.splitext(filename)
                if os.path.exists(base + '.mp4'):
                    filename = base + '.mp4'

        if filename and os.path.exists(filename):
            if os.path.getsize(filename) > 50 * 1024 * 1024:
                await callback.message.edit_text("⚠️ الملف أكبر من 50 ميجابايت.")
                return

            title = info.get('title', 'ملف مُحمل')
            file_input = types.FSInputFile(filename)
            
            if quality_type == "audio":
                await callback.message.answer_audio(audio=file_input, caption=f"🎵 **{title[:80]}**", parse_mode="Markdown")
            elif quality_type == "sub":
                await callback.message.answer_document(document=file_input, caption=f"📜 **ملف الترجمة:** {title[:60]}", parse_mode="Markdown")
            else:
                await callback.message.answer_video(video=file_input, caption=f"✨ **{title[:80]}**", parse_mode="Markdown")
            
            await callback.message.delete()
        else:
            await callback.message.edit_text("❌ لم يتم العثور على الملف الناتج.")

    except Exception as e:
        logging.error(f"DL Error: {e}")
        await callback.message.edit_text("❌ حدث خطأ أثناء تحميل الملف.")
    
    finally:
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception:
                pass
        ACTIVE_USERS.discard(user_id)
        URL_CACHE.pop(cache_key, None)

@dp.callback_query(F.data.startswith("cancel:"))
async def callback_cancel(callback: types.CallbackQuery):
    cache_key = callback.data.split(":")[1]
    ACTIVE_USERS.discard(callback.from_user.id)
    URL_CACHE.pop(cache_key, None)
    try:
        await callback.message.delete()
    except Exception:
        pass

@dp.message(F.text)
async def handle_other_text(message: types.Message):
    _, is_banned = get_user_data(message.from_user.id)
    if not is_banned:
        await message.answer("💡 أهلاً بك! أرسل رابطاً صحيحاً (رابط منشور أو حساب إنستجرام) للبدء.")

async def main():
    logging.info("🚀 البوت الأسطوري جاهز ويعمل بكفاءة مطلقة...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    asyncio.run(main())
