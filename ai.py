import os
import asyncio
import logging
import requests
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo
from telethon.errors import MessageNotModifiedError
import yt_dlp

api_id = 18377832
api_hash = 'ed8556c450c6d0fd68912423325dd09c'
session_name = 'anon'
client = TelegramClient(session_name, api_id, api_hash)

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

async def download_and_upload(event, url, title, quality, message_id, original_message, client):
    temp_filename = f"temp_{hash(url)}_{asyncio.get_event_loop().time()}.mp4"
    total_size, _ = get_file_size(url)
    downloaded = 0
    last_update_time = 0

    try:
        await original_message.edit("📥 در حال دانلود...")

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
                    try:
                        await original_message.edit(progress_text)
                    except MessageNotModifiedError:
                        pass

        await original_message.edit("📤 در حال آپلود...")

        await client.send_file(
            event.chat_id,
            file=temp_filename,
            caption=f"🎵 {title}\n🎚 کیفیت: {quality}",
            reply_to=message_id,
            supports_streaming=True
        )
        await original_message.delete()

    except Exception as e:
        await original_message.edit(f"خطا در پردازش: {str(e)}")
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

@client.on(events.NewMessage(pattern=r'.*(pornhub\.com|xvideos\.com|xnxx\.com|youtube\.com|youtu\.be|instagram\.com|pinterest\.com|soundcloud\.com|spotify\.com)/.*'))
async def handle_media_link(event):
    url = event.raw_text.strip()
    msg = await event.reply("در حال واکشی اطلاعات...")

    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'skip_download': True}) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get('title', 'بدون عنوان')
        description = info.get('description', '')
        duration = info.get('duration')
        thumbnail = info.get('thumbnail')
        formats = info.get('formats', [])

        duration_str = f"\n⏱ زمان: {duration//60}:{duration%60:02d}" if duration else ""
        desc_str = f"\n📝 توضیحات:\n{description[:300]}..." if description else ""

        links = []
        for f in formats:
            if f.get('ext') in ['mp4', 'm4a', 'webm'] and f.get('url'):
                size_bytes, size_mb = get_file_size(f['url'])
                links.append(f"🔹 {f.get('format_note', f['ext'])} - {size_mb} - [دانلود]({f['url']})")

        thumb_file = None
        if thumbnail:
            thumb_file = f"thumb_{hash(url)}.jpg"
            download_thumbnail(thumbnail, thumb_file)

        text = (
            f"🎬 عنوان: {title}"
            f"{duration_str}"
            f"{desc_str}\n\n"
            f"{chr(128279)} لینک‌ها:\n" +
            "\n".join(links[:5]) +
            f"\n\nبرای دانلود با ربات:\n/Don?{url}"
        )

        await msg.delete()
        await event.reply(text, file=thumb_file if thumb_file and os.path.exists(thumb_file) else None, link_preview=False)

    except Exception as e:
        await msg.edit(f"خطا در پردازش لینک: {str(e)}")

@client.on(events.NewMessage(pattern=r'^/Don\?(https?://[^\s]+)'))
async def handle_download_command(event):
    url = event.pattern_match.group(1)
    processing = await event.reply("در حال آماده‌سازی دانلود...")

    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'format': 'bestaudio/best'}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'بدون عنوان')
            formats = info.get('formats', [])
            for f in formats:
                if f.get('ext') in ['mp4', 'm4a', 'webm'] and f.get('url'):
                    await download_and_upload(event, f['url'], title, f.get('format_note', f['ext']), event.id, processing, client)
                    return

        await processing.edit("فرمت قابل دانلود پیدا نشد.")

    except Exception as e:
        await processing.edit(f"خطا در دانلود: {str(e)}")

async def main():
    print("ربات آماده است.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        client.start()
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("ربات متوقف شد.")
