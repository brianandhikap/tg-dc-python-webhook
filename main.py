import asyncio
import threading
from bot import TelegramBot
from web import run_web_server

def start_web_server():
    """Start Flask web server in separate thread"""
    print("🌐 Starting web server...")
    run_web_server()

async def main():
    """Main function"""
    # Start web server in background thread
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    
    # Wait a bit for web server to start
    await asyncio.sleep(2)
    
    # Start Telegram bot with debug mode
    bot = TelegramBot(debug=True)  # Set False to disable debug logs
    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\n⏹️ Stopping bot...")
        await bot.stop()
    except Exception as e:
        print(f"❌ Error: {e}")
        await bot.stop()

if __name__ == '__main__':
    asyncio.run(main())
