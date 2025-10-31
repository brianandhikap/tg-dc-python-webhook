import os
import asyncio
import aiohttp
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from datetime import datetime
import config
from database import Database

class TelegramBot:
    def __init__(self):
        self.client = TelegramClient(
            f'{config.SESSION_PATH}/{config.TELEGRAM_SESSION}',
            config.TELEGRAM_API_ID,
            config.TELEGRAM_API_HASH
        )
        self.db = Database()
        self.base_url = f"https://{config.HOST}:{config.PORT}"
        
    async def start(self):
        """Start the Telegram client"""
        await self.client.start(phone=config.TELEGRAM_PHONE)
        print("✅ Telegram client started")
        
        # Get user info
        me = await self.client.get_me()
        print(f"👤 Logged in as: {me.first_name} ({me.phone})")
        
        # Setup event handlers
        self.setup_handlers()
        
        # Get groups to monitor
        groups = self.db.get_all_groups()
        print(f"📊 Monitoring {len(groups)} groups from database")
        
        print("🚀 Bot is running... Press Ctrl+C to stop")
        await self.client.run_until_disconnected()
    
    def setup_handlers(self):
        """Setup message handlers"""
        @self.client.on(events.NewMessage())
        async def handler(event):
            await self.handle_message(event)
    
    async def handle_message(self, event):
        """Handle incoming messages"""
        try:
            # Get chat and message info
            chat = await event.get_chat()
            chat_id = event.chat_id
            
            # Convert to proper group ID format
            if not str(chat_id).startswith('-100'):
                chat_id = int(f"-100{chat_id}")
            
            # Get topic ID (for forum/topics)
            topic_id = 0
            if hasattr(event.message, 'reply_to') and event.message.reply_to:
                if hasattr(event.message.reply_to, 'reply_to_top_id'):
                    topic_id = event.message.reply_to.reply_to_top_id or 0
                elif hasattr(event.message.reply_to, 'forum_topic') and event.message.reply_to.forum_topic:
                    topic_id = event.message.reply_to.reply_to_msg_id or 0
            
            # Check if this group+topic has webhook
            webhook_url = self.db.get_webhook(chat_id, topic_id)
            if not webhook_url:
                return  # No webhook configured for this group/topic
            
            # Get sender info
            sender = await event.get_sender()
            sender_name = self.get_sender_name(sender)
            
            # Get and save avatar
            avatar_url = await self.get_avatar_url(sender, sender_name)
            
            # Prepare message content
            content = event.message.message or ""
            
            # Handle media
            embeds = []
            if event.message.media:
                media_url = await self.handle_media(event.message)
                if media_url:
                    embed = {
                        "image": {"url": media_url}
                    }
                    if content:
                        embed["description"] = content
                        content = ""  # Move text to embed
                    embeds.append(embed)
            
            # Send to Discord
            await self.send_to_discord(
                webhook_url=webhook_url,
                username=sender_name,
                avatar_url=avatar_url,
                content=content,
                embeds=embeds if embeds else None
            )
            
            print(f"✅ Forwarded message from {sender_name} in {chat.title} (Topic: {topic_id})")
            
        except Exception as e:
            print(f"❌ Error handling message: {e}")
    
    def get_sender_name(self, sender):
        """Get sender display name"""
        if hasattr(sender, 'first_name'):
            name = sender.first_name or ""
            if hasattr(sender, 'last_name') and sender.last_name:
                name += f" {sender.last_name}"
            return name.strip() or "Unknown User"
        elif hasattr(sender, 'title'):
            return sender.title
        return "Unknown User"
    
    async def get_avatar_url(self, sender, sender_name):
        """Download and get avatar URL"""
        try:
            # Create safe filename
            safe_name = "".join(c for c in sender_name if c.isalnum() or c in (' ', '_')).rstrip()
            safe_name = safe_name.replace(' ', '_')
            
            avatar_path = f"{config.MEDIA_AVA_PATH}/{safe_name}.jpg"
            
            # Download avatar if not exists or older than 1 day
            if not os.path.exists(avatar_path) or self.is_file_old(avatar_path, days=1):
                photo = await self.client.download_profile_photo(
                    sender,
                    file=avatar_path
                )
                if photo:
                    print(f"📸 Downloaded avatar for {sender_name}")
            
            if os.path.exists(avatar_path):
                return f"{self.base_url}/ava/{safe_name}.jpg"
            
        except Exception as e:
            print(f"⚠️ Error downloading avatar: {e}")
        
        # Return default Discord avatar if failed
        return None
    
    async def handle_media(self, message):
        """Download and get media URL"""
        try:
            if isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
                # Generate unique filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                extension = self.get_media_extension(message.media)
                filename = f"{timestamp}_{message.id}{extension}"
                filepath = f"{config.MEDIA_FILES_PATH}/{filename}"
                
                # Download media
                await self.client.download_media(message, filepath)
                print(f"📥 Downloaded media: {filename}")
                
                return f"{self.base_url}/media/{filename}"
                
        except Exception as e:
            print(f"⚠️ Error downloading media: {e}")
        
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
    
    async def send_to_discord(self, webhook_url, username, avatar_url, content, embeds=None):
        """Send message to Discord webhook"""
        try:
            payload = {
                "username": username[:80],  # Discord limit
            }
            
            if avatar_url:
                payload["avatar_url"] = avatar_url
            
            if content:
                # Discord has 2000 char limit
                payload["content"] = content[:2000]
            
            if embeds:
                payload["embeds"] = embeds[:10]  # Discord limit: 10 embeds
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status not in [200, 204]:
                        print(f"⚠️ Discord webhook error: {response.status}")
                        text = await response.text()
                        print(f"Response: {text}")
                    
        except Exception as e:
            print(f"❌ Error sending to Discord: {e}")
    
    async def stop(self):
        """Stop the bot"""
        await self.client.disconnect()
        self.db.close()
        print("👋 Bot stopped")
