import asyncio
from telethon import TelegramClient, events
import config

async def test_detection():
    client = TelegramClient(
        f'{config.SESSION_PATH}/{config.TELEGRAM_SESSION}',
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH
    )
    
    await client.start(phone=config.TELEGRAM_PHONE)
    
    # Group yang mau di-test
    TEST_GROUP_ID = -1001487307688  # MVP Crypstocks
    
    print("=" * 80)
    print(f"TESTING TOPIC DETECTION FOR GROUP: {TEST_GROUP_ID}")
    print("=" * 80)
    print("\n📌 Send a message in the topic you want to monitor...")
    print("Press Ctrl+C to stop\n")
    
    @client.on(events.NewMessage(chats=[TEST_GROUP_ID]))
    async def handler(event):
        chat = await event.get_chat()
        
        print(f"\n{'='*80}")
        print(f"📨 MESSAGE RECEIVED")
        print(f"{'='*80}")
        print(f"Chat: {chat.title}")
        print(f"Group ID: {event.chat_id}")
        
        # Multiple detection methods
        topic_methods = {}
        
        # Method 1: reply_to_top_id
        if hasattr(event.message, 'reply_to') and event.message.reply_to:
            if hasattr(event.message.reply_to, 'reply_to_top_id'):
                topic_methods['reply_to_top_id'] = event.message.reply_to.reply_to_top_id
            if hasattr(event.message.reply_to, 'reply_to_msg_id'):
                topic_methods['reply_to_msg_id'] = event.message.reply_to.reply_to_msg_id
            if hasattr(event.message.reply_to, 'forum_topic'):
                topic_methods['forum_topic'] = event.message.reply_to.forum_topic
        
        # Method 2: message attributes
        topic_methods['message_id'] = event.message.id
        
        # Method 3: Raw attributes
        print(f"\n🔍 TOPIC DETECTION RESULTS:")
        for method, value in topic_methods.items():
            print(f"   {method}: {value}")
        
        # Print raw reply_to object
        if hasattr(event.message, 'reply_to'):
            print(f"\n📋 Raw reply_to object:")
            print(f"   {event.message.reply_to}")
        
        # Print message text
        if event.message.message:
            preview = event.message.message[:100]
            print(f"\n💬 Message: {preview}")
        
        print(f"\n✅ RECOMMENDED TOPIC_ID: {topic_methods.get('reply_to_top_id', 0)}")
        print(f"\n📝 SQL Command:")
        topic_id = topic_methods.get('reply_to_top_id', 0)
        print(f"   INSERT INTO tg_dc_webhook (group_id, topic_id, webhook_url)")
        print(f"   VALUES ({event.chat_id}, {topic_id}, 'YOUR_WEBHOOK_URL');")
        print(f"{'='*80}\n")
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(test_detection())
