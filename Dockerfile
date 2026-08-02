FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tor && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir flask requests pysocks dissect

COPY . .

# Expose API port
EXPOSE 8080

# Start
CMD ["python3", "server.py", "--port", "8080", "--host", "0.0.0.0"]
