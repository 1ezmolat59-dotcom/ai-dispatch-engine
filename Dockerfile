# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts

COPY frontend/ ./
RUN node build.mjs


# ── Stage 2: Python runtime ────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY main.py .
COPY mock_fsm.py .
COPY ai_dispatch/ ./ai_dispatch/

# Copy built frontend from stage 1
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# Create data directory for ML seed data
RUN mkdir -p ai_dispatch/data

# Use PORT env var (Railway/Render set this automatically), default 8000
ENV PORT=8000
EXPOSE 8000

COPY start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
