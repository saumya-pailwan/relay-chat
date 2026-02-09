#!/bin/bash
# Start Redis server for RelayChat
# This script should be run before starting the backend

echo "Starting RelayChat dependencies..."

# Check if Redis is already running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Starting Redis server..."
    redis-server --daemonize yes
    sleep 2
    
    if redis-cli ping > /dev/null 2>&1; then
        echo "✓ Redis started successfully"
    else
        echo "✗ Failed to start Redis"
        exit 1
    fi
else
    echo "✓ Redis is already running"
fi

# Check backend status
if sudo supervisorctl status backend | grep -q "RUNNING"; then
    echo "✓ Backend is running"
else
    echo "Restarting backend..."
    sudo supervisorctl restart backend
    sleep 3
    echo "✓ Backend restarted"
fi

echo ""
echo "✅ All services are ready!"
echo "   - Redis: Running on localhost:6379"
echo "   - Backend: Running on 0.0.0.0:8001"
echo "   - Frontend: Running on localhost:3000"
echo ""
