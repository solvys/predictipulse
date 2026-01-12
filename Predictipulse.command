#!/bin/bash
# PREDICTiPULSE Launcher
# Double-click this file to start PREDICTiPULSE

cd "$(dirname "$0")"

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                   PREDICTiPULSE                           ║"
echo "║              Starting Trading Engine...                   ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 first."
    echo "   Visit: https://www.python.org/downloads/"
    read -p "Press Enter to exit..."
    exit 1
fi

# Check if requirements are installed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "📦 Installing required packages..."
    pip3 install -r requirements.txt
fi

# Kill any existing process on port 3000
lsof -ti:3000 | xargs kill -9 2>/dev/null

echo "🚀 Starting PREDICTiPULSE server..."
echo ""

# Start the Flask server in background
python3 app.py &
SERVER_PID=$!

# Wait for server to start
sleep 2

# Check if server started successfully
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "❌ Failed to start server. Check the logs above."
    read -p "Press Enter to exit..."
    exit 1
fi

echo "✅ PREDICTiPULSE is running at: http://localhost:3000"
echo ""
echo "Opening in your default browser..."

# Open in default browser
open "http://localhost:3000"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  PREDICTiPULSE is running. Press Ctrl+C to stop.         "
echo "═══════════════════════════════════════════════════════════"
echo ""

# Wait for user to stop
wait $SERVER_PID
