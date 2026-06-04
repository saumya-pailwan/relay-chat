import redis.asyncio as redis
from typing import Set, Dict
import logging

logger = logging.getLogger(__name__)

class PresenceManager:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client = None
        self.online_users_by_room: Dict[str, Set[str]] = {}
    
    async def connect(self):
        self.redis_client = await redis.from_url(self.redis_url, decode_responses=True)
        logger.info("PresenceManager connected to Redis")
    
    async def user_online(self, user_id: str, username: str):
        await self.redis_client.hset("presence:users", user_id, username)
        await self.redis_client.incr(f"presence:connections:{user_id}")
        logger.info(f"User {username} ({user_id}) is now online")

    async def user_offline(self, user_id: str):
        count = await self.redis_client.decr(f"presence:connections:{user_id}")
        if count <= 0:
            await self.redis_client.hdel("presence:users", user_id)
            await self.redis_client.delete(f"presence:connections:{user_id}")
        logger.info(f"User {user_id} disconnected (remaining connections: {max(count, 0)})")
    
    async def get_online_users(self) -> Dict[str, str]:
        return await self.redis_client.hgetall("presence:users")
    
    async def user_join_room(self, room_id: str, user_id: str):
        if room_id not in self.online_users_by_room:
            self.online_users_by_room[room_id] = set()
        self.online_users_by_room[room_id].add(user_id)
        await self.redis_client.sadd(f"presence:room:{room_id}", user_id)
        logger.info(f"User {user_id} joined room {room_id}")
    
    async def user_leave_room(self, room_id: str, user_id: str):
        if room_id in self.online_users_by_room:
            self.online_users_by_room[room_id].discard(user_id)
        await self.redis_client.srem(f"presence:room:{room_id}", user_id)
        logger.info(f"User {user_id} left room {room_id}")
    
    async def get_room_online_users(self, room_id: str) -> Set[str]:
        members = await self.redis_client.smembers(f"presence:room:{room_id}")
        return members if members else set()
    
    async def disconnect(self):
        if self.redis_client:
            await self.redis_client.close()
            logger.info("PresenceManager disconnected from Redis")
