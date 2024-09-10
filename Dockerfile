# Use the official Python image as the base image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements.txt file to the container
COPY requirements.txt .
COPY usfmtools /app/usfmtools
COPY listener.py .
COPY entry.sh .
RUN chmod +x entry.sh


ENV OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the listener.py script when the container starts
CMD ["./entry.sh"]