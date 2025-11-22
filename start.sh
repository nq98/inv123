#!/bin/bash
# Production startup script for Replit deployment

# Use PORT environment variable if set, otherwise default to 5000
PORT=${PORT:-5000}

# Start Gunicorn with production settings
exec gunicorn \
  --bind "0.0.0.0:$PORT" \
  --workers 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  app:app
