#!/bin/bash

# Askesis Development Runner
# Starts both backend and frontend for local development

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting Askesis in development mode...${NC}"

# Create .env from example if it doesn't exist
if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo -e "${GREEN}Creating .env from .env.example (DEV_MODE=true)...${NC}"
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
fi

# Check if we need to set up backend
if [ ! -d "$BACKEND_DIR/venv" ]; then
    echo -e "${GREEN}Setting up backend virtual environment...${NC}"
    cd "$BACKEND_DIR"
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    cd "$BACKEND_DIR"
    source venv/bin/activate
fi

# Run database migrations
echo -e "${GREEN}Running database migrations...${NC}"
cd "$BACKEND_DIR"
alembic upgrade head

# Check if we need to install frontend deps
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo -e "${GREEN}Installing frontend dependencies...${NC}"
    cd "$FRONTEND_DIR"
    npm install
fi

# Function to cleanup on exit
cleanup() {
    echo -e "\n${BLUE}Shutting down...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start backend
echo -e "${GREEN}Starting backend on http://localhost:8000${NC}"
cd "$BACKEND_DIR"
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to start
sleep 2

# Start frontend
echo -e "${GREEN}Starting frontend on http://localhost:5173${NC}"
cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!

echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}Askesis is running!${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Frontend: ${GREEN}http://localhost:5173${NC}"
echo -e "Backend:  ${GREEN}http://localhost:8000${NC}"
echo -e "API Docs: ${GREEN}http://localhost:8000/docs${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Press Ctrl+C to stop\n"

# Wait for both processes
wait
