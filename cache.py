import time
from threading import Lock

class SimpleCache:
    def __init__(self, ttl=300):
        self.cache = {}
        self.ttl = ttl
        self.lock = Lock()
    
    def get(self, key):
        with self.lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    return value
                else:
                    del self.cache[key]
            return None
    
    def set(self, key, value):
        with self.lock:
            self.cache[key] = (value, time.time())
    
    def clear(self):
        with self.lock:
            self.cache.clear()
    
    def delete(self, key):
        with self.lock:
            if key in self.cache:
                del self.cache[key]
