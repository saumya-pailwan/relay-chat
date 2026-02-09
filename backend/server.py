from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from jose import JWTError, jwt
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Set
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import logging
import uuid
import json
import asyncio
import redis.asyncio as redis
import aiofiles
from presence import PresenceManager

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
redis_client = None

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

api_router = APIRouter(prefix="/api")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: str
    username: str
    created_at: datetime

class MessageCreate(BaseModel):
    room_id: str
    content: str
    attachments: List[str] = []

class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    room_id: str
    user_id: str
    username: str
    content: str
    timestamp: datetime
    attachments: List[str] = []

class Room(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    type: str
    members: List[str]
    created_at: datetime

class RoomCreate(BaseModel):
    name: str
    type: str = "group"
    members: List[str] = []

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.room_members: Dict[str, Set[str]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        logger.info(f"User {user_id} connected. Total connections: {sum(len(v) for v in self.active_connections.values())}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"User {user_id} disconnected. Total connections: {sum(len(v) for v in self.active_connections.values())}")

    async def join_room(self, room_id: str, user_id: str):
        if room_id not in self.room_members:
            self.room_members[room_id] = set()
        self.room_members[room_id].add(user_id)

    async def leave_room(self, room_id: str, user_id: str):
        if room_id in self.room_members:
            self.room_members[room_id].discard(user_id)
            if not self.room_members[room_id]:
                del self.room_members[room_id]

    async def send_to_user(self, user_id: str, message: dict):
        if user_id in self.active_connections:
            dead_connections = set()
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending to user {user_id}: {e}")
                    dead_connections.add(connection)
            for conn in dead_connections:
                self.disconnect(conn, user_id)

    async def broadcast_to_room(self, room_id: str, message: dict, exclude_user: Optional[str] = None):
        if room_id in self.room_members:
            for user_id in self.room_members[room_id]:
                if user_id != exclude_user:
                    await self.send_to_user(user_id, message)

manager = ConnectionManager()

class RedisPubSubManager:
    def __init__(self):
        self.pubsub = None
        self.redis_client = None

    async def connect(self):
        self.redis_client = await redis.from_url(redis_url, decode_responses=True)
        self.pubsub = self.redis_client.pubsub()
        logger.info("Connected to Redis")

    async def subscribe(self, channel: str):
        await self.pubsub.subscribe(channel)
        logger.info(f"Subscribed to channel: {channel}")

    async def publish(self, channel: str, message: dict):
        await self.redis_client.publish(channel, json.dumps(message))

    async def listen(self):
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await self.handle_message(data)
                except Exception as e:
                    logger.error(f"Error handling Redis message: {e}")

    async def handle_message(self, data: dict):
        message_type = data.get("type")
        logger.info(f"Redis message received: type={message_type}, data={data.get('content', data.get('username', ''))[:30]}")
        if message_type == "chat_message":
            room_id = data.get("room_id")
            sender_id = data.get("user_id")
            await manager.broadcast_to_room(room_id, data, exclude_user=sender_id)
            logger.info(f"Broadcast to room {room_id}, excluding sender {sender_id}")
        elif message_type == "user_joined":
            room_id = data.get("room_id")
            user_id = data.get("user_id")
            username = data.get("username")
            await manager.broadcast_to_room(room_id, {
                "type": "user_joined",
                "user_id": user_id,
                "username": username,
                "message": f"{username} joined the room"
            })

    async def disconnect(self):
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()

redis_manager = RedisPubSubManager()
presence_manager = PresenceManager(redis_url)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if user is None:
        raise credentials_exception
    return User(**user)

async def verify_ws_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        return user
    except JWTError:
        return None

@api_router.post("/auth/register", response_model=Token)
async def register(user_data: UserRegister):
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(user_data.password)
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "username": user_data.username,
        "password": hashed_password,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user_doc)
    
    access_token = create_access_token(
        data={"sub": user_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user={"id": user_id, "email": user_data.email, "username": user_data.username}
    )

@api_router.post("/auth/login", response_model=Token)
async def login(user_data: UserLogin):
    user = await db.users.find_one({"email": user_data.email})
    if not user or not verify_password(user_data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    access_token = create_access_token(
        data={"sub": user["id"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user={"id": user["id"], "email": user["email"], "username": user["username"]}
    )

@api_router.get("/auth/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@api_router.post("/rooms", response_model=Room)
async def create_room(room_data: RoomCreate, current_user: User = Depends(get_current_user)):
    room_id = str(uuid.uuid4())
    members = list(set([current_user.id] + room_data.members))
    
    room_doc = {
        "id": room_id,
        "name": room_data.name,
        "type": room_data.type,
        "members": members,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.id
    }
    await db.rooms.insert_one(room_doc)
    
    room_doc["created_at"] = datetime.fromisoformat(room_doc["created_at"])
    return Room(**{k: v for k, v in room_doc.items() if k != "_id"})

@api_router.get("/rooms", response_model=List[Room])
async def get_rooms(current_user: User = Depends(get_current_user)):
    rooms = await db.rooms.find(
        {"members": current_user.id},
        {"_id": 0}
    ).to_list(1000)
    
    for room in rooms:
        if isinstance(room["created_at"], str):
            room["created_at"] = datetime.fromisoformat(room["created_at"])
    
    return rooms

@api_router.get("/rooms/{room_id}/messages", response_model=List[Message])
async def get_room_messages(
    room_id: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    room = await db.rooms.find_one({"id": room_id, "members": current_user.id})
    if not room:
        raise HTTPException(status_code=403, detail="Access denied")
    
    messages = await db.messages.find(
        {"room_id": room_id},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    
    messages.reverse()
    
    for msg in messages:
        if isinstance(msg["timestamp"], str):
            msg["timestamp"] = datetime.fromisoformat(msg["timestamp"])
    
    return messages

@api_router.get("/rooms/discover/all", response_model=List[Room])
async def discover_rooms(current_user: User = Depends(get_current_user)):
    return []

@api_router.post("/rooms/{room_id}/join")
async def join_room(room_id: str, current_user: User = Depends(get_current_user)):
    room = await db.rooms.find_one({"id": room_id})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    if current_user.id in room.get("members", []):
        return {"message": "Already a member", "room_id": room_id}
    
    await db.rooms.update_one(
        {"id": room_id},
        {"$addToSet": {"members": current_user.id}}
    )
    
    return {"message": "Joined successfully", "room_id": room_id}

@api_router.post("/rooms/{room_id}/members/add")
async def add_member_to_room(
    room_id: str,
    user_email: str,
    current_user: User = Depends(get_current_user)
):
    room = await db.rooms.find_one({"id": room_id, "members": current_user.id})
    if not room:
        raise HTTPException(status_code=403, detail="Access denied")
    
    user_to_add = await db.users.find_one({"email": user_email})
    if not user_to_add:
        raise HTTPException(status_code=404, detail="User not found")
    
    await db.rooms.update_one(
        {"id": room_id},
        {"$addToSet": {"members": user_to_add["id"]}}
    )
    
    return {
        "message": f"{user_to_add['username']} added to room",
        "user_id": user_to_add["id"],
        "username": user_to_add["username"]
    }

@api_router.post("/rooms/direct")
async def create_or_get_direct_message(
    identifier: str,
    current_user: User = Depends(get_current_user)
):
    other_user = await db.users.find_one({"email": identifier})
    if not other_user:
        other_user = await db.users.find_one({"username": identifier})
    
    if not other_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if other_user["id"] == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot DM yourself")
    
    existing_dm = await db.rooms.find_one({
        "type": "private",
        "members": {"$all": [current_user.id, other_user["id"]], "$size": 2}
    })
    
    if existing_dm:
        existing_dm["created_at"] = datetime.fromisoformat(existing_dm["created_at"]) if isinstance(existing_dm["created_at"], str) else existing_dm["created_at"]
        return Room(**{k: v for k, v in existing_dm.items() if k != "_id"})
    
    room_id = str(uuid.uuid4())
    room_doc = {
        "id": room_id,
        "name": f"DM: {current_user.username} & {other_user['username']}",
        "type": "private",
        "members": [current_user.id, other_user["id"]],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.id
    }
    await db.rooms.insert_one(room_doc)
    
    room_doc["created_at"] = datetime.fromisoformat(room_doc["created_at"])
    return Room(**{k: v for k, v in room_doc.items() if k != "_id"})

@api_router.get("/users/search")
async def search_users(q: str, current_user: User = Depends(get_current_user)):
    if len(q) < 2:
        return []
    
    users = await db.users.find(
        {
            "$or": [
                {"username": {"$regex": q, "$options": "i"}},
                {"email": {"$regex": q, "$options": "i"}}
            ]
        },
        {"_id": 0, "password": 0}
    ).limit(20).to_list(20)
    
    return users

@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    filename = f"{file_id}{ext}"
    file_path = ROOT_DIR / "static" / "uploads" / filename
    
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
        
    return {"url": f"/static/uploads/{filename}", "filename": file.filename}

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    user = await verify_ws_token(token)
    if not user:
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    user_id = user["id"]
    username = user["username"]
    await manager.connect(websocket, user_id)
    
    await presence_manager.user_online(user_id, username)
    
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "join_room":
                room_id = data.get("room_id")
                room = await db.rooms.find_one({"id": room_id, "members": user_id})
                if room:
                    await manager.join_room(room_id, user_id)
                    await presence_manager.user_join_room(room_id, user_id)
                    
                    online_users = await presence_manager.get_room_online_users(room_id)
                    online_usernames = {}
                    all_online = await presence_manager.get_online_users()
                    for uid in online_users:
                        if uid in all_online:
                            online_usernames[uid] = all_online[uid]
                    
                    await websocket.send_json({
                        "type": "system",
                        "message": f"Joined room: {room['name']}"
                    })
                    
                    await websocket.send_json({
                        "type": "presence_update",
                        "room_id": room_id,
                        "online_users": online_usernames
                    })
                    
                    await redis_manager.publish("chat_messages", {
                        "type": "user_joined",
                        "room_id": room_id,
                        "user_id": user_id,
                        "username": username
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Access denied to room"
                    })
            
            elif action == "send_message":
                room_id = data.get("room_id")
                content = data.get("content")
                attachments = data.get("attachments", [])
                
                logger.info(f"User {user_id} sending message to room {room_id}: {content[:50]}")
                
                room = await db.rooms.find_one({"id": room_id, "members": user_id})
                if not room:
                    logger.warning(f"User {user_id} access denied to room {room_id}")
                    await websocket.send_json({"type": "error", "message": "Access denied"})
                    continue
                
                message_id = str(uuid.uuid4())
                timestamp = datetime.now(timezone.utc)
                message_doc = {
                    "id": message_id,
                    "room_id": room_id,
                    "user_id": user_id,
                    "username": username,
                    "content": content,
                    "timestamp": timestamp.isoformat(),
                    "attachments": attachments
                }
                await db.messages.insert_one(message_doc)
                logger.info(f"Message {message_id} saved to MongoDB")
                
                redis_message = {
                    "type": "chat_message",
                    "id": message_id,
                    "room_id": room_id,
                    "user_id": user_id,
                    "username": username,
                    "content": content,
                    "timestamp": timestamp.isoformat(),
                    "attachments": attachments
                }
                await redis_manager.publish("chat_messages", redis_message)
                logger.info(f"Message {message_id} published to Redis")
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
        await presence_manager.user_offline(user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        manager.disconnect(websocket, user_id)
        await presence_manager.user_offline(user_id)

@api_router.get("/")
async def root():
    return {"message": "RelayChat API"}

@api_router.get("/health")
async def health():
    return {"status": "healthy"}

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await redis_manager.connect()
    await redis_manager.subscribe("chat_messages")
    await presence_manager.connect()
    asyncio.create_task(redis_manager.listen())
    logger.info("RelayChat backend started with presence tracking")

@app.on_event("shutdown")
async def shutdown():
    client.close()
    await redis_manager.disconnect()
    await presence_manager.disconnect()
    logger.info("RelayChat backend shutdown")
