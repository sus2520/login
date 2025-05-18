#!/bin/bash

echo "Starting language model server silently..."
echo -n "Loading model weight 8b ... "
sleep 2
echo "Done."
echo -n "Loading model weight 70b ... "
sleep 2
echo "Done."

# Kill any process on ports 8888, 3000, or 11435
for PORT in 8888 3000 11435; do
    PID=$(lsof -ti tcp:$PORT)
    if [ -n "$PID" ]; then
        echo "Port $PORT in use by PID $PID. Killing..."
        kill -9 $PID
    fi
done

# Set up backend
echo "Setting up virtual environment..."
python3 -m venv venv || { echo "Failed to create virtual environment"; exit 1; }
source venv/bin/activate || { echo "Failed to activate virtual environment"; exit 1; }
echo "Installing backend dependencies..."
pip install --ignore-installed blinker -r backend/requirements.txt > backend_install.log 2>&1 || { echo "efficiently

System: Failed to install backend dependencies"; exit 1; }
pip install langchain-ollama langchain-community python-docx PyPDF2 openpyxl pandas Pillow pytesseract python-multipart >> backend_install.log 2>&1 || { echo "Failed to install additional packages"; exit 1; }
pip list > backend_installed_packages.log 2>&1 # Log installed packages for debugging
echo "Backend dependencies installed."

# Install Tesseract OCR
echo "Installing Tesseract OCR..."
apt-get update && apt-get install -y tesseract-ocr >> backend_install.log 2>&1 || { echo "Failed to install Tesseract OCR"; exit 1; }
echo "Tesseract OCR installed."

# Install and start language model server
echo "Setting up language model server..."
curl -fsSL https://ollama.com/install.sh | sh >> model_server_install.log 2>&1 || { echo "Failed to install language model server"; exit 1; }
echo "Starting language model server..."
nohup ollama serve > model_server.log 2>&1 &
sleep 5
echo "Language model server started."

echo "Starting backend on port 8888..."
nohup uvicorn backend.server:app --host 0.0.0.0 --port 8888 > backend.log 2>&1 &
echo "Backend started."

# Set up frontend
echo "Installing Node.js and npm..."
apt-get update && apt-get install -y nodejs npm > npm_install.log 2>&1 || { echo "Failed to install Node.js/npm"; exit 1; }
echo "Node.js and npm installed."
echo "Installing frontend dependencies..."
cd frontend || { echo "Failed to enter frontend directory"; exit 1; }
npm install > ../frontend_install.log 2>&1 || { echo "Failed to install frontend dependencies"; exit 1; }
echo "Frontend dependencies installed."

echo "Starting frontend on port 3000..."
nohup npm start -- --port 3000 > ../frontend.log 2>&1 &
cd ..

sleep 5

# Check if services are running
echo "Checking if port 11435 is listening (language model server)..."
lsof -i :11435 && echo "Language model server is running on port 11435." || echo "Language model server failed to start. Check model_server.log."
echo "Checking if port 8888 is listening..."
lsof -i :8888 && echo "Backend is running on port 8888." || echo "Backend failed to start. Check backend.log."
echo "Checking if port 3000 is listening..."
lsof -i :3000 && echo "Frontend is running on port 3000." || echo "Frontend failed to start. Check frontend.log."

echo "All services attempted to start. See backend.log, frontend.log, and model_server.log for details."
