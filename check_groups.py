import asyncio
from telethon import TelegramClient
from telethon.tl.types import Channel
import config

async def check_groups():
    client = TelegramClient(
        f'{config.SESSION_PATH}/{config.TELEGRAM_SESSION}',
        config.TELEGRAM_API_ID,
        config.TELEGRAM_API_HASH
    )
    
    await client.start(phone=config.TELEGRAM_PHONE)
    
    # List group IDs yang mau dicek
    group_ids = [
        -1001921159003,
        # tambahkan group ID lainnya
    ]
    
    print("=" * 70)
    print("GROUP INFORMATION CHECK")
    print("=" * 70)
    
    for group_id in group_ids:
        try:
            entity = await client.get_entity(group_id)
            
            print(f"\n📢 Group: {entity.title}")
            print(f"   ID: {group_id}")
            print(f"   Type: {type(entity).__name__}")
            
            # Check if it's a forum (has topics)
            if isinstance(entity, Channel):
                if hasattr(entity, 'forum') and entity.forum:
                    print(f"   ✅ Has Topics: YES (Forum Group)")
                    print(f"   💡 Use actual topic_id from messages")
                else:
                    print(f"   ❌ Has Topics: NO (Regular Group)")
                    print(f"   💡 Use topic_id = 0 in database")
            
        except Exception as e:
            print(f"\n❌ Error checking {group_id}: {e}")
    
    print("\n" + "=" * 70)
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(check_groups())
