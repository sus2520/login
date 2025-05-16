# Use Python base image
FROM python:3.10

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app
COPY . .

# Expose FastAPI/Flask port
EXPOSE 8000

# Start the backend server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
