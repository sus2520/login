cat << EOF > /workspace/fullstack-bot/start.sh
#!/bin/bash

echo "Starting language model server silently..."
echo -n "Loading LLaMA models and dependencies ... "
sleep 2
echo "Done."

# Install lsof if not installed
if ! command -v lsof &> /dev/null; then
    apt-get update >> install_lsof.log 2>&1
    apt-get install -y lsof >> install_lsof.log 2>&1 || { echo "Failed to install lsof"; exit 1; }
fi

# Install curl if not installed (needed for ngrok URL and Ollama check)
if ! command -v curl &> /dev/null; then
    apt-get update >> install_curl.log 2>&1
    apt-get install -y curl >> install_curl.log 2>&1 || { echo "Failed to install curl"; exit 1; }
fi

# Install python3 and pip if not installed
if ! command -v python3 &> /dev/null || ! command -v pip3 &> /dev/null; then
    apt-get update >> install_python.log 2>&1
    apt-get install -y python3 python3-pip >> install_python.log 2>&1 || { echo "Failed to install python3 and pip"; exit 1; }
fi

# Install Tesseract OCR
if ! command -v tesseract &> /dev/null; then
    apt-get update >> install_tesseract.log 2>&1
    apt-get install -y tesseract-ocr >> install_tesseract.log 2>&1 || { echo "Failed to install Tesseract OCR"; exit 1; }
fi

# Install Ollama if not installed
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh >> install_ollama.log 2>&1 || { echo "Failed to install Ollama"; exit 1; }
fi

# Install backend dependencies
python3 -m venv venv || { echo "Failed to create virtual environment"; exit 1; }
source venv/bin/activate || { echo "Failed to activate virtual environment"; exit 1; }
pip install --ignore-installed blinker fastapi uvicorn langchain-ollama python-docx PyPDF2 openpyxl pandas Pillow pytesseract python-multipart >> backend_install.log 2>&1 || { echo "Failed to install backend dependencies"; exit 1; }
pip list > backend_installed_packages.log 2>&1

# Kill any existing ngrok processes to avoid session limit
NGROK_PID=\$(ps aux | grep '[n]grok' | awk '{print \$2}')
if [ -n "\$NGROK_PID" ]; then
    kill -9 \$NGROK_PID
fi

# Kill any process on port 8888 (backend), but not 11434 yet
for PORT in 8888; do
    while PID=\$(lsof -ti tcp:\$PORT); do
        kill -9 \$PID
        sleep 2
    done
done

# Check if Ollama is already running on port 11434
export OLLAMA_HOST=127.0.0.1:11434
if curl -s http://127.0.0.1:11434 > /dev/null; then
    echo "Language model server is already running on port 11434."
else
    # Kill any process on port 11434 if not responding correctly
    while PID=\$(lsof -ti tcp:11434); do
        kill -9 \$PID
        sleep 2
    done
    # Start the language model server (Ollama) on port 11434
    nohup ollama serve > model_server.log 2>&1 &
    MODEL_SERVER_PID=\$!
    sleep 25
    # Verify Ollama is running
    if curl -s http://127.0.0.1:11434 > /dev/null; then
        echo "Language model server started successfully."
    else
        echo "Language model server failed to start. Check model_server.log:"
        if [ -f model_server.log ]; then
            tail -n 20 model_server.log
        else
            echo "model_server.log not found. Ollama may not be installed or executable."
        fi
        exit 1
    fi
fi

# Pull LLaMA models if not already pulled
if ! ollama list | grep -q 'llama3:8b'; then
    ollama pull llama3:8b >> install_models.log 2>&1 || { echo "Failed to pull llama3:8b. Check install_models.log:"; tail -n 20 install_models.log; exit 1; }
fi
if ! ollama list | grep -q 'llama3:70b'; then
    ollama pull llama3:70b >> install_models.log 2>&1 || { echo "Failed to pull llama3:70b. Check install_models.log:"; tail -n 20 install_models.log; exit 1; }
fi

# Install ngrok if not installed
if ! command -v ngrok &> /dev/null; then
    apt-get update >> install_ngrok.log 2>&1
    apt-get install -y wget unzip >> install_ngrok.log 2>&1
    wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.zip >> install_ngrok.log 2>&1 || { echo "Failed to download ngrok"; exit 1; }
    unzip ngrok-v3-stable-linux-amd64.zip >> install_ngrok.log 2>&1 || { echo "Failed to unzip ngrok"; exit 1; }
    mv ngrok /usr/local/bin/ || { echo "Failed to move ngrok to /usr/local/bin"; exit 1; }
    rm ngrok-v3-stable-linux-amd64.zip
fi

# Configure ngrok authtoken
NGROK_AUTHTOKEN="2xGekWSvLSAVOMAujXcR7e4jR3Z_4XiT7v1Ts5yADhN6sCCQh"
for attempt in {1..3}; do
    ngrok authtoken \$NGROK_AUTHTOKEN >> ngrok.log 2>&1 && break
    sleep 5
    if [ \$attempt -eq 3 ]; then
        echo "Failed to configure ngrok authtoken after 3 attempts."
        exit 1
    fi
done

# Start the backend server
source venv/bin/activate
nohup uvicorn backend.server:app --host 0.0.0.0 --port 8888 > backend.log 2>&1 &
BACKEND_PID=\$!
sleep 20

# Check if the backend server is running
if lsof -i :8888 > /dev/null; then
    echo "Backend started successfully."
else
    echo "Backend failed to start. Check backend.log."
    exit 1
fi

# Start ngrok
nohup ngrok http 8888 > ngrok.log 2>&1 &
NGROK_PID=\$!
sleep 10

# Get the ngrok tunnel URL
for attempt in {1..5}; do
    NGROK_URL=\$(curl -s http://localhost:4040/api/tunnels | grep -o 'https://[^"]*.ngrok-free.app')
    if [ -n "\$NGROK_URL" ]; then
        echo "ngrok tunnel started: \$NGROK_URL"
        break
    fi
    sleep 5
    if [ \$attempt -eq 5 ]; then
        echo "Failed to retrieve ngrok URL after retries. Check ngrok.log."
        exit 1
    fi
done

echo "All services started successfully."
echo "Backend API is accessible at \$NGROK_URL"

wait
EOF