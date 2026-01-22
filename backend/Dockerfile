FROM python:3.11-slim

# Update system packages to latest versions for security
# Install build dependencies for asyncpg
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y build-essential libpq-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN groupadd -r kure && useradd -r -g kure kure

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and change ownership
COPY . .
RUN chown -R kure:kure /app

# Switch to non-root user
USER kure

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
