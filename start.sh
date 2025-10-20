#!/bin/bash
set -e

echo "🚀 Starting Discord Voice Bot with WhisperX"
echo "================================================"

# Check for GPU
if command -v nvidia-smi &> /dev/null; then
    echo "🎮 GPU Check:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || echo "⚠️  GPU detected but nvidia-smi failed"
else
    echo "💻 No GPU detected - will use CPU mode"
fi

echo "================================================"
echo ""

# Start WhisperX server in background
python3 /app/whisper-server.py &
WHISPER_PID=$!
echo "✅ Started WhisperX server (PID: $WHISPER_PID)"

# Wait for WhisperX to be ready (check health endpoint)
echo "⏳ Waiting for WhisperX server to be ready (model loading)..."
MAX_WAIT=90
WAITED=0

while [ $WAITED -lt $MAX_WAIT ]; do
    # Check health endpoint on port 4902 - only returns 200 when model is loaded
    if curl -f -s http://localhost:4902/health > /dev/null 2>&1; then
        echo "✅ WhisperX server is ready!"
        break
    fi
    
    sleep 1
    WAITED=$((WAITED + 1))
    
    if [ $((WAITED % 10)) -eq 0 ]; then
        echo "   Still waiting for model to load... (${WAITED}s elapsed)"
    fi
    
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo "❌ WhisperX server failed to start within ${MAX_WAIT} seconds"
        kill $WHISPER_PID 2>/dev/null
        exit 1
    fi
done

# Start Node.js server in background
node /app/server.js &
NODE_PID=$!
echo "✅ Started Node.js server (PID: $NODE_PID)"

echo ""
echo "================================================"
echo "🎙️  Voice bot is ready!"
echo "================================================"

# Wait for either process to exit
wait -n

# If one exits, kill the other
kill $WHISPER_PID $NODE_PID 2>/dev/null

exit $?
