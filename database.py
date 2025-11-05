import mysql.connector
from mysql.connector import Error, pooling
import config
import logging
import time
from cache import SimpleCache

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.connection_pool = None
        self.cache = SimpleCache(ttl=config.CACHE_TTL) if config.ENABLE_CACHE else None
        self.init_pool()
    
    def init_pool(self):
        """Initialize connection pool"""
        try:
            self.connection_pool = pooling.MySQLConnectionPool(
                pool_name="tgdc_pool",
                pool_size=10,  # Increased pool size
                pool_reset_session=True,
                host=config.MYSQL_HOST,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                database=config.MYSQL_DATABASE,
                autocommit=True,
                connection_timeout=10
            )
            logger.info("✅ MySQL connection pool created")
        except Error as e:
            logger.error(f"❌ Error creating connection pool: {e}")
            raise
    
    def get_connection(self):
        """Get connection from pool with retry"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return self.connection_pool.get_connection()
            except Error as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                else:
                    raise
    
    def get_webhook(self, group_id, topic_id=0):
        """Get webhook URL for specific group and topic (with cache)"""
        cache_key = f"webhook_{group_id}_{topic_id}"
        
        # Try cache first
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            # Try exact match first
            query = "SELECT webhook_url FROM tg_dc_webhook WHERE group_id = %s AND topic_id = %s"
            cursor.execute(query, (group_id, topic_id))
            result = cursor.fetchone()
            
            # If not found and topic_id is not 0, try wildcard
            if not result and topic_id != 0:
                query = "SELECT webhook_url FROM tg_dc_webhook WHERE group_id = %s AND topic_id = -1"
                cursor.execute(query, (group_id,))
                result = cursor.fetchone()
            
            cursor.close()
            
            webhook_url = result['webhook_url'] if result else None
            
            # Cache the result (even if None)
            if self.cache:
                self.cache.set(cache_key, webhook_url)
            
            return webhook_url
            
        except Error as e:
            logger.error(f"❌ Error fetching webhook: {e}")
            return None
        finally:
            if connection and connection.is_connected():
                connection.close()
    
    def get_all_groups(self):
        """Get all unique group IDs from database (with cache)"""
        cache_key = "all_groups"
        
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached
        
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor()
            query = "SELECT DISTINCT group_id FROM tg_dc_webhook"
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            
            groups = [row[0] for row in results]
            
            if self.cache:
                self.cache.set(cache_key, groups)
            
            return groups
        except Error as e:
            logger.error(f"❌ Error fetching groups: {e}")
            return []
        finally:
            if connection and connection.is_connected():
                connection.close()
    
    def get_all_webhooks_for_group(self, group_id):
        """Get all webhooks for a specific group"""
        connection = None
        try:
            connection = self.get_connection()
            cursor = connection.cursor(dictionary=True)
            query = "SELECT topic_id, webhook_url FROM tg_dc_webhook WHERE group_id = %s"
            cursor.execute(query, (group_id,))
            results = cursor.fetchall()
            cursor.close()
            return results
        except Error as e:
            logger.error(f"❌ Error fetching webhooks: {e}")
            return []
        finally:
            if connection and connection.is_connected():
                connection.close()
    
    def close(self):
        """Close connection pool"""
        try:
            if self.connection_pool:
                logger.info("❌ Closing MySQL connection pool")
            if self.cache:
                self.cache.clear()
        except Exception as e:
            logger.error(f"Error closing pool: {e}")
