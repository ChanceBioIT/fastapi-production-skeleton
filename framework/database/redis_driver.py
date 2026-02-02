import redis.asyncio as redis
from .base import BaseDatabaseDriver

class RedisDriver(BaseDatabaseDriver):
    def __init__(self, url: str):
        self.url = url
        self.client = None

    async def connect(self):
        self.client = redis.from_url(self.url, decode_responses=True)

    async def disconnect(self):
        if self.client:
            await self.client.close()

    def get_client(self):
        return self.client
