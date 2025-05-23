from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_ollama import OllamaLLM
import os
import io
from docx import Document
import PyPDF2
from PIL import Image
import pytesseract
import sqlite3
import bcrypt

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lacd.onrender.com", "https://llama3.test-hr.com"],  # Added new URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Friendly name to model name mapping
FRIENDLY_MODEL_MAP = {
    "basic": "llama3:8b",
    "ultra": "llama3:70b",
}

AVAILABLE_MODELS = list(FRIENDLY_MODEL_MAP.keys())

class GenerateRequest(BaseModel):
    prompt: str
    model: str = "basic"
    max_new_tokens: int = 1000

def get_llm(friendly_name: str) -> OllamaLLM:
    if friendly_name not in FRIENDLY_MODEL_MAP:
        raise ValueError(f"Model '{friendly_name}' not supported. Use one of {AVAILABLE_MODELS}")
    model_name = FRIENDLY_MODEL_MAP[friendly_name]
    return OllamaLLM(model=model_name, base_url="http://127.0.0.1:11434")

# Database setup
DATABASE = "users.db"

# List of allowed usernames (case-insensitive comparison)
ALLOWED_USERS = {"roberto", "pablo", "shafeena"}

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Initialize the database
init_db()

# Helper functions for password hashing
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

# Pydantic models for signup and login requests
class SignupRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

# Signup endpoint (restricted to allowed users)
@app.post("/signup")
async def signup(request: SignupRequest):
    name = request.name
    email = request.email
    password = request.password

    # Check if the name is in the allowed users list (case-insensitive)
    if name.lower() not in ALLOWED_USERS:
        return {"status": "error", "error": f"User '{name}' is not allowed to sign up.."}

    # Validate input
    if not name or not email or not password:
        return {"status": "error", "error": "Missing required fields"}

    if len(password) < 8:
        return {"status": "error", "error": "Password must be at least 8 characters long"}

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            return {"status": "error", "error": "Email already exists"}

        # Hash the password and store the user
        hashed_password = hash_password(password)
        cursor.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)',
                      (name, email, hashed_password))
        conn.commit()
        conn.close()

        # Return success response (without token)
        return {
            "status": "success",
            "user": {"name": name, "email": email}
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}

# Login endpoint
@app.post("/login")
async def login(request: LoginRequest):
    email = request.email
    password = request.password

    # Validate input
    if not email or not password:
        return {"status": "error", "error": "Missing email or password"}

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            return {"status": "error", "error": "Invalid credentials"}

        # Verify password
        if not verify_password(password, user[3]):  # user[3] is the hashed password
            return {"status": "error", "error": "Invalid credentials"}

        # Since only allowed users can sign up, no additional name check is needed here
        return {
            "status": "success",
            "user": {"name": user[1], "email": user[2]}  # user[1] is name, user[2] is email
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}

# Generate endpoint (no authentication required)
@app.post("/generate")
async def generate_text(request: Request, file: UploadFile = File(None)):
    try:
        data = await request.json()
        prompt = data.get("prompt", "")
        friendly_name = data.get("model", "basic")
        max_new_tokens = data.get("max_new_tokens", 1000)

        if file:
            content = await file.read()
            if file.filename.endswith(".txt"):
                prompt = content.decode("utf-8")
            elif file.filename.endswith(".docx"):
                doc = Document(io.BytesIO(content))
                prompt = "\n".join([para.text for para in doc.paragraphs])
            elif file.filename.endswith(".pdf"):
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
                prompt = ""
                for page in pdf_reader.pages:
                    prompt += page.extract_text() + "\n"
            elif file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff")):
                image = Image.open(io.BytesIO(content))
                prompt = pytesseract.image_to_string(image)
            else:
                return {"status": "error", "error": "Unsupported file type. Supported types: .txt, .docx, .pdf, images (.png, .jpg, .jpeg, .bmp, .tiff)"}

        if friendly_name not in AVAILABLE_MODELS:
            return {"status": "error", "error": f"Invalid model. Choose from {AVAILABLE_MODELS}"}

        llm = get_llm(friendly_name)
        response = llm.invoke(prompt)
        return {"status": "success", "response": response}
    except ValueError as ve:
        return {"status": "error", "error": str(ve)}
    except Exception as e:
        return {"status": "error", "error": f"Failed to generate response: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)