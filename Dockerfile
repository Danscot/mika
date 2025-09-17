FROM python:3.12-slim

WORKDIR /usr/src/app

# Install system dependencies (for FAISS, numpy, etc.)
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m appuser
USER appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TELEGRAM=""
ENV AI=""
ENV PYTHONUNBUFFERED=1

CMD ["python", "./bot.py"]
