# Discord Bot
# Connects to separate WhisperX container for STT

FROM node:18-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsodium23 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js dependencies
COPY package*.json ./
RUN npm install --omit=dev --ignore-scripts && \
    npm cache clean --force

# Copy application code
COPY server.js .
COPY whisper-client.js .

# Create non-root user with different UID to avoid conflict
RUN adduser --disabled-password --gecos '' --uid 1001 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 4900

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:4900/health || exit 1

# Run Discord bot
CMD ["node", "/app/server.js"]
