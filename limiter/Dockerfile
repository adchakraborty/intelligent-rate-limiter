FROM python:3.11-slim

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Create log directory (consistent with backend)
RUN mkdir -p /var/log/limiter && chmod 755 /var/log/limiter

EXPOSE 8080
ENV PORT=8080

# Add health check at Docker level
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "app.py"]