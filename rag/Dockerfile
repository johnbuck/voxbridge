# VoxBridge RAG Service
# Hybrid retrieval with vector search, BM25, and knowledge graphs

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies for unstructured and document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build tools
    build-essential \
    # PDF processing (poppler)
    poppler-utils \
    # OCR (tesseract)
    tesseract-ocr \
    tesseract-ocr-eng \
    # Image processing
    libmagic1 \
    libgl1 \
    libglib2.0-0 \
    # Document processing
    pandoc \
    # Network tools
    curl \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create non-root user for security
RUN useradd -m -u 1000 raguser && chown -R raguser:raguser /app
USER raguser

# Expose port
EXPOSE 4910

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:4910/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "4910"]
