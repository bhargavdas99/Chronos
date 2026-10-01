# Use a lightweight official Python base image
FROM python:3.11-slim

# Prevent Python from writing .pyc files to disk and ensure logs buffer directly to stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory inside the container
WORKDIR /app

# Install system dependencies required for building C-extensions if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies without caching wheel files inside image
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code into container
COPY . .

# Expose port 8000 for internal Docker network communication
EXPOSE 8000

# Command to run FastAPI app with Uvicorn on container startup
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]