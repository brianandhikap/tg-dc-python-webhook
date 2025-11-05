import asyncio
import threading
from bot import TelegramBot
from web import run_web_server

# Use uvloop for better async performance (Linux only)
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("✅ Using uvloop for better performance")
except ImportError:
    print("⚠️ uvloop not available, using default event loop")

def start_web_server():
    """Start Flask web server in separate thread"""
    print("🌐 Starting web server...")
    run_web_server()

async def main():
    """Main function"""
    # Start web server in background
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    
    await asyncio.sleep(2)
    
    # Start bot
    bot = TelegramBot(debug=False)  # Set True for verbose logging
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
