FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy application code
COPY . /app/

# Expose port
EXPOSE 8100

# Run API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8100"]
