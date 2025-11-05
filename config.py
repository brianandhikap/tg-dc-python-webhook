import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Config
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_PHONE = os.getenv('TELEGRAM_PHONE')
TELEGRAM_SESSION = os.getenv('TELEGRAM_SESSION', 'telegram_session')

# MySQL Config
MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

# Web Server Config
HOST = os.getenv('HOST', '103.103.20.15')
PORT = int(os.getenv('PORT', 1212))

# Performance Config
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 10))  # Parallel message processors
DISCORD_RATE_LIMIT = int(os.getenv('DISCORD_RATE_LIMIT', 5))  # Max concurrent Discord requests
QUEUE_MAX_SIZE = int(os.getenv('QUEUE_MAX_SIZE', 1000))
ENABLE_CACHE = os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
CACHE_TTL = int(os.getenv('CACHE_TTL', 300))  # 5 minutes

# Media Paths
MEDIA_AVA_PATH = 'media/ava'
MEDIA_FILES_PATH = 'media/media'
SESSION_PATH = 'session'

# Create directories
os.makedirs(MEDIA_AVA_PATH, exist_ok=True)
os.makedirs(MEDIA_FILES_PATH, exist_ok=True)
os.makedirs(SESSION_PATH, exist_ok=True)
