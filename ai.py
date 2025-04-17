import os
import asyncio
import logging
import requests
from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeVideo
from telethon.errors import MessageNotModifiedError
import yt_dlp

# ---------------- تنظیمات کلاینت ----------------
api_id = 18377832  # جایگزین کن با api_id واقعی
api_hash = 'ed8556c450c6d0fd68912423325dd09c'  # جایگزین کن با api_hash واقعی
session_name = 'anon'
client = TelegramClient(session_name, api_id, api_hash)

# ---------------- حافظه‌های موقت ----------------
temp_formats = {}
temp_thumbnails = {}
user_requests = {}
last_progress_text = {}

# ---------------- ابزارها ----------------
def create_progress_bar(percentage: float, width: int = 25) -> str:
    filled = int(width * percentage / 100)
    empty = width - filled
    bar = '━' * filled + '─' * empty
    return f"[{bar}] {percentage:.1f}%"

def get_file_size(url):
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        size = int(response.headers.get('content-length', 0))
        return size, f"{size / 1024 / 1024:.2f} MB" if size > 0 else "حجم نامشخص"
    except:
        return 0, "حجم نامشخص"

def download_thumbnail(url, filename):
    try:
        response = requests.get(url)
        with open(filename, 'wb') as f:
            f.write(response.content)
        return True
    except:
        return False

async def cleanup_temp_files(message_id, temp_filename):
    if os.path.exists(temp_filename):
        os.remove(temp_filename)
    if message_id in temp_thumbnails:
        thumb_filename = temp_thumbnails[message_id]
        if os.path.exists(thumb_filename):
            os.remove(thumb_filename)
        del temp_thumbnails[message_id]
    if message_id in user_requests:
        del user_requests[message_id]
    if message_id in temp_formats:
        del temp_formats[message_id]
    if message_id in last_progress_text:
        del last_progress_text[message_id]

# ---------------- دانلود و ارسال ----------------
async def download_and_upload(event, url, title, quality, message_id, original_message, client):
    temp_filename = f"temp_{hash(url)}_{asyncio.get_event_loop().time()}.mp4"
    total_size, _ = get_file_size(url)
    downloaded = 0
    last_update_time = 0

    try:
        await original_message.edit("📥 در حال دانلود...", buttons=None)
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(temp_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                current_time = asyncio.get_event_loop().time()
                if current_time - last_update_time > 1.0 and total_size > 0:
                    last_update_time = current_time
                    percentage = (downloaded / total_size) * 100
                    progress_bar = create_progress_bar(percentage)
                    size_mb = downloaded / (1024 * 1024)
                    total_mb = total_size / (1024 * 1024)
                    progress_text = (
                        f"📥 در حال دانلود...\n"
                        f"{progress_bar}\n"
                        f"💾 {size_mb:.1f}MB / {total_mb:.1f}MB"
                    )
                    if message_id not in last_progress_text or last_progress_text[message_id] != progress_text:
                        try:
                            await original_message.edit(progress_text, buttons=None)
                            last_progress_text[message_id] = progress_text
                        except MessageNotModifiedError:
                            pass

        last_update_time = 0
        
        async def progress_callback(current, total):
            nonlocal last_update_time
            current_time = asyncio.get_event_loop().time()
            if current_time - last_update_time > 1.0:
                last_update_time = current_time
                percentage = (current / total) * 100
                progress_bar = create_progress_bar(percentage)
                size_mb = current / (1024 * 1024)
                total_mb = total / (1024 * 1024)
                progress_text = (
                    f"📤 در حال آپلود...\n"
                    f"{progress_bar}\n"
                    f"💾 {size_mb:.1f}MB / {total_mb:.1f}MB"
                )
                if message_id not in last_progress_text or last_progress_text[message_id] != progress_text:
                    try:
                        await original_message.edit(progress_text, buttons=None)
                        last_progress_text[message_id] = progress_text
                    except MessageNotModifiedError:
                        pass

        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration')
            view_count = info.get('view_count')
            like_count = info.get('like_count')
            
            caption = f"🎥 عنوان: {title}\n📹 کیفیت: {quality}\n"
            if duration:
                caption += f"⏱ مدت زمان: {duration//60}:{duration%60:02d}\n"
            if view_count:
                caption += f"👁 بازدید: {view_count:,}\n"
            if like_count:
                caption += f"👍 لایک: {like_count:,}"

        thumb_filename = temp_thumbnails.get(message_id)
        
        await client.send_file(
            event.chat_id,
            file=temp_filename,
            caption=caption,
            reply_to=message_id,
            thumb=thumb_filename if thumb_filename and os.path.exists(thumb_filename) else None,
            supports_streaming=True,
            attributes=[DocumentAttributeVideo(duration=duration if duration else 0, w=1920, h=1080, supports_streaming=True)],
            progress_callback=progress_callback
        )
        await original_message.delete()

    except Exception as e:
        await original_message.edit(f"خطا در پردازش: {str(e)}")
    finally:
        await cleanup_temp_files(message_id, temp_filename)

# ---------------- مدیریت دستورات ----------------
async def dl_handlers(client):
    @client.on(events.NewMessage(pattern=r'.*(pornhub\.com|xvideos\.com|xnxx\.com)/.*'))
    async def handle_url(event):
        url = event.message.text
        processing_msg = await event.reply("در حال پردازش لینک...")

        ydl_opts = {
            'quiet': True,
            'format': 'bestvideo+bestaudio/best',
            'noplaylist': True,
            'no_warnings': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                title = info.get('title', 'عنوان پیدا نشد')
                thumbnail = info.get('thumbnail')
                duration = info.get('duration')
                view_count = info.get('view_count')
                
                thumb_filename = f"thumb_{hash(url)}.jpg"
                if thumbnail and download_thumbnail(thumbnail, thumb_filename):
                    temp_thumbnails[event.message.id] = thumb_filename

                formats = []
                for f in info.get('formats', []):
                    protocol = f.get('protocol', '').lower()
                    if f.get('url') and f.get('ext') == 'mp4' and 'hls' not in protocol and 'm3u8' not in protocol:
                        size_bytes, size_mb = get_file_size(f['url'])
                        formats.append({
                            'quality': f.get('format', 'کیفیت نامشخص'),
                            'url': f.get('url'),
                            'size': size_mb,
                            'size_bytes': size_bytes
                        })

                if not formats:
                    await processing_msg.edit("هیچ فرمتی پیدا نشد!")
                    return

                message_id = event.message.id
                temp_formats[message_id] = formats
                user_requests[message_id] = {
                    'user_id': event.sender_id,
                    'formats': formats,
                    'title': title
                }

                buttons = []
                for i, fmt in enumerate(formats):
                    quality_text = fmt['quality'].split('-')[0].strip()
                    buttons.append([Button.inline(f"{quality_text} ({fmt['size']})", data=f"dl_quality_{i}")])
                
                duration_str = f"\n⏱ مدت زمان: {duration//60}:{duration%60:02d}" if duration else ""
                views_str = f"\n👁 بازدید: {view_count:,}" if view_count else ""
                
                await processing_msg.delete()
                await event.reply(
                    f"🎥 عنوان: {title}{duration_str}{views_str}\nکیفیت مورد نظر رو انتخاب کن:",
                    buttons=buttons,
                    file=thumb_filename if os.path.exists(thumb_filename) else None
                )

        except Exception as e:
            await processing_msg.edit(f"خطایی رخ داد: {str(e)}")

    @client.on(events.CallbackQuery(pattern=r'^dl_quality_\d+$'))
    async def button(event):
        try:
            data = event.data.decode('utf-8')
            message = await event.get_message()
            message_id = message.reply_to_msg_id if message.reply_to_msg_id else message.id
            
            if message_id not in user_requests or event.sender_id != user_requests[message_id]['user_id']:
                await event.answer("شما اجازه انتخاب کیفیت برای درخواست کاربر دیگر را ندارید!", alert=True)
                return

            request_info = user_requests[message_id]
            title = request_info['title']
            formats = request_info['formats']

            if data.startswith("dl_quality_"):
                fmt_index = int(data.split('_')[2])
                if fmt_index < len(formats):
                    selected_format = formats[fmt_index]
                    quality_text = selected_format['quality'].split('-')[0].strip()
                    await download_and_upload(event, selected_format['url'], title, quality_text, message_id, message, client)

        except Exception as e:
            await event.answer(f"خطایی رخ داد: {str(e)}", alert=True)

# ---------------- اجرای برنامه ----------------
async def main():
    await dl_handlers(client)
    print("ربات آماده است.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        client.start()
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("ربات متوقف شد.")
