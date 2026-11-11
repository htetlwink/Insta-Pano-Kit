# Use official lightweight Python image
FROM python:3.12-slim

# Avoid buffering and bytecode
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies including FFmpeg for video panning
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    liblcms2-2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . /app/

# Render sets PORT environment variable dynamically
ENV PORT=8080
EXPOSE 8080

# Run production Gunicorn server with 1 worker optimized for Render's 512MB memory limit
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 180 --max-requests 50 --max-requests-jitter 10 web_app:app
