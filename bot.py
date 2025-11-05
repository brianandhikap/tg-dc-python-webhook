import os
import asyncio
import aiohttp
import logging
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.errors import FloodWaitError, ServerError, TimedOutError
from datetime import datetime
import config
from database import Database

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, debug=False):
        self.client = TelegramClient(
            f'{config.SESSION_PATH}/{config.TELEGRAM_SESSION}',
            config.TELEGRAM_API_ID,
            config.TELEGRAM_API_HASH,
            connection_retries=5,
            retry_delay=1,
            auto_reconnect=True,
            timeout=30
        )
        self.db = Database()
        self.base_url = f"http://{config.HOST}:{config.PORT}"
        self.debug = debug
        
        # High-performance queue
        self.message_queue = asyncio.Queue(maxsize=config.QUEUE_MAX_SIZE)
        
        # Semaphore for Discord rate limiting
        self.discord_semaphore = asyncio.Semaphore(config.DISCORD_RATE_LIMIT)
        
        # Shared aiohttp session (connection reuse)
        self.http_session = None
        
        # Statistics
        self.stats = {
            'received': 0,
            'processed': 0,
            'failed': 0,
            'skipped': 0
        }
        
    async def start(self):
        """Start the Telegram client"""
        try:
            await self.client.start(phone=config.TELEGRAM_PHONE)
            logger.info("✅ Telegram client started")
            
            me = await self.client.get_me()
            logger.info(f"👤 Logged in as: {me.first_name} ({me.phone})")
            
            # Create shared HTTP session
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            connector = aiohttp.TCPConnector(limit=50, limit_per_host=10)
            self.http_session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            
            # Setup event handlers
            self.setup_handlers()
            
            # Start multiple worker tasks
            workers = []
            for i in range(config.MAX_WORKERS):
                worker = asyncio.create_task(self.message_worker(i))
                workers.append(worker)
            logger.info(f"🔄 Started {config.MAX_WORKERS} message workers")
            
            # Start stats reporter
            asyncio.create_task(self.stats_reporter())
            
            # Get groups to monitor
            groups = self.db.get_all_groups()
            logger.info(f"📊 Monitoring {len(groups)} groups from database")
            
            logger.info("="*60)
            logger.info("🚀 HIGH PERFORMANCE MODE - Bot is running...")
            logger.info("="*60)
            
            # Keep alive
            await self.keep_alive()
            
        except Exception as e:
            logger.error(f"❌ Error in start: {e}", exc_info=True)
            raise
    
    async def keep_alive(self):
        """Keep the bot alive"""
        while True:
            try:
                await self.client.run_until_disconnected()
            except (ServerError, TimedOutError) as e:
                logger.warning(f"⚠️ Connection error: {e}. Reconnecting...")
                await asyncio.sleep(3)
                try:
                    await self.client.connect()
                    logger.info("✅ Reconnected")
                except Exception as reconnect_error:
                    logger.error(f"❌ Reconnection failed: {reconnect_error}")
                    await asyncio.sleep(5)
            except KeyboardInterrupt:
                logger.info("⏹️ Stopping bot...")
                break
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}", exc_info=True)
                await asyncio.sleep(3)
    
    def setup_handlers(self):
        """Setup message handlers"""
        @self.client.on(events.NewMessage())
        async def handler(event):
            try:
                self.stats['received'] += 1
                
                # Non-blocking queue put
                try:
                    self.message_queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning(f"⚠️ Queue full! Skipping message {event.message.id}")
                    self.stats['skipped'] += 1
                    
            except Exception as e:
                logger.error(f"❌ Error in handler: {e}")
    
    async def message_worker(self, worker_id):
        """Worker task to process messages from queue"""
        logger.info(f"👷 Worker {worker_id} started")
        
        while True:
            try:
                # Get message from queue (non-blocking with timeout)
                try:
                    event = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                # Process the message
                await self.handle_message(event, worker_id)
                
                # Mark task as done
                self.message_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info(f"🛑 Worker {worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in worker {worker_id}: {e}", exc_info=True)
                await asyncio.sleep(0.1)
    
    async def stats_reporter(self):
        """Report statistics every 30 seconds"""
        while True:
            await asyncio.sleep(30)
            queue_size = self.message_queue.qsize()
            logger.info(
                f"📊 Stats - Received: {self.stats['received']}, "
                f"Processed: {self.stats['processed']}, "
                f"Failed: {self.stats['failed']}, "
                f"Skipped: {self.stats['skipped']}, "
                f"Queue: {queue_size}"
            )
    
    async def handle_message(self, event, worker_id):
        """Handle incoming messages (optimized)"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Get chat info (cached)
            chat = await event.get_chat()
            chat_id = event.chat_id
            
            if not str(chat_id).startswith('-100'):
                chat_id = int(f"-100{chat_id}")
            
            # Fast topic detection
            topic_id = await self.detect_topic_fast(event, chat_id)
            
            # Check database (cached)
            webhook_url = self.db.get_webhook(chat_id, topic_id)
            
            if not webhook_url:
                self.stats['skipped'] += 1
                return
            
            # Get sender info (parallel)
            sender_task = event.get_sender()
            
            # Handle media download (parallel if exists)
            media_task = None
            if event.message.media:
                media_task = asyncio.create_task(self.handle_media_fast(event.message))
            
            # Wait for sender
            sender = await sender_task
            sender_name = self.get_sender_name(sender)
            
            # Get avatar (async, non-blocking)
            avatar_url_task = asyncio.create_task(self.get_avatar_url(sender, sender_name))
            
            # Get content
            content = event.message.message or ""
            
            # Wait for media if exists
            embeds = []
            if media_task:
                media_url = await media_task
                if media_url:
                    embed = {"image": {"url": media_url}}
                    if content:
                        embed["description"] = content
                        content = ""
                    embeds.append(embed)
            
            # Wait for avatar
            avatar_url = await avatar_url_task
            
            # Send to Discord (with rate limiting)
            async with self.discord_semaphore:
                success = await self.send_to_discord_fast(
                    webhook_url=webhook_url,
                    username=sender_name,
                    avatar_url=avatar_url,
                    content=content,
                    embeds=embeds if embeds else None
                )
            
            if success:
                self.stats['processed'] += 1
                elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
                if self.debug:
                    logger.info(f"✅ [W{worker_id}] Forwarded in {elapsed:.0f}ms - {sender_name}")
            else:
                self.stats['failed'] += 1
            
        except FloodWaitError as e:
            logger.warning(f"⚠️ FloodWait: {e.seconds}s")
            await asyncio.sleep(e.seconds)
            self.stats['failed'] += 1
        except Exception as e:
            logger.error(f"❌ Error in handle_message: {e}", exc_info=True)
            self.stats['failed'] += 1
    
    async def detect_topic_fast(self, event, chat_id):
        """Fast topic detection without extra API calls"""
        topic_id = 0
        
        if hasattr(event.message, 'reply_to') and event.message.reply_to:
            reply = event.message.reply_to
            
            # Quick check - no API calls
            if hasattr(reply, 'forum_topic') and reply.forum_topic:
                if hasattr(reply, 'reply_to_msg_id') and reply.reply_to_msg_id:
                    topic_id = reply.reply_to_msg_id
            elif hasattr(reply, 'reply_to_top_id') and reply.reply_to_top_id:
                topic_id = reply.reply_to_top_id
        
        return topic_id
    
    def get_sender_name(self, sender):
        """Get sender display name"""
        try:
            if hasattr(sender, 'first_name'):
                name = sender.first_name or ""
                if hasattr(sender, 'last_name') and sender.last_name:
                    name += f" {sender.last_name}"
                return name.strip() or "Unknown User"
            elif hasattr(sender, 'title'):
                return sender.title
            return "Unknown User"
        except:
            return "Unknown User"
    
    async def get_avatar_url(self, sender, sender_name):
        """Download avatar (async, cached)"""
        try:
            safe_name = "".join(c for c in sender_name if c.isalnum() or c in (' ', '_')).rstrip()
            safe_name = safe_name.replace(' ', '_')
            avatar_path = f"{config.MEDIA_AVA_PATH}/{safe_name}.jpg"
            
            # Check if exists and not old
            if os.path.exists(avatar_path):
                if not self.is_file_old(avatar_path, days=1):
                    return f"{self.base_url}/ava/{safe_name}.jpg"
            
            # Download in background (non-blocking)
            asyncio.create_task(self._download_avatar(sender, avatar_path))
            
            # Return URL immediately (even if not downloaded yet)
            return f"{self.base_url}/ava/{safe_name}.jpg"
            
        except:
            return None
    
    async def _download_avatar(self, sender, avatar_path):
        """Background avatar download"""
        try:
            await self.client.download_profile_photo(sender, file=avatar_path)
        except:
            pass
    
    async def handle_media_fast(self, message):
        """Fast media download - ORIGINAL QUALITY"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            
            if isinstance(message.media, MessageMediaPhoto):
                filename = f"{timestamp}_{message.id}.jpg"
                filepath = f"{config.MEDIA_FILES_PATH}/{filename}"
                
                # Download ORIGINAL quality
                await self.client.download_media(message.photo, filepath, thumb=-1)
                return f"{self.base_url}/media/{filename}"
            
            elif isinstance(message.media, MessageMediaDocument):
                mime = message.media.document.mime_type
                
                if 'image' in mime:
                    ext = '.jpg' if 'jpeg' in mime else ('.png' if 'png' in mime else '.jpg')
                elif 'video' in mime:
                    ext = '.mp4'
                elif 'gif' in mime:
                    ext = '.gif'
                else:
                    for attr in message.media.document.attributes:
                        if hasattr(attr, 'file_name'):
                            ext = os.path.splitext(attr.file_name)[1] or '.file'
                            break
                    else:
                        ext = '.file'
                
                filename = f"{timestamp}_{message.id}{ext}"
                filepath = f"{config.MEDIA_FILES_PATH}/{filename}"
                
                await self.client.download_media(message, filepath)
                return f"{self.base_url}/media/{filename}"
                
        except Exception as e:
            logger.error(f"⚠️ Media download error: {e}")
            return None
    
    def is_file_old(self, filepath, days=1):
        """Check if file is old"""
        if not os.path.exists(filepath):
            return True
        file_time = os.path.getmtime(filepath)
        current_time = datetime.now().timestamp()
        return (current_time - file_time) > (days * 24 * 60 * 60)
    
    async def send_to_discord_fast(self, webhook_url, username, avatar_url, content, embeds=None):
        """Fast Discord send using shared session"""
        try:
            payload = {"username": username[:80]}
            
            if avatar_url:
                payload["avatar_url"] = avatar_url
            if content:
                payload["content"] = content[:2000]
            if embeds:
                payload["embeds"] = embeds[:10]
            
            async with self.http_session.post(webhook_url, json=payload) as response:
                return response.status in [200, 204]
                
        except asyncio.TimeoutError:
            logger.error("❌ Discord timeout")
            return False
        except Exception as e:
            logger.error(f"❌ Discord error: {e}")
            return False
    
    async def stop(self):
        """Stop the bot"""
        try:
            if self.http_session:
                await self.http_session.close()
            await self.client.disconnect()
            self.db.close()
            logger.info("👋 Bot stopped")
        except Exception as e:
            logger.error(f"Error stopping: {e}")
