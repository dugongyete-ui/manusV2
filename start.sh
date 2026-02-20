#!/bin/bash
set -e

mkdir -p /tmp/mongodb_data /tmp/redis_data /tmp/logs

pkill -f mongod 2>/dev/null || true
pkill -f redis-server 2>/dev/null || true
pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1

echo "=== Starting MongoDB ==="
mongod --dbpath /tmp/mongodb_data --bind_ip 127.0.0.1 --port 27017 --fork --logpath /tmp/logs/mongodb.log --noauth

echo "=== Starting Redis ==="
redis-server --daemonize yes --dir /tmp/redis_data --bind 127.0.0.1 --port 6379 --logfile /tmp/logs/redis.log

sleep 2

echo "=== Checking Redis ==="
redis-cli ping && echo "Redis OK"

echo "=== Checking Dependencies ==="
if [ ! -d "/home/runner/workspace/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  cd /home/runner/workspace/frontend && npm install --legacy-peer-deps --silent
fi

pip show fastapi > /dev/null 2>&1 || {
  echo "Installing backend dependencies..."
  cd /home/runner/workspace/backend && pip install -q -r requirements.txt
}

pip show email-validator > /dev/null 2>&1 || {
  echo "Installing sandbox dependencies..."
  cd /home/runner/workspace/sandbox && pip install -q -r requirements.txt
}

echo "=== Starting Sandbox (port 8080) ==="
cd /home/runner/workspace/sandbox
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --log-level info > /tmp/logs/sandbox.log 2>&1 &

sleep 1

echo "=== Starting Backend (port 8000) ==="
cd /home/runner/workspace/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info > /tmp/logs/backend.log 2>&1 &

sleep 2

echo "=== Checking Backend ==="
for i in {1..10}; do
  if curl -s http://127.0.0.1:8000/api/v1/auth/status > /dev/null 2>&1; then
    echo "Backend is ready!"
    break
  fi
  echo "Waiting for backend... ($i/10)"
  sleep 1
done

echo "=== Starting Frontend (port 5000) ==="
cd /home/runner/workspace/frontend
exec npx --yes vite --host 0.0.0.0 --port 5000
