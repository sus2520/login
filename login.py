from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import hashlib
import os
import secrets

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lacd.onrender.com", "https://llama3.test-hr.com", "http://localhost:3000", "<your-frontend-url>"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# Helper functions for password hashing using hashlib
def hash_password(password: str) -> tuple[str, str]:
    # Generate a random salt
    salt = secrets.token_hex(16)  # 16 bytes, hex-encoded
    # Combine password and salt, then hash with SHA-256
    salted_password = (password + salt).encode('utf-8')
    hashed = hashlib.sha256(salted_password).hexdigest()
    # Return the hash and salt (store both in the database)
    return hashed, salt

def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    # Recompute the hash with the provided password and stored salt
    salted_password = (password + salt).encode('utf-8')
    computed_hash = hashlib.sha256(salted_password).hexdigest()
    # Compare the computed hash with the stored hash
    return computed_hash == stored_hash

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
        return {"status": "error", "error": f"User '{name}' is not allowed to sign up."}

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

        # Hash the password and get the salt
        hashed_password, salt = hash_password(password)
        # Store the hashed password and salt (modify the table structure to store the salt)
        cursor.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', (name, email, f"{hashed_password}:{salt}"))
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "user": {"name": name, "email": email}
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


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

        # Extract the stored hash and salt (stored as "hash:salt")
        stored_password = user[3]  # user[3] is the password field
        try:
            stored_hash, salt = stored_password.split(":")
        except ValueError:
            return {"status": "error", "error": "Invalid stored password format"}

        # Verify password
        if not verify_password(password, stored_hash, salt):
            return {"status": "error", "error": "Invalid credentials"}

        return {
            "status": "success",
            "user": {"name": user[1], "email": user[2]}  # user[1] is name, user[2] is email
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}

# Add health check endpoint for Render
@app.get("/healthz")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)