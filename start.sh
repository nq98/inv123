#!/bin/bash
# Production startup script for Replit deployment

# Use PORT environment variable if set, otherwise default to 5000
PORT=${PORT:-5000}

# Start Gunicorn with production settings
# Increased timeout to 300s (5 minutes) for long-running AI processing
exec gunicorn \
  --bind "0.0.0.0:$PORT" \
  --workers 2 \
  --worker-class gevent \
  --worker-connections 1000 \
  --timeout 300 \
  --graceful-timeout 300 \
  --keep-alive 75 \
  --access-logfile - \
  --error-logfile - \
  app:app
