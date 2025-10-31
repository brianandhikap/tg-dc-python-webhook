import mysql.connector
from mysql.connector import Error
import config

class Database:
    def __init__(self):
        self.connection = None
        self.connect()
    
    def connect(self):
        try:
            self.connection = mysql.connector.connect(
                host=config.MYSQL_HOST,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                database=config.MYSQL_DATABASE
            )
            if self.connection.is_connected():
                print("✅ Connected to MySQL database")
        except Error as e:
            print(f"❌ Error connecting to MySQL: {e}")
    
    def get_webhook(self, group_id, topic_id=0):
        """Get webhook URL for specific group and topic"""
        try:
            cursor = self.connection.cursor(dictionary=True)
            query = "SELECT webhook_url FROM tg_dc_webhook WHERE group_id = %s AND topic_id = %s"
            cursor.execute(query, (group_id, topic_id))
            result = cursor.fetchone()
            cursor.close()
            return result['webhook_url'] if result else None
        except Error as e:
            print(f"❌ Error fetching webhook: {e}")
            return None
    
    def get_all_groups(self):
        """Get all unique group IDs from database"""
        try:
            cursor = self.connection.cursor()
            query = "SELECT DISTINCT group_id FROM tg_dc_webhook"
            cursor.execute(query)
            results = cursor.fetchall()
            cursor.close()
            return [row[0] for row in results]
        except Error as e:
            print(f"❌ Error fetching groups: {e}")
            return []

    def get_all_webhooks_for_group(self, group_id):
        """Get all webhooks for a specific group (any topic)"""
        try:
            cursor = self.connection.cursor(dictionary=True)
            query = "SELECT topic_id, webhook_url FROM tg_dc_webhook WHERE group_id = %s"
            cursor.execute(query, (group_id,))
            results = cursor.fetchall()
            cursor.close()
            return results
        except Error as e:
            print(f"❌ Error fetching webhooks: {e}")
            return []

    def get_webhook(self, group_id, topic_id=0):
        """Get webhook URL for specific group and topic"""
        try:
            cursor = self.connection.cursor(dictionary=True)
            query = "SELECT webhook_url FROM tg_dc_webhook WHERE group_id = %s AND topic_id = %s"
            cursor.execute(query, (group_id, topic_id))
            result = cursor.fetchone()
            cursor.close()
            return result['webhook_url'] if result else None
        except Error as e:
            print(f"❌ Error fetching webhook: {e}")
            return None
        
    def close(self):
        if self.connection and self.connection.is_connected():
            self.connection.close()
            print("❌ MySQL connection closed")
