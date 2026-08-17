FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt schedule

# Copy application code
COPY . /app/aquavision-service/
COPY ../services/scheduler/ /app/scheduler/

WORKDIR /app/aquavision-service

# Run scheduler
CMD ["python", "-m", "scheduler.main"]
