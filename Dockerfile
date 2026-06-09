FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Create dirs for persistent data
RUN mkdir -p /app/reports /app/data

# Unbuffered Python output for Docker logs
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV TZ=US/Eastern

# Default: hourly mode
CMD ["python", "-u", "main.py", "--mode", "hourly"]
