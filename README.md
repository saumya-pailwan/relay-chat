# RelayChat - Scalable Real-Time Messaging Backend

## Overview

RelayChat is a real-time messaging system, it can handle thousands of concurrent WebSocket connections with low latency and high availability.

## Architecture

### Core Components

1. **FastAPI Backend**: Handles HTTP REST APIs and WebSocket connections
2. **Redis Pub/Sub**: Cross-pod message broadcasting for horizontal scaling
3. **MongoDB**: Persistent message storage
4. **WebSocket Manager**: Manages active connections per pod

### Message Flow

```
[Sender] -> (WebSocket) -> [Backend Pod] -> [MongoDB] (Persist)
                                 |
                                 v
                          [Redis Pub/Sub]
                                 |
                   (Broadcast to all instances)
                                 |
                                 v
                        [All Backend Pods]
                                 |
                                 v
                            (WebSocket)
                                 |
                                 v
                        [Recipient Clients]
```


## Features

### Implemented (Phase 1)
- JWT-based authentication
- Real-time messaging via WebSockets
- Private and group chat rooms
- Message persistence (MongoDB)
- Horizontal scalability (Redis Pub/Sub)
- Connection management
- Message history
- Basic React UI

## Tech Stack

**Backend**
- FastAPI (Python)
- WebSockets
- Redis (Pub/Sub)
- MongoDB (async with Motor)
- JWT authentication

**Frontend**
- React 19
- Tailwind CSS
- Shadcn UI components
- Native WebSocket API

**Infrastructure**
- Docker Compose (local testing)
- Kubernetes-ready architecture

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- Redis
- MongoDB

### Local Development

1. **Start Redis & MongoDB**:
```bash
# Start Redis (required for WebSocket pub/sub)
./scripts/start-redis.sh

# Or use Docker Compose
docker-compose up redis mongodb -d
```

2. **Backend**:
```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8001
```

3. **Frontend**:
```bash
cd frontend
yarn install
yarn start
```

**Important:** Redis must be running before starting the backend. If you see "Authentication failed" errors, check that Redis is running with `redis-cli ping`.

### Full Stack with Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop all services
docker-compose down
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Create account
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Get current user

### Rooms
- `POST /api/rooms` - Create room
- `GET /api/rooms` - List user's rooms
- `GET /api/rooms/{room_id}/messages` - Get room message history

### WebSocket
- `WS /api/ws?token={jwt}` - WebSocket connection

#### WebSocket Actions:
```json
{"action": "join_room", "room_id": "xxx"}

{"action": "send_message", "room_id": "xxx", "content": "Hello!"}
```

## Scaling Strategy

### Horizontal Scaling

1. **Stateless Backend**: No shared memory between pods
2. **Redis Pub/Sub**: Synchronizes messages across all instances
3. **Kubernetes Ready**: Deploy multiple replicas
4. **Load Balancer**: WebSocket-aware routing (sticky sessions not required)

### Performance Targets

- 5K+ concurrent WebSocket connections per pod
- <100ms message delivery latency
- Horizontal scaling via pod replication

### Example Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: relaychat-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: relaychat
  template:
    spec:
      containers:
      - name: backend
        image: relaychat:latest
        ports:
        - containerPort: 8001
        env:
        - name: REDIS_URL
          value: "redis://redis-service:6379"
        - name: MONGO_URL
          value: "mongodb://mongo-service:27017"
```

## Testing

### Backend Tests
```bash
cd backend
pytest
```

### Load Testing (WebSockets)
```bash
# Install artillery
npm install -g artillery

# Run WebSocket load test
arsenal run tests/load-test.yml
```

## Environment Variables

### Backend (.env)
```
MONGO_URL=mongodb://localhost:27017
DB_NAME=test_database
REDIS_URL=redis://localhost:6379
JWT_SECRET_KEY=your-secret-key-change-in-production
CORS_ORIGINS=*
```

### Frontend (.env)
```
REACT_APP_BACKEND_URL=http://localhost:8001
```

## Security

- JWT token-based authentication
- WebSocket connections validated with JWT
- Password hashing with bcrypt
- Room access control (membership verification)
- CORS configuration

## Monitoring

### Logs
```bash
# Backend logs
tail -f /var/log/supervisor/backend.*.log

# Docker logs
docker-compose logs -f backend
```

### Metrics
- Active WebSocket connections
- Redis Pub/Sub latency
- MongoDB write performance
- Message delivery time
- Pod CPU/Memory usage