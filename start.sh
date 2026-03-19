#!/bin/sh
# Startup script for Railway / Render / Docker
# Logs the port being used and ensures clean startup

echo "=== AI Dispatch Engine ==="
echo "PORT=${PORT:-8000}"
echo "ENVIRONMENT=${ENVIRONMENT:-development}"
echo "Python: $(python --version)"
echo "Working dir: $(pwd)"
echo "=========================="

exec uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --log-level info \
  --no-access-log
