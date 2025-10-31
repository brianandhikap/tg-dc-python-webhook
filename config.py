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

# Media Paths
MEDIA_AVA_PATH = 'media/ava'
MEDIA_FILES_PATH = 'media/media'
SESSION_PATH = 'session'

# Create directories if not exist
os.makedirs(MEDIA_AVA_PATH, exist_ok=True)
os.makedirs(MEDIA_FILES_PATH, exist_ok=True)
os.makedirs(SESSION_PATH, exist_ok=True)
