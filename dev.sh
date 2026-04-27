#!/bin/bash

# TradeCraft Development Server Script
# Stops existing processes and starts both frontend and backend

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Port numbers
BACKEND_PORT=8000
FRONTEND_PORT=5173

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  TradeCraft Development Server${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Function to kill process on a port
kill_port() {
    local port=$1
    local service_name=$2

    if lsof -ti:$port > /dev/null 2>&1; then
        echo -e "${YELLOW}Stopping $service_name on port $port...${NC}"
        lsof -ti:$port | xargs kill -9 2>/dev/null || true
        sleep 1
        echo -e "${GREEN}✓ $service_name stopped${NC}"
    else
        echo -e "${GREEN}✓ No $service_name running${NC}"
    fi
}

# Kill existing processes
echo -e "${YELLOW}Checking for existing processes...${NC}"
kill_port $BACKEND_PORT "backend"
kill_port $FRONTEND_PORT "frontend"
echo ""

# Store PIDs for cleanup
BACKEND_PID=""
FRONTEND_PID=""

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down servers...${NC}"
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}✓ Servers stopped${NC}"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Start backend
echo -e "${BLUE}Starting backend server...${NC}"
cd "$SCRIPT_DIR/backend"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies if needed
if [ ! -f "venv/lib/python*/site-packages/fastapi" ] 2>/dev/null; then
    echo -e "${YELLOW}Installing backend dependencies...${NC}"
    pip install -r requirements.txt -q
fi

# Start backend in background
uvicorn app.main:app --reload --port $BACKEND_PORT > /dev/null 2>&1 &
BACKEND_PID=$!
echo -e "${GREEN}✓ Backend started on http://localhost:$BACKEND_PORT${NC}"

# Give backend time to start
sleep 2

# Start frontend
echo -e "${BLUE}Starting frontend server...${NC}"
cd "$SCRIPT_DIR/frontend"

# Check node_modules
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies...${NC}"
    npm install
fi

# Start frontend in background
npm run dev -- --force > /dev/null 2>&1 &
FRONTEND_PID=$!
echo -e "${GREEN}✓ Frontend started on http://localhost:$FRONTEND_PORT${NC}"

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  All servers running!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BLUE}Frontend:${NC} http://localhost:$FRONTEND_PORT"
echo -e "  ${BLUE}Backend:${NC}  http://localhost:$BACKEND_PORT"
echo -e "  ${BLUE}API Docs:${NC}  http://localhost:$BACKEND_PORT/docs"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all servers${NC}"
echo ""

# Wait for processes
wait