import os
import asyncio
import aiohttp
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from datetime import datetime
import config
from database import Database

class TelegramBot:
    def __init__(self, debug=True):
        self.client = TelegramClient(
            f'{config.SESSION_PATH}/{config.TELEGRAM_SESSION}',
            config.TELEGRAM_API_ID,
            config.TELEGRAM_API_HASH
        )
        self.db = Database()
        self.base_url = f"http://{config.HOST}:{config.PORT}"  # Changed to HTTP
        self.debug = debug
        
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
        
        # Print group list
        for group_id in groups:
            try:
                entity = await self.client.get_entity(group_id)
                print(f"   📢 {entity.title} ({group_id})")
            except:
                print(f"   📢 Group ID: {group_id}")
        
        print("\n" + "="*60)
        print("🚀 Bot is running... Waiting for messages...")
        print("="*60 + "\n")
        
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
            original_chat_id = chat_id
            if not str(chat_id).startswith('-100'):
                chat_id = int(f"-100{chat_id}")
            
            # Get topic ID (for forum/topics)
            topic_id = 0
            if hasattr(event.message, 'reply_to') and event.message.reply_to:
                if hasattr(event.message.reply_to, 'reply_to_top_id'):
                    topic_id = event.message.reply_to.reply_to_top_id or 0
                elif hasattr(event.message.reply_to, 'forum_topic') and event.message.reply_to.forum_topic:
                    topic_id = event.message.reply_to.reply_to_msg_id or 0
            
            if self.debug:
                print(f"\n📨 New message detected!")
                print(f"   Chat: {getattr(chat, 'title', 'Unknown')} ({chat_id})")
                print(f"   Topic ID: {topic_id}")
            
            # Check if this group+topic has webhook
            webhook_url = self.db.get_webhook(chat_id, topic_id)
            
            if not webhook_url:
                if self.debug:
                    print(f"   ⚠️ No webhook configured for this group/topic")
                    print(f"   Database lookup: group_id={chat_id}, topic_id={topic_id}")
                return
            
            if self.debug:
                print(f"   ✅ Webhook found! Forwarding to Discord...")
            
            # Get sender info
            sender = await event.get_sender()
            sender_name = self.get_sender_name(sender)
            
            if self.debug:
                print(f"   👤 Sender: {sender_name}")
            
            # Get and save avatar
            avatar_url = await self.get_avatar_url(sender, sender_name)
            
            # Prepare message content
            content = event.message.message or ""
            
            if self.debug and content:
                preview = content[:50] + "..." if len(content) > 50 else content
                print(f"   💬 Content: {preview}")
            
            # Handle media
            embeds = []
            if event.message.media:
                if self.debug:
                    print(f"   📎 Media detected, downloading...")
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
            success = await self.send_to_discord(
                webhook_url=webhook_url,
                username=sender_name,
                avatar_url=avatar_url,
                content=content,
                embeds=embeds if embeds else None
            )
            
            if success:
                print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] Forwarded: {sender_name} → Discord")
            else:
                print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] Failed to forward from {sender_name}")
            
        except Exception as e:
            print(f"❌ Error handling message: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
    
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
                if photo and self.debug:
                    print(f"   📸 Downloaded avatar for {sender_name}")
            
            if os.path.exists(avatar_path):
                return f"{self.base_url}/ava/{safe_name}.jpg"
            
        except Exception as e:
            if self.debug:
                print(f"   ⚠️ Error downloading avatar: {e}")
        
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
                if self.debug:
                    print(f"   📥 Downloaded media: {filename}")
                
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
                        return False
                    return True
                    
        except Exception as e:
            print(f"❌ Error sending to Discord: {e}")
            return False
    
    async def stop(self):
        """Stop the bot"""
        await self.client.disconnect()
        self.db.close()
        print("👋 Bot stopped")
