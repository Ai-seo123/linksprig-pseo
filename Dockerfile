# Stage 1: Build the React frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
# Build frontend (Vite environment detects production and uses relative paths)
ENV VITE_API_URL=""
RUN npm run build

# Stage 2: Combine with Python FastAPI backend
FROM python:3.10-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY backend/ ./backend

# Copy the automation scripts that the backend runs in background tasks
COPY import_html_posts.py ai_writer.py generate_blogs_from_excel.py generator.py internal_linker.py push_csv_to_wp.py qa_validator.py ./
COPY database/ ./database
COPY wp-import/ ./wp-import

# Copy built frontend assets from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose port and start FastAPI application
EXPOSE 10000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "10000"]
