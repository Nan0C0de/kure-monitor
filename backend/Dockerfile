FROM python:3.11-slim

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