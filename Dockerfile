FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    git-lfs \
    && rm -rf /var/lib/apt/lists/*

# Initialize Git LFS
RUN git lfs install

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create directories for data
RUN mkdir -p /app/papers

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Use shell as entrypoint instead of directly running the script
ENTRYPOINT ["/bin/bash"]
