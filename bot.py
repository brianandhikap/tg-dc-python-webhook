import os
import asyncio
import aiohttp
import logging
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.errors import (
    FloodWaitError,
    ServerError,
    TimedOutError,
    RPCError
)

TelethonConnectionError = (OSError, ConnectionError)
from datetime import datetime
from queue import Queue
from threading import Thread
import config
from database import Database

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, debug=True):
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
        self.message_queue = asyncio.Queue()
        self.is_processing = False
        
    async def start(self):
        """Start the Telegram client"""
        try:
            await self.client.start(phone=config.TELEGRAM_PHONE)
            logger.info("✅ Telegram client started")
            
            # Get user info
            me = await self.client.get_me()
            logger.info(f"👤 Logged in as: {me.first_name} ({me.phone})")
            
            # Setup event handlers
            self.setup_handlers()
            
            # Start message processor
            asyncio.create_task(self.process_message_queue())
            
            # Get groups to monitor
            groups = self.db.get_all_groups()
            logger.info(f"📊 Monitoring {len(groups)} groups from database")
            
            logger.info("="*60)
            logger.info("🚀 Bot is running... Waiting for messages...")
            logger.info("="*60)
            
            # Keep alive loop
            await self.keep_alive()
            
        except Exception as e:
            logger.error(f"❌ Error in start: {e}", exc_info=True)
            raise
    
    async def keep_alive(self):
        """Keep the bot alive and handle reconnection"""
        while True:
            try:
                await self.client.run_until_disconnected()
            except (ServerError, TimedOutError, TelethonConnectionError) as e:
                logger.warning(f"⚠️ Connection error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
                try:
                    await self.client.connect()
                    logger.info("✅ Reconnected successfully")
                except Exception as reconnect_error:
                    logger.error(f"❌ Reconnection failed: {reconnect_error}")
                    await asyncio.sleep(10)
            except KeyboardInterrupt:
                logger.info("⏹️ Stopping bot...")
                break
            except Exception as e:
                logger.error(f"❌ Unexpected error in keep_alive: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    def setup_handlers(self):
        """Setup message handlers"""
        @self.client.on(events.NewMessage())
        async def handler(event):
            try:
                # Add to queue instead of processing directly
                await self.message_queue.put(event)
                if self.debug:
                    logger.info(f"📥 Message added to queue (size: {self.message_queue.qsize()})")
            except Exception as e:
                logger.error(f"❌ Error in handler: {e}", exc_info=True)
    
    async def process_message_queue(self):
        """Process messages from queue one by one"""
        logger.info("🔄 Message processor started")
        
        while True:
            try:
                # Get message from queue
                event = await self.message_queue.get()
                
                # Process the message
                await self.handle_message(event)
                
                # Mark task as done
                self.message_queue.task_done()
                
                # Small delay to prevent rate limiting
                await asyncio.sleep(0.5)
                
            except asyncio.CancelledError:
                logger.info("🛑 Message processor cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in process_message_queue: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def handle_message(self, event):
        """Handle incoming messages"""
        try:
            # Get chat and message info
            chat = await event.get_chat()
            chat_id = event.chat_id
            
            # Convert to proper group ID format
            if not str(chat_id).startswith('-100'):
                chat_id = int(f"-100{chat_id}")
            
            # ============= SMART TOPIC DETECTION =============
            topic_id = 0
            detection_method = "none"
            
            is_forum = hasattr(chat, 'forum') and chat.forum
            
            if hasattr(event.message, 'reply_to') and event.message.reply_to:
                reply = event.message.reply_to
                
                # Priority 1: forum_topic = True
                if hasattr(reply, 'forum_topic') and reply.forum_topic:
                    if hasattr(reply, 'reply_to_msg_id') and reply.reply_to_msg_id:
                        topic_id = reply.reply_to_msg_id
                        detection_method = "forum_topic (direct)"
                
                # Priority 2: reply_to_top_id
                elif hasattr(reply, 'reply_to_top_id') and reply.reply_to_top_id:
                    potential_topic_id = reply.reply_to_top_id
                    
                    try:
                        top_message = await self.client.get_messages(chat_id, ids=potential_topic_id)
                        
                        if top_message:
                            if hasattr(top_message, 'reply_to') and top_message.reply_to:
                                if hasattr(top_message.reply_to, 'forum_topic') and top_message.reply_to.forum_topic:
                                    if hasattr(top_message.reply_to, 'reply_to_msg_id'):
                                        topic_id = top_message.reply_to.reply_to_msg_id
                                        detection_method = "traced from nested reply"
                                elif hasattr(top_message.reply_to, 'reply_to_top_id') and top_message.reply_to.reply_to_top_id:
                                    topic_id = top_message.reply_to.reply_to_top_id
                                    detection_method = "traced from reply chain"
                                else:
                                    topic_id = potential_topic_id
                                    detection_method = "reply_to_top_id (fallback)"
                            else:
                                topic_id = potential_topic_id
                                detection_method = "reply_to_top_id (verified)"
                    except Exception as e:
                        topic_id = potential_topic_id
                        detection_method = f"reply_to_top_id (no verify)"
                        logger.warning(f"Could not verify topic: {e}")
            
            # ============= LOGGING =============
            logger.info("="*70)
            logger.info(f"📨 NEW MESSAGE")
            logger.info(f"Chat: {getattr(chat, 'title', 'Unknown')}")
            logger.info(f"Group ID: {chat_id}")
            logger.info(f"Is Forum: {'YES ✅' if is_forum else 'NO ❌'}")
            logger.info(f"Detected Topic ID: {topic_id} (method: {detection_method})")
            
            # ============= CHECK DATABASE =============
            webhook_url = self.db.get_webhook(chat_id, topic_id)
            
            logger.info(f"🔍 Database Lookup: group_id={chat_id}, topic_id={topic_id}")
            
            if not webhook_url:
                logger.warning(f"❌ NOT FOUND")
                
                all_webhooks = self.db.get_all_webhooks_for_group(chat_id)
                if all_webhooks and self.debug:
                    logger.info(f"⚠️ Group has {len(all_webhooks)} webhooks in database")
                
                logger.info("="*70)
                return
            
            logger.info(f"✅ Webhook found")
            
            # Get sender info
            sender = await event.get_sender()
            sender_name = self.get_sender_name(sender)
            logger.info(f"👤 Sender: {sender_name}")
            
            # Get and save avatar
            avatar_url = await self.get_avatar_url(sender, sender_name)
            
            # Prepare message content
            content = event.message.message or ""
            
            if content:
                preview = content[:100] + "..." if len(content) > 100 else content
                logger.info(f"💬 Content: {preview}")
            
            # Handle media (HIGH QUALITY)
            embeds = []
            if event.message.media:
                logger.info(f"📎 Media detected, downloading HIGH QUALITY version...")
                media_url = await self.handle_media(event.message)
                if media_url:
                    embed = {
                        "image": {"url": media_url}
                    }
                    if content:
                        embed["description"] = content
                        content = ""
                    embeds.append(embed)
            
            # Send to Discord with retry
            logger.info(f"📤 Sending to Discord...")
            success = await self.send_to_discord_with_retry(
                webhook_url=webhook_url,
                username=sender_name,
                avatar_url=avatar_url,
                content=content,
                embeds=embeds if embeds else None
            )
            
            if success:
                logger.info(f"✅ SUCCESS - Forwarded to Discord")
            else:
                logger.error(f"❌ FAILED - Could not forward to Discord")
            
            logger.info("="*70)
            
        except FloodWaitError as e:
            logger.warning(f"⚠️ FloodWait: sleeping for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"❌ Error handling message: {e}", exc_info=True)
    
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
        except Exception as e:
            logger.error(f"Error getting sender name: {e}")
            return "Unknown User"
    
    async def get_avatar_url(self, sender, sender_name):
        """Download and get avatar URL"""
        try:
            safe_name = "".join(c for c in sender_name if c.isalnum() or c in (' ', '_')).rstrip()
            safe_name = safe_name.replace(' ', '_')
            
            avatar_path = f"{config.MEDIA_AVA_PATH}/{safe_name}.jpg"
            
            if not os.path.exists(avatar_path) or self.is_file_old(avatar_path, days=1):
                photo = await self.client.download_profile_photo(
                    sender,
                    file=avatar_path
                )
                if photo:
                    logger.info(f"📸 Downloaded avatar for {sender_name}")
            
            if os.path.exists(avatar_path):
                return f"{self.base_url}/ava/{safe_name}.jpg"
            
        except Exception as e:
            logger.warning(f"⚠️ Error downloading avatar: {e}")
        
        return None
    
    async def handle_media(self, message):
        """Download HIGH QUALITY media and get URL"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # For PHOTOS - download ORIGINAL quality
            if isinstance(message.media, MessageMediaPhoto):
                filename = f"{timestamp}_{message.id}.jpg"
                filepath = f"{config.MEDIA_FILES_PATH}/{filename}"
                
                # Download with size=0 to get ORIGINAL quality (not compressed)
                await self.client.download_media(
                    message.photo,
                    filepath,
                    thumb=-1  # -1 = largest available size (original)
                )
                logger.info(f"📥 Downloaded HIGH QUALITY photo: {filename}")
                return f"{self.base_url}/media/{filename}"
            
            # For DOCUMENTS (images sent as files)
            elif isinstance(message.media, MessageMediaDocument):
                # Get original filename and extension
                mime = message.media.document.mime_type
                
                # Determine extension
                if 'image' in mime:
                    ext = '.jpg' if 'jpeg' in mime else ('.png' if 'png' in mime else '.jpg')
                elif 'video' in mime:
                    ext = '.mp4'
                elif 'gif' in mime:
                    ext = '.gif'
                else:
                    # Try to get from attributes
                    for attr in message.media.document.attributes:
                        if hasattr(attr, 'file_name'):
                            ext = os.path.splitext(attr.file_name)[1] or '.file'
                            break
                    else:
                        ext = '.file'
                
                filename = f"{timestamp}_{message.id}{ext}"
                filepath = f"{config.MEDIA_FILES_PATH}/{filename}"
                
                # Download document (always original quality)
                await self.client.download_media(message, filepath)
                logger.info(f"📥 Downloaded document: {filename}")
                return f"{self.base_url}/media/{filename}"
                
        except Exception as e:
            logger.error(f"⚠️ Error downloading media: {e}", exc_info=True)
        
        return None
    
    def get_media_extension(self, media):
        """Get file extension from media"""
        if isinstance(media, MessageMediaPhoto):
            return ".jpg"
        elif isinstance(media, MessageMediaDocument):
            mime = media.document.mime_type
            if 'image' in mime:
                return '.jpg' if 'jpeg' in mime else '.png'
            elif 'video' in mime:
                return '.mp4'
            elif 'gif' in mime:
                return '.gif'
            else:
                return '.file'
        return '.file'
    
    def is_file_old(self, filepath, days=1):
        """Check if file is older than specified days"""
        if not os.path.exists(filepath):
            return True
        file_time = os.path.getmtime(filepath)
        current_time = datetime.now().timestamp()
        return (current_time - file_time) > (days * 24 * 60 * 60)
    
    async def send_to_discord_with_retry(self, webhook_url, username, avatar_url, content, embeds=None, max_retries=3):
        """Send message to Discord webhook with retry mechanism"""
        for attempt in range(max_retries):
            try:
                success = await self.send_to_discord(webhook_url, username, avatar_url, content, embeds)
                if success:
                    return True
                
                # If failed, wait before retry
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Retry {attempt + 1}/{max_retries} in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                logger.error(f"Error in send attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep((attempt + 1) * 2)
        
        return False
    
    async def send_to_discord(self, webhook_url, username, avatar_url, content, embeds=None):
        """Send message to Discord webhook"""
        try:
            payload = {
                "username": username[:80],
            }
            
            if avatar_url:
                payload["avatar_url"] = avatar_url
            
            if content:
                payload["content"] = content[:2000]
            
            if embeds:
                payload["embeds"] = embeds[:10]
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status not in [200, 204]:
                        text = await response.text()
                        logger.error(f"⚠️ Discord webhook error {response.status}: {text}")
                        return False
                    return True
                    
        except asyncio.TimeoutError:
            logger.error("❌ Discord webhook timeout")
            return False
        except Exception as e:
            logger.error(f"❌ Error sending to Discord: {e}", exc_info=True)
            return False
    
    async def stop(self):
        """Stop the bot"""
        try:
            await self.client.disconnect()
            self.db.close()
            logger.info("👋 Bot stopped")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
