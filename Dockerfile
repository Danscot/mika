FROM python:3.12-slim

WORKDIR /usr/src/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m appuser

# Copy files first
COPY . .

# Change ownership so appuser can write to this folder
RUN chown -R appuser:appuser /usr/src/app

USER appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ENV TELEGRAM=""
ENV AI=""
ENV PYTHONUNBUFFERED=1

CMD ["python", "./bot.py"]
