# PROJECT-ALPHA V2 Production Dockerfile
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PORT=5001

WORKDIR /app

# Install system runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends     curl     && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip &&     pip install --no-cache-dir -r requirements.txt

# Copy V2 application code and necessary runtime assets
COPY v2/ ./v2/
COPY docs/ ./docs/

# Ensure persistent SQLite data directory exists
RUN mkdir -p /app/v2/data

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3     CMD curl -f http://localhost:/health || exit 1

CMD ["sh", "-c", "uvicorn v2.app_v2:app --host 0.0.0.0 --port "]
