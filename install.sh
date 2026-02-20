#!/bin/bash
set -e

echo "========================================"
echo "  AI Manus - Auto Install Dependencies"
echo "========================================"

echo ""
echo "[1/4] Installing Backend Python dependencies..."
cd /home/runner/workspace/backend
pip install -q -r requirements.txt
echo "  Backend dependencies installed."

echo ""
echo "[2/4] Installing Sandbox Python dependencies..."
cd /home/runner/workspace/sandbox
pip install -q -r requirements.txt
echo "  Sandbox dependencies installed."

echo ""
echo "[3/4] Installing Frontend Node.js dependencies..."
cd /home/runner/workspace/frontend
npm install --legacy-peer-deps
echo "  Frontend dependencies installed."

echo ""
echo "[4/4] Verifying installations..."
cd /home/runner/workspace

echo "  - Python: $(python3 --version)"
echo "  - Node.js: $(node --version)"
echo "  - npm: $(npm --version)"
echo "  - MongoDB: $(mongod --version 2>&1 | head -1)"
echo "  - Redis: $(redis-server --version | head -1)"

python3 -c "import fastapi; print(f'  - FastAPI: {fastapi.__version__}')" 2>/dev/null || echo "  - FastAPI: NOT INSTALLED"
python3 -c "import openai; print(f'  - OpenAI: {openai.__version__}')" 2>/dev/null || echo "  - OpenAI: NOT INSTALLED"
python3 -c "import motor; print(f'  - Motor: {motor.version}')" 2>/dev/null || echo "  - Motor: NOT INSTALLED"

echo ""
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "To start the application, run: bash start.sh"
