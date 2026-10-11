# Single image: builds the frontend and serves it from the FastAPI backend (one URL for the QR code).
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG VITE_PUBLIC_URL=""
ENV VITE_PUBLIC_URL=$VITE_PUBLIC_URL
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY fixtures/ fixtures/
COPY cache/ cache/
COPY --from=web /web/dist frontend/dist
ENV DEMO_OFFLINE=true PORT=8000
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
